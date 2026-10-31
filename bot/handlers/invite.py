"""Invite a friend (2026-10-31, todira_common/referrals.py): /invite and the button in /profile send the user their own
link, with a button that opens Telegram's share screen with a ready text."""
from __future__ import annotations

import asyncio
from urllib.parse import quote

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from todira_common import referrals
from todira_common.bot_strings import bot_text
from todira_common.db import get_session
from todira_common.language import DEFAULT_LANG
from todira_common.models import User


def _user_sync(telegram_user_id: int) -> tuple[int | None, str]:
    with get_session() as session:
        row = session.execute(
            select(User.id, User.language).where(User.telegram_user_id == telegram_user_id)
        ).first()
        return (row.id, row.language or DEFAULT_LANG) if row else (None, DEFAULT_LANG)


def invite_reply(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    link = referrals.invite_link(user_id)
    share_text = bot_text("invite.share_text", lang, days=referrals.REWARD_DAYS)
    share_url = f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(share_text, safe='')}"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(bot_text("invite.share_btn", lang), url=share_url)]])
    return bot_text("invite.message", lang, days=referrals.REWARD_DAYS, link=link), markup


async def _send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query is not None:
        await update.callback_query.answer()
    user_id, lang = await asyncio.to_thread(_user_sync, update.effective_user.id)
    if user_id is None:
        return  # not signed up yet: /start first
    text, markup = invite_reply(user_id, lang)
    await update.effective_message.reply_text(text, reply_markup=markup, disable_web_page_preview=True)


def build_invite_handlers() -> list:
    return [CommandHandler("invite", _send), CallbackQueryHandler(_send, pattern=r"^invite:show$")]
