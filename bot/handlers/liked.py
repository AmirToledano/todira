"""/liked, plus the shared ❤️/🙈/🎉 inline-button handler attached to every listing card — sent
both by the scraper's new-match notifications and by this bot's /apartments and /liked. The bot
process (long-running, polling) is what receives the button press regardless of which process
originally sent the card.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from dorin_common.cards import format_caption, send_listing_card
from dorin_common.db import get_session
from dorin_common.models import Listing, UserListingAction
from dorin_common.users import get_or_create_user

LIKED_LIMIT = 10


def _load_liked_sync(tg_user) -> list[Listing]:
    with get_session() as session:
        user = get_or_create_user(session, tg_user)
        stmt = (
            select(Listing)
            .join(UserListingAction, UserListingAction.listing_id == Listing.id)
            .where(UserListingAction.user_id == user.id)
            .where(UserListingAction.action == "liked")
            .where(Listing.is_delisted.is_(False))
            .order_by(UserListingAction.created_at.desc())
            .limit(LIKED_LIMIT)
        )
        return list(session.scalars(stmt))


async def liked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # asyncio.to_thread — see handlers/start.py's _upsert_user_sync comment: a synchronous DB
    # call directly on the event loop would freeze every other user's bot interaction too, not
    # just this one, since PTB processes updates one at a time by default.
    results = await asyncio.to_thread(_load_liked_sync, update.effective_user)

    if not results:
        await update.message.reply_text(
            "עדיין לא שמרת אף דירה. אפשר ללחוץ ❤️ שמור על כרטיס דירה כדי לשמור אותה כאן."
        )
        return

    for listing in results:
        await send_listing_card(
            context.bot, update.effective_chat.id, listing, format_caption(listing)
        )


def _apply_reaction_sync(tg_user, action: str, listing_id: int) -> str:
    """Returns the toast text to show via query.answer()."""
    with get_session() as session:
        user = get_or_create_user(session, tg_user)

        if action == "found":
            user.is_active = False
            session.commit()
            return "מזל טוב! השהיתי את החיפוש עבורך. שלח/י /start כדי לחזור."

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

    return "נשמר ❤️" if action == "like" else "הוסתר 🙈"


async def reaction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    action, _, raw_id = query.data.partition(":")
    listing_id = int(raw_id)

    # asyncio.to_thread — see handlers/start.py's _upsert_user_sync comment: a synchronous DB
    # call directly on the event loop would freeze every other user's bot interaction too, not
    # just this one, since PTB processes updates one at a time by default.
    toast = await asyncio.to_thread(_apply_reaction_sync, update.effective_user, action, listing_id)
    await query.answer(toast)


def build_reaction_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(reaction_callback, pattern=r"^(like|hide|found):\d+$")


def build_liked_handler() -> CommandHandler:
    return CommandHandler("liked", liked)
