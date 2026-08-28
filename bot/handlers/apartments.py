"""/apartments — the current top matching, non-hidden, non-delisted listings for the user's
saved filter. `find_matching_listings` is also reused by filter_conversation.py to show an
example match right after a filter is saved (mirrors the reference bot's "👀 הראי לי דוגמה"
prompt)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes

from dorin_common.cards import format_caption, listing_keyboard
from dorin_common.db import get_session
from dorin_common.matching import evaluate
from dorin_common.models import Filter, Listing, User, UserListingAction

RECENT_LISTINGS_SCANNED = 200  # how far back to look before filtering/matching
RESULT_LIMIT = 10


def find_matching_listings(session: Session, user_id: int, filter_row: Filter, limit: int) -> list[Listing]:
    hidden_ids = set(
        session.scalars(
            select(UserListingAction.listing_id).where(
                UserListingAction.user_id == user_id,
                UserListingAction.action == "hidden",
            )
        )
    )

    recent = session.scalars(
        select(Listing)
        .where(Listing.deal_type == filter_row.deal_type)
        .where(Listing.is_delisted.is_(False))
        .order_by(Listing.scraped_at.desc())
        .limit(RECENT_LISTINGS_SCANNED)
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


async def apartments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
        filter_row = (
            session.scalar(select(Filter).where(Filter.user_id == user.id)) if user else None
        )
        if user is None or filter_row is None:
            await update.message.reply_text("עדיין לא הגדרת סינון. שלח/י /filter כדי להתחיל.")
            return

        matches = find_matching_listings(session, user.id, filter_row, RESULT_LIMIT)

    if not matches:
        await update.message.reply_text(
            "לא נמצאו כרגע דירות תואמות. אני אמשיך לחפש ואודיע לך כשתתפרסם דירה מתאימה."
        )
        return

    for listing in matches:
        await update.message.reply_text(
            format_caption(listing),
            reply_markup=listing_keyboard(listing.id),
            parse_mode=ParseMode.HTML,
        )


def build_apartments_handler() -> CommandHandler:
    return CommandHandler("apartments", apartments)
