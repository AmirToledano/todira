"""/apartments — how many of the user's saved filter's current matches exist right now, with a
link to see them all on the website. `find_matching_listings` is also reused by
filter_conversation.py to compute the same "how many match right now" count right after a filter
is saved."""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from config import WEBSITE_URL
from dorin_common.db import get_session
from dorin_common.enums import NotificationReason
from dorin_common.matching import evaluate
from dorin_common.models import Filter, Listing, SentNotification, User, UserListingAction


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
    recent = session.scalars(query.order_by(Listing.scraped_at.desc()))

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
    onboarding.py), NOT for /apartments (which should always show everything on demand, see
    find_matching_listings above). `limit=None` (the default, and what both real call sites use)
    means `total` is the TRUE current match count, not bounded by anything — see
    find_matching_listings' own 2026-09-15 comment on why that matters here specifically.

    Records each newly-shown listing as a SentNotification (reason=NEW) — the SAME bookkeeping
    the scraper's own notifier uses (scraper/notifier.py) — so a listing shown here is never
    repeated, whether the same user re-saves/tweaks their filter and gets shown matches again, or
    a later scrape run would otherwise push it as a "new match". Found live 2026-09-02: saving a
    filter always resent every single current match in full, every time — a real user tweaking
    their filter a few times in a row got the same cards over and over, flooding their chat.
    Caller is responsible for committing afterward (matches the existing session-per-call-site
    pattern in filter_conversation.py/onboarding.py, no session.commit() here)."""
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


def _count_matches_sync(tg_user) -> int | None:
    """Returns None to signal "no saved filter yet" (vs. 0 = a real filter with no current
    matches) — the caller needs to tell the two apart to show a different message. Otherwise the
    TRUE total number of current matches, no cap (see find_matching_listings' own 2026-09-15
    comment).

    2026-09-15: this used to load up to RESULT_LIMIT=10 Listing rows and send each as its own
    Telegram card directly in the chat. Real owner complaint the same day: for a broad filter
    (thousands of matches) that both flooded the chat with an arbitrary, uninformative subset of
    only 10 AND never told the user how many really matched. Same fix direction as
    filter_conversation._handle_save's own 2026-09-15 change: just the count, plus a link to the
    website's own full, paginated /apartments view — which already applies its own
    has_access/locked-card gating (see website/main.py's own /apartments route), so this command
    doesn't need to know or care about access level at all anymore."""
    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
        filter_row = (
            session.scalar(select(Filter).where(Filter.user_id == user.id)) if user else None
        )
        if user is None or filter_row is None:
            return None
        return len(find_matching_listings(session, user.id, filter_row))


async def apartments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # asyncio.to_thread — see handlers/start.py's _upsert_user_sync comment: PTB processes
    # updates one at a time by default, so a blocking DB call on the event loop freezes every
    # other user's interaction with the bot too, not just this one.
    total = await asyncio.to_thread(_count_matches_sync, update.effective_user)
    if total is None:
        await update.message.reply_text("עדיין לא הגדרת סינון. שלח/י /filter כדי להתחיל.")
        return

    apartments_url = f"{WEBSITE_URL}/apartments?uid={update.effective_user.id}"
    if total:
        await update.message.reply_text(
            f"👀 יש כרגע {total} דירות שמתאימות — כולן כאן: {apartments_url}"
        )
    else:
        await update.message.reply_text(
            "לא נמצאו כרגע דירות תואמות. אני אמשיך לחפש ואודיע לך כשתתפרסם דירה מתאימה. "
            f"אפשר גם לעקוב באתר: {apartments_url}"
        )


def build_apartments_handler() -> CommandHandler:
    return CommandHandler("apartments", apartments)
