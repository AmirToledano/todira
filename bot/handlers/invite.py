"""/invite and the reward when a friend joins (2026-10-20, owner: "whoever brings a friend gets 5 more days").
The rules are in todira_common/invite.py."""
from __future__ import annotations

import asyncio
import datetime as dt
import html
import logging
from zoneinfo import ZoneInfo

from sqlalchemy import select
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import CommandHandler, ContextTypes
from todira_common import invite
from todira_common.bot_strings import bot_text
from todira_common.db import get_session
from todira_common.language import DEFAULT_LANG
from todira_common.models import User

logger = logging.getLogger(__name__)


def _invite_text_sync(telegram_user_id: int) -> str | None:
    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
        if user is None:
            return None
        return bot_text("invite.text", user.language or DEFAULT_LANG, link=html.escape(invite.invite_link(user.id)))


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = await asyncio.to_thread(_invite_text_sync, update.effective_user.id)
    if text is None:
        text = bot_text("invite.text", DEFAULT_LANG, link="/start")  # not registered yet: /start first
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


def _reward_inviter_sync(telegram_user_id: int, payload: str | None) -> tuple[int, str] | None:
    """(inviter's Telegram id, message to send them) when this /start was a new friend's, else None."""
    if not payload or not payload.startswith(invite.PREFIX):
        return None
    now = dt.datetime.now(dt.timezone.utc)
    with get_session() as session:
        new_user = session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
        if new_user is None:
            return None
        inviter = invite.apply_invite(session, new_user, payload, now)
        if inviter is None or inviter.telegram_user_id is None:
            return None
        until = invite.access_end(inviter, now).astimezone(ZoneInfo("Asia/Jerusalem")).strftime("%d.%m.%Y")
        logger.info("invite: a new friend joined - the inviter got %s more days", invite.INVITE_BONUS.days)
        return inviter.telegram_user_id, bot_text("invite.joined", inviter.language or DEFAULT_LANG, date=until)


async def reward_inviter(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str | None) -> None:
    try:
        result = await asyncio.to_thread(_reward_inviter_sync, update.effective_user.id, payload)
    except Exception:
        logger.exception("invite: could not reward the inviter")
        return
    if result is None:
        return
    chat_id, text = result
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except TelegramError:
        logger.warning("invite: the inviter could not be told (blocked the bot?)")


def build_invite_handlers() -> list:
    return [CommandHandler("invite", invite_command)]
