"""/apartments — the current top matching, non-hidden, non-delisted listings for the user's
saved filter. `find_matching_listings` is also reused by filter_conversation.py to show an
example match right after a filter is saved (mirrors the reference bot's "👀 הראי לי דוגמה"
prompt)."""
from __future__ import annotations

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from config import WEBSITE_URL
from dorin_common.access import has_full_access
from dorin_common.cards import format_caption, send_listing_card
from dorin_common.db import get_session
from dorin_common.enums import NotificationReason
from dorin_common.matching import evaluate
from dorin_common.models import Filter, Listing, SentNotification, User, UserListingAction

RECENT_LISTINGS_SCANNED = 500  # how far back to look before filtering/matching
RESULT_LIMIT = 10

# Mirrors website/main.py's _is_owner_id / bot/handlers/start.py's own copy — same secret, same
# "owner always has full access" override.
OWNER_TELEGRAM_USER_ID = os.environ.get("OWNER_TELEGRAM_USER_ID")


def find_matching_listings(session: Session, user_id: int, filter_row: Filter, limit: int) -> list[Listing]:
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
    )
    if filter_row.cities:
        # Found live 2026-09-07: this only ever narrowed by deal_type, so a filter for one
        # specific (usually less active) city could have its own matching listings permanently
        # pushed out of the RECENT_LISTINGS_SCANNED window by newer listings scraped for every
        # OTHER city — a real, live "silently show fewer/zero matches" bug for exactly the users a
        # narrow filter is meant to serve well. cities is itself a hard filter (matching.py never
        # lets a listing outside it through), so applying it here too only ever removes rows that
        # would have failed evaluate() anyway — never changes which listings can match.
        query = query.where(Listing.city.in_(filter_row.cities))
    recent = session.scalars(
        query.order_by(Listing.scraped_at.desc()).limit(RECENT_LISTINGS_SCANNED)
    )

    matches: list[Listing] = []
    for listing in recent:
        if listing.id in hidden_ids:
            continue
        if evaluate(filter_row, listing).matched:
            matches.append(listing)
        if len(matches) >= limit:
            break
    return matches


def find_new_matches_to_show(
    session: Session, user_id: int, filter_row: Filter, limit: int
) -> tuple[int, list[Listing]]:
    """Returns (total_current_matches, matches_not_yet_shown_to_this_user) — for the "here's what
    matches right now" summary shown right after saving a filter (filter_conversation.py,
    onboarding.py), NOT for /apartments (which should always show everything on demand, see
    find_matching_listings above).

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


def _load_matches_sync(tg_user) -> tuple[bool, list[Listing]] | None:
    """Returns None to signal "no saved filter yet" (vs. an empty list = a real filter with 0
    current matches) — the caller needs to tell the two apart to show a different message.
    Otherwise (has_access, matches) — has_access (dorin_common.access.has_full_access) decides
    whether format_caption below shows the full card or the locked/teaser one, see that module's
    2026-09-05 comment."""
    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
        filter_row = (
            session.scalar(select(Filter).where(Filter.user_id == user.id)) if user else None
        )
        if user is None or filter_row is None:
            return None
        is_owner = bool(OWNER_TELEGRAM_USER_ID) and str(tg_user.id) == str(OWNER_TELEGRAM_USER_ID)
        access = has_full_access(user, is_owner=is_owner)
        matches = find_matching_listings(session, user.id, filter_row, RESULT_LIMIT)
        return access, matches


async def apartments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # asyncio.to_thread — see handlers/start.py's _upsert_user_sync comment: PTB processes
    # updates one at a time by default, so a blocking DB call on the event loop freezes every
    # other user's interaction with the bot too, not just this one.
    result = await asyncio.to_thread(_load_matches_sync, update.effective_user)
    if result is None:
        await update.message.reply_text("עדיין לא הגדרת סינון. שלח/י /filter כדי להתחיל.")
        return
    has_access, matches = result

    if not matches:
        await update.message.reply_text(
            "לא נמצאו כרגע דירות תואמות. אני אמשיך לחפש ואודיע לך כשתתפרסם דירה מתאימה."
        )
        return

    upgrade_url = f"{WEBSITE_URL}/upgrade?uid={update.effective_user.id}"
    for listing in matches:
        await send_listing_card(
            context.bot,
            update.effective_chat.id,
            listing,
            format_caption(listing, has_access=has_access, upgrade_url=upgrade_url),
        )


def build_apartments_handler() -> CommandHandler:
    return CommandHandler("apartments", apartments)
