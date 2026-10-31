"""The four answers to the morning "is the search still right?" message (scraper/checkin.py, 2026-10-31).

✅ keeps everything as it is, ✏️ opens /filter (an entry point of the filter conversation, see
filter_conversation.build_filter_conversation_handler), ⏸️ pauses the alerts like /profile does, and 🎉 pauses them like a
card's "found a flat" button and asks for a short testimonial.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, ContextTypes

from handlers.testimonial import ask_for_testimonial, ask_found
from todira_common.bot_strings import bot_text
from todira_common.db import get_session
from todira_common.language import DEFAULT_LANG
from todira_common.models import User

logger = logging.getLogger(__name__)


def _pause_sync(telegram_user_id: int) -> tuple[int | None, str]:
    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
        if user is None:
            return None, DEFAULT_LANG
        user.is_active = False
        session.commit()
        return user.id, user.language or DEFAULT_LANG


async def _answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    choice = query.data.split(":", 1)[1]
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass  # an old message can't be edited any more; the answer still counts
    if choice == "ok":
        await query.answer("👍")
        return
    user_id, lang = await asyncio.to_thread(_pause_sync, update.effective_user.id)
    if choice == "pause":
        await query.answer(bot_text("checkin.paused", lang), show_alert=True)
        if user_id is not None:
            await ask_found(context.bot, update.effective_chat.id, user_id, lang)
        return
    await query.answer(bot_text("liked.found_paused", lang), show_alert=True)
    try:
        await ask_for_testimonial(context.bot, update.effective_chat.id, context, lang)
    except Exception:
        logger.exception("Could not ask user %s for a testimonial", update.effective_user.id)


def build_checkin_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(_answer, pattern=r"^ci:(ok|pause|found)$")
