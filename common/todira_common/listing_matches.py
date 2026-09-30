"""Shared "which listings currently match this filter" query + bookkeeping — used by the bot
(bot/handlers/apartments.py, which re-exports both names below for its own existing callers/tests),
and by website/whatsapp_webhook.py (2026-09-27) for the WhatsApp-connect "here's what already
matches" summary. Moved here from bot/handlers/apartments.py because it's no longer bot-only: the
website's WhatsApp webhook needs the exact same query+evaluate()+SentNotification bookkeeping, and
website's Docker image doesn't (and shouldn't) copy bot/ — same reasoning as todira_common/cards.py
and todira_common/whatsapp_client.py's own moves.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from todira_common.enums import NotificationReason
from todira_common.matching import evaluate
from todira_common.models import Filter, Listing, SentNotification, UserListingAction


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
    hidden_ids = set(
        session.scalars(
            select(UserListingAction.listing_id).where(
                UserListingAction.user_id == user_id,
                UserListingAction.action == "hidden",
            )
        )
    )

    query = (
        select(Listing)
        .where(Listing.deal_type == filter_row.deal_type)
        .where(Listing.is_delisted.is_(False))
        # 2026-09-13 cross-source dedup — a duplicate row is a real DB row (still upserted/
        # price-refreshed every run) but never its own visible listing, see models.py's
        # Listing.duplicate_of_id docstring.
        .where(Listing.duplicate_of_id.is_(None))
    )
    if filter_row.cities:
        # Found live 2026-09-07: this only ever narrowed by deal_type, so a filter for one
        # specific (usually less active) city could have its own matching listings permanently
        # pushed out of the old recency window by newer listings scraped for every OTHER city — a
        # real, live "silently show fewer/zero matches" bug for exactly the users a narrow filter
        # is meant to serve well. cities is itself a hard filter (matching.py never lets a
        # listing outside it through), so applying it here too only ever removes rows that would
        # have failed evaluate() anyway — never changes which listings can match.
        query = query.where(Listing.city.in_(filter_row.cities))
    recent = session.scalars(query.order_by(Listing.first_seen_at.desc(), Listing.id.desc()))

    matches: list[Listing] = []
    for listing in recent:
        if listing.id in hidden_ids:
            continue
        if evaluate(filter_row, listing).matched:
            matches.append(listing)
        if limit is not None and len(matches) >= limit:
            break
    return matches


def find_new_matches_to_show(
    session: Session, user_id: int, filter_row: Filter, limit: int | None = None
) -> tuple[int, list[Listing]]:
    """Returns (total_current_matches, matches_not_yet_shown_to_this_user) — for the "here's what
    matches right now" summary shown right after saving a filter (filter_conversation.py,
    onboarding.py) or right after connecting WhatsApp (website/whatsapp_webhook.py), NOT for
    /apartments (which should always show everything on demand, see find_matching_listings above).
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
    pattern in filter_conversation.py/onboarding.py/whatsapp_webhook.py, no session.commit() here).
    """
    matches = find_matching_listings(session, user_id, filter_row, limit)
    already_shown_ids = set(
        session.scalars(
            select(SentNotification.listing_id).where(SentNotification.user_id == user_id)
        )
    )
    new_to_show = [m for m in matches if m.id not in already_shown_ids]
    for listing in new_to_show:
        session.add(
            SentNotification(user_id=user_id, listing_id=listing.id, reason=NotificationReason.NEW)
        )
    return len(matches), new_to_show
