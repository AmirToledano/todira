"""Shared "which listings currently match this filter" query + bookkeeping — used by the bot
(bot/handlers/apartments.py, which re-exports both names below for its own existing callers/tests).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from todira_common.enums import NotificationReason
from todira_common.matching import evaluate
from todira_common.models import Filter, Listing, SentNotification, UserListingAction

# 2026-10-14 (owner: "the site is slow"): measured live, /apartments took 16-27 s on the server — every request (and
# every infinite-scroll page) loaded EVERY candidate listing as a full ORM object, raw_payload JSON and photo lists
# included, just to run evaluate() on it, with ~140,000 active listings since the full-country sweeps. Matching now
# reads only the columns evaluate() looks at, as plain rows; full Listing objects are loaded only for the listings that
# are actually shown. tests/test_listing_matches_columns.py keeps this list in step with matching.py.
MATCH_COLUMNS = (
    Listing.id,
    Listing.first_seen_at,
    Listing.deal_type,
    Listing.property_type,
    Listing.city,
    Listing.neighborhood,
    Listing.street,
    Listing.latitude,
    Listing.longitude,
    Listing.price,
    Listing.rooms,
    Listing.floor,
    Listing.size_sqm,
    Listing.move_in_date,
    Listing.safe_room_type,
    Listing.furniture,
    Listing.is_broker_listing,
    Listing.description,
    Listing.has_parking,
    Listing.has_elevator,
    Listing.has_balcony,
    Listing.pets_allowed,
    Listing.is_renovated,
    Listing.is_roommate_friendly,
)


def hidden_listing_ids(session: Session, user_id: int) -> set[int]:
    return set(
        session.scalars(
            select(UserListingAction.listing_id).where(
                UserListingAction.user_id == user_id,
                UserListingAction.action == "hidden",
            )
        )
    )


def matching_listing_rows(session: Session, filter_row: Filter, hidden_ids: set[int] | None = None) -> list:
    """Every active, non-duplicate listing that matches `filter_row`, newest first, as light rows (only MATCH_COLUMNS,
    attribute access like a Listing). The single place the "which listings match" scan lives: the bot, the website's
    /apartments and the filter-save summary all use it."""
    query = (
        select(*MATCH_COLUMNS)
        .where(Listing.deal_type == filter_row.deal_type)
        .where(Listing.is_delisted.is_(False))
        # 2026-09-13 cross-source dedup — a duplicate row is a real DB row (still upserted/price-refreshed every run)
        # but never its own visible listing, see models.py's Listing.duplicate_of_id docstring.
        .where(Listing.duplicate_of_id.is_(None))
    )
    if filter_row.cities:
        # cities is a hard filter (matching.py never lets a listing outside it through), so applying it here too only
        # ever removes rows that would have failed evaluate() anyway — never changes which listings can match.
        query = query.where(Listing.city.in_(filter_row.cities))
    # Price and rooms are hard filters too: the same comparisons matching.py's _check_hard_filters makes (a missing
    # price passes unless require_price; a missing room count fails once a rooms range is set), so the database drops
    # what evaluate() would drop anyway and Python only checks the rest. evaluate() still has the final word.
    price_min, price_max = getattr(filter_row, "price_min", None), getattr(filter_row, "price_max", None)
    if getattr(filter_row, "require_price", False):
        query = query.where(Listing.price.is_not(None))
    if price_min is not None:
        query = query.where(or_(Listing.price.is_(None), Listing.price >= price_min))
    if price_max is not None:
        query = query.where(or_(Listing.price.is_(None), Listing.price <= price_max))
    rooms_min, rooms_max = getattr(filter_row, "rooms_min", None), getattr(filter_row, "rooms_max", None)
    if rooms_min is not None:
        query = query.where(Listing.rooms >= rooms_min)
    if rooms_max is not None:
        query = query.where(Listing.rooms <= rooms_max)
    hidden_ids = hidden_ids or set()
    return [
        row
        for row in session.execute(query.order_by(Listing.first_seen_at.desc(), Listing.id.desc()))
        if row.id not in hidden_ids and evaluate(filter_row, row).matched
    ]


def load_listings(session: Session, ids: list[int]) -> list[Listing]:
    """Full Listing objects for `ids`, in the same order (an id that no longer exists is skipped)."""
    if not ids:
        return []
    by_id: dict[int, Listing] = {}
    for start in range(0, len(ids), 1000):
        chunk = ids[start : start + 1000]
        by_id.update((listing.id, listing) for listing in session.scalars(select(Listing).where(Listing.id.in_(chunk))).all())
    return [by_id[i] for i in ids if i in by_id]


def find_matching_listings(
    session: Session, user_id: int, filter_row: Filter, limit: int | None = None
) -> list[Listing]:
    """`limit=None` (the default) scans every active listing that could possibly match — no
    artificial recency window. 2026-09-15: used to stop the underlying query at the 500
    most-recently-scraped rows (a constant then called RECENT_LISTINGS_SCANNED) before filtering,
    regardless of `limit` — a real owner complaint the same day for the filter-save flow
    (find_new_matches_to_show below): a broad filter matching thousands of listings only ever got
    credit for whichever happened to be among the 500 most recent, so both the reported count and
    the /apartments link's own now-unrelated 500-row cap (website/main.py) silently hid the rest.
    Removed here — `limit` (kept as an optional parameter for any future caller that genuinely
    wants a small preview; nothing in this codebase currently passes one) is the only bound this
    function still supports; a real DB read of a few thousand rows plus a cheap in-Python
    evaluate() per row is not a concern at this project's current scale, and only ever runs once
    per explicit action (a filter save, or the bot's own /apartments command's count-only check —
    see apartments.py's own _count_matches_sync, which also dropped its old RESULT_LIMIT=10 cap
    the same day), never on every page scroll."""
    rows = matching_listing_rows(session, filter_row, hidden_listing_ids(session, user_id))
    if limit is not None:
        rows = rows[:limit]
    return load_listings(session, [row.id for row in rows])


def find_new_matches_to_show(
    session: Session,
    user_id: int,
    filter_row: Filter,
    limit: int | None = None,
    since: dt.datetime | None = None,
) -> tuple[int, list[Listing]]:
    """Returns (total_current_matches, matches_not_yet_shown_to_this_user) — for the "here's what
    matches right now" summary shown right after saving a filter (filter_conversation.py,
    onboarding.py), NOT for
    /apartments (which should always show everything on demand, see find_matching_listings above).
    `since` (2026-10-02): only listings FIRST SEEN at/after it are returned and marked shown.
    `limit=None` (the default, and what every real call site uses) means `total` is the TRUE
    current match count, not bounded by anything — see find_matching_listings' own 2026-09-15
    comment on why that matters here specifically.

    Records each newly-shown listing as a SentNotification (reason=NEW) — the SAME bookkeeping
    the scraper's own notifier uses (scraper/notifier.py) — so a listing shown here is never
    repeated, whether the same user re-saves/tweaks their filter and gets shown matches again, or
    a later scrape run would otherwise push it as a "new match". Found live 2026-09-02: saving a
    filter always resent every single current match in full, every time — a real user tweaking
    their filter a few times in a row got the same cards over and over, flooding their chat.
    Caller is responsible for committing afterward (matches the existing session-per-call-site
    pattern in filter_conversation.py/onboarding.py, no session.commit() here).
    """
    matches = matching_listing_rows(session, filter_row, hidden_listing_ids(session, user_id))
    if limit is not None:
        matches = matches[:limit]
    already_shown_ids = set(
        session.scalars(
            select(SentNotification.listing_id).where(SentNotification.user_id == user_id)
        )
    )
    new_to_show = load_listings(session, [
        m.id for m in matches
        if m.id not in already_shown_ids and (since is None or m.first_seen_at >= since)
    ])
    for listing in new_to_show:
        session.add(
            SentNotification(user_id=user_id, listing_id=listing.id, reason=NotificationReason.NEW)
        )
    return len(matches), new_to_show
