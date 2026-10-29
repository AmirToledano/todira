"""/language — lets a user pick which of the 5 supported languages the bot talks to them in.

2026-10-18 real owner report: a friend's bot opened in English (it followed the phone's language) and there was
no way at all to switch it to Hebrew. New users now always start in Hebrew (see start.py), and this command (also
a button in /profile) switches it. The choice is stored on User.language, which every handler, the alerts and the
website already read."""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from todira_common.bot_strings import bot_text
from todira_common.db import get_session
from todira_common.language import DEFAULT_LANG, SUPPORTED_LANGS
from todira_common.models import User
from todira_common.users import get_or_create_user

# Each language's name in itself, so anyone can find their own whatever language the bot is in now.
LANGUAGE_LABELS = {
    "he": "עברית",
    "en": "English",
    "ru": "Русский",
    "fr": "Français",
    "ar": "العربية",
}


def language_keyboard(current: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(("✅ " if code == current else "") + LANGUAGE_LABELS[code], callback_data=f"lang:set:{code}")]
        for code in SUPPORTED_LANGS
    ]
    return InlineKeyboardMarkup(rows)


def _current_language_sync(tg_user) -> str:
    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
        return (user.language if user is not None else None) or DEFAULT_LANG


def _set_language_sync(tg_user, code: str) -> None:
    with get_session() as session:
        user = get_or_create_user(session, tg_user)
        # Hebrew is stored as None, like every new user: "never changed" and "chose Hebrew" mean the same thing.
        user.language = None if code == DEFAULT_LANG else code
        session.commit()


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current = await asyncio.to_thread(_current_language_sync, update.effective_user)
    await update.message.reply_text(bot_text("language.prompt", current), reply_markup=language_keyboard(current))


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    if data == "lang:menu":
        # The button in /profile: the picker comes as its own message, the profile stays as it was.
        current = await asyncio.to_thread(_current_language_sync, update.effective_user)
        await query.answer()
        await query.message.reply_text(bot_text("language.prompt", current), reply_markup=language_keyboard(current))
        return

    code = data.removeprefix("lang:set:")
    if code not in SUPPORTED_LANGS:
        await query.answer()
        return
    await asyncio.to_thread(_set_language_sync, update.effective_user, code)
    # A /start or /filter conversation already open keeps its language in user_data; switch it too, so the very
    # next reply is already in the new language.
    for key in ("onboarding_lang", "lang"):
        if key in context.user_data:
            context.user_data[key] = code
    await query.answer()
    try:
        await query.edit_message_text(bot_text("language.changed", code), reply_markup=language_keyboard(code))
    except BadRequest as exc:  # 2026-10-29: tapping the language already chosen leaves the message as it is
        if "message is not modified" not in str(exc).lower():
            raise


def build_language_handlers() -> list:
    return [
        CommandHandler("language", language_command),
        CallbackQueryHandler(language_callback, pattern=r"^lang:"),
    ]
