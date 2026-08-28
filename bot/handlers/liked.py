"""/liked, plus the shared ❤️/🙈/🎉 inline-button handler attached to every listing card — sent
both by the scraper's new-match notifications and by this bot's /apartments and /liked. The bot
process (long-running, polling) is what receives the button press regardless of which process
originally sent the card.
"""
from __future__ import annotations

from sqlalchemy import select
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from dorin_common.cards import format_caption, listing_keyboard
from dorin_common.db import get_session
from dorin_common.models import Listing, UserListingAction
from dorin_common.users import get_or_create_user

LIKED_LIMIT = 10


async def liked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with get_session() as session:
        user = get_or_create_user(session, update.effective_user)
        stmt = (
            select(Listing)
            .join(UserListingAction, UserListingAction.listing_id == Listing.id)
            .where(UserListingAction.user_id == user.id)
            .where(UserListingAction.action == "liked")
            .where(Listing.is_delisted.is_(False))
            .order_by(UserListingAction.created_at.desc())
            .limit(LIKED_LIMIT)
        )
        results = list(session.scalars(stmt))

    if not results:
        await update.message.reply_text(
            "עדיין לא שמרת אף דירה. אפשר ללחוץ ❤️ שמור על כרטיס דירה כדי לשמור אותה כאן."
        )
        return

    for listing in results:
        await update.message.reply_text(
            format_caption(listing),
            reply_markup=listing_keyboard(listing.id),
            parse_mode=ParseMode.HTML,
        )


async def reaction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    action, _, raw_id = query.data.partition(":")
    listing_id = int(raw_id)

    with get_session() as session:
        user = get_or_create_user(session, update.effective_user)

        if action == "found":
            user.is_active = False
            session.commit()
            await query.answer("מזל טוב! השהיתי את החיפוש עבורך. שלח/י /start כדי לחזור.")
            return

        db_action = "liked" if action == "like" else "hidden"
        exists = session.scalar(
            select(UserListingAction.id).where(
                UserListingAction.user_id == user.id,
                UserListingAction.listing_id == listing_id,
                UserListingAction.action == db_action,
            )
        )
        if not exists:
            session.add(UserListingAction(user_id=user.id, listing_id=listing_id, action=db_action))
            session.commit()

    await query.answer("נשמר ❤️" if action == "like" else "הוסתר 🙈")


def build_reaction_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(reaction_callback, pattern=r"^(like|hide|found):\d+$")


def build_liked_handler() -> CommandHandler:
    return CommandHandler("liked", liked)
