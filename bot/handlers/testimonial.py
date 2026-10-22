""""Did you find a flat?" and the testimonial that follows a "yes" (2026-10-22, owner approved). See
todira_common/testimonials.py for when the question is asked and how a testimonial reaches the site."""
from __future__ import annotations

import asyncio
import datetime as dt
import html
import logging

from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, ContextTypes

from handlers.support import OWNER_TELEGRAM_USER_ID, _mark_notified_sync
from todira_common import owner_inbox, testimonials
from todira_common.bot_strings import bot_text
from todira_common.db import get_session
from todira_common.language import DEFAULT_LANG
from todira_common.models import ContactMessage, User
from sqlalchemy import select

logger = logging.getLogger(__name__)

AWAITING_KEY = "awaiting_testimonial"


def _user_lang_sync(telegram_user_id: int) -> str:
    with get_session() as session:
        lang = session.scalar(select(User.language).where(User.telegram_user_id == telegram_user_id))
        return lang or DEFAULT_LANG


def _claim_ask_sync(user_id: int) -> bool:
    """True when this user may be asked now (not asked in the last 60 days), and records the ask."""
    now = dt.datetime.now(dt.timezone.utc)
    with get_session() as session:
        if testimonials.asked_recently(session, user_id, now):
            return False
        testimonials.mark_asked(session, user_id, now)
        return True


async def ask_found(bot: Bot, chat_id: int, user_id: int, lang: str) -> None:
    """Asks "did you find a flat?" unless this user was asked recently. Never raises."""
    try:
        if not await asyncio.to_thread(_claim_ask_sync, user_id):
            return
        await bot.send_message(
            chat_id=chat_id, text=bot_text("found_ask.question", lang), reply_markup=testimonials.found_keyboard(lang)
        )
    except Exception:
        logger.exception("Could not ask user %s whether they found a flat", user_id)


async def ask_for_testimonial(bot: Bot, chat_id: int, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
    context.user_data[AWAITING_KEY] = True
    await bot.send_message(chat_id=chat_id, text=bot_text("found_ask.yes_reply", lang))


async def found_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = await asyncio.to_thread(_user_lang_sync, update.effective_user.id)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass
    if query.data == "tq:yes":
        await ask_for_testimonial(context.bot, update.effective_chat.id, context, lang)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=bot_text("found_ask.no_reply", lang))


def _save_sync(name: str | None, telegram_user_id: int, message: str) -> int:
    with get_session() as session:
        row = ContactMessage(name=name, message=message, telegram_user_id=telegram_user_id, source=testimonials.SOURCE)
        session.add(row)
        session.commit()
        return row.id


async def take_testimonial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """When the user was just asked for a testimonial, saves this message as one, tells the owner and thanks the user.
    Returns whether the message was taken (the caller then does nothing else with it)."""
    if not context.user_data.pop(AWAITING_KEY, False):
        return False
    user = update.effective_user
    text = update.message.text or ""
    message_id = await asyncio.to_thread(_save_sync, user.first_name, user.id, text)
    lang = await asyncio.to_thread(_user_lang_sync, user.id)
    await update.message.reply_text(bot_text("found_ask.thanks", lang))
    if OWNER_TELEGRAM_USER_ID:
        owner_text = (
            f"⭐ <b>המלצה חדשה</b>\nמאת: {html.escape(user.first_name or 'משתמש')}\n\n{html.escape(text)}\n\n"
            "אפשר להציג אותה באתר מתיבת ההודעות."
        )
        for chat_id in await asyncio.to_thread(owner_inbox.owner_chat_ids, OWNER_TELEGRAM_USER_ID):
            try:
                await context.bot.send_message(chat_id=chat_id, text=owner_text, parse_mode=ParseMode.HTML)
            except TelegramError:
                logger.exception("Failed to forward a testimonial to the owner")
                continue
            await asyncio.to_thread(_mark_notified_sync, message_id)
            break
    return True


def build_found_answer_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(found_answer_callback, pattern=r"^tq:(yes|no)$")
