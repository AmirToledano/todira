"""Shared "this message is a support/help request, not apartment criteria" detector + escalation,
used by onboarding.py and filter_conversation.py. contact_fallback.py's catch-all only fires when
NO ConversationHandler is active for the user — but a user mid-onboarding or mid-/filter who types
"I want to talk to a human" is very much inside an active conversation, whose own handler happily
tries to reinterpret that as apartment search criteria and just re-asks its own question forever
(found 2026-09-01: a real tester asked for support three times inside onboarding and got the same
"which city, rent or buy?" prompt every time). This module lets both conversations recognize that
intent and forward it to the owner exactly like contact_fallback.py does, without abandoning
whatever state the user was in.
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import time

from todira_common import owner_inbox
from todira_common.db import get_session
from todira_common.models import ContactMessage
from todira_common.support import looks_like_help_request
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

OWNER_TELEGRAM_USER_ID = os.environ.get("OWNER_TELEGRAM_USER_ID")

__all__ = ["escalate_to_owner", "looks_like_help_request", "looks_like_a_sentence"]


def looks_like_a_sentence(text: str) -> bool:
    """True when text reads like a real message rather than a single failed attempt at the value
    a menu prompt asked for. Used where there's no keyword-based signal to go on (see
    filter_conversation.py's numeric/date/city prompts, which don't call Gemini) — a genuine typo
    at a number/date field is almost always one token ("500rf", "3.5.2"), while an actual question
    is almost always more than one word."""
    return len((text or "").split()) >= 2


def _save_sync(name: str | None, telegram_user_id: int, message: str) -> int:
    with get_session() as session:
        row = ContactMessage(
            name=name, message=message, telegram_user_id=telegram_user_id, source="telegram_bot"
        )
        session.add(row)
        session.commit()
        return row.id


def _mark_notified_sync(contact_message_id: int) -> None:
    with get_session() as session:
        row = session.get(ContactMessage, contact_message_id)
        if row is not None:
            row.notified_owner = True
            session.commit()


async def escalate_to_owner(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """Saves a ContactMessage and best-effort notifies the owner. Returns whether the owner
    notification actually went through (mirrors contact_fallback.py's own notified_owner tracking)."""
    user = update.effective_user
    contact_message_id = await asyncio.to_thread(_save_sync, user.first_name, user.id, text)

    if not OWNER_TELEGRAM_USER_ID:
        return False
    # user.first_name/username and the message text itself are all attacker-controlled (any
    # Telegram user can set their own name or type anything) — escaped before going into an
    # HTML-parsed message so they can't break the owner notification's formatting or inject a
    # fake link/tag into what the owner reads as trusted app text.
    display_name = html.escape(user.first_name or "משתמש")
    username_part = f" (@{html.escape(user.username)})" if user.username else ""
    owner_text = (
        f"🙋 <b>בקשת תמיכה תוך כדי שיחה עם הבוט</b>\n"
        f"מאת: {display_name}{username_part} "
        f"(Telegram user ID: {user.id})\n\n{html.escape(text)}"
    )
    # 2026-10-20: the owner's inbox group first when he has one, then his private chat (todira_common/owner_inbox.py)
    for chat_id in await asyncio.to_thread(owner_inbox.owner_chat_ids, OWNER_TELEGRAM_USER_ID):
        try:
            await context.bot.send_message(chat_id=chat_id, text=owner_text, parse_mode=ParseMode.HTML)
        except TelegramError:
            logger.exception("Failed to forward mid-conversation help request to the owner")
            continue
        await asyncio.to_thread(_mark_notified_sync, contact_message_id)
        return True
    return False


# 2026-10-24 (owner): /support - the next message the user writes goes straight to the owner's inbox group.
from telegram.ext import CommandHandler, ConversationHandler, MessageHandler, filters  # noqa: E402

from todira_common.bot_strings import bot_text  # noqa: E402

AWAIT_SUPPORT_TEXT = 0


def _lang_sync(telegram_user_id: int) -> str:
    from handlers.testimonial import _user_lang_sync

    return _user_lang_sync(telegram_user_id)


# 2026-10-29 (code review): the wait for the support message is saved across restarts, so a /support nobody followed up
# turned the user's next search message - days later - into a support ticket. After this long it is no longer the answer.
SUPPORT_WAIT_SECONDS = 15 * 60


def _pass_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ends the support wait and hands this same update to the bot's other handlers once the wait is over."""
    context.user_data.pop("support_at", None)
    context.application.create_task(context.application.process_update(update))
    return ConversationHandler.END


async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = await asyncio.to_thread(_lang_sync, update.effective_user.id)
    context.user_data["support_at"] = time.time()
    await update.message.reply_text(bot_text("support.prompt", lang))
    return AWAIT_SUPPORT_TEXT


async def support_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if time.time() - context.user_data.get("support_at", 0) > SUPPORT_WAIT_SECONDS:
        return _pass_on(update, context)
    context.user_data.pop("support_at", None)
    lang = await asyncio.to_thread(_lang_sync, update.effective_user.id)
    await escalate_to_owner(update, context, update.message.text or "")
    await update.message.reply_text(bot_text("support.sent", lang))
    return ConversationHandler.END


async def support_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = await asyncio.to_thread(_lang_sync, update.effective_user.id)
    await update.message.reply_text(bot_text("support.cancelled", lang))
    return ConversationHandler.END


async def _support_other_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Another command while /support waits for text: drop the wait and run that command (2026-10-29: it used to be
    swallowed - /start or /filter got no reply at all)."""
    return _pass_on(update, context)


def build_support_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("support", support_start)],
        states={AWAIT_SUPPORT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_text)]},
        fallbacks=[
            CommandHandler("cancel", support_cancel),
            MessageHandler(filters.COMMAND, _support_other_command),
        ],
        name="support_conversation",
        persistent=True,
        allow_reentry=True,
        conversation_timeout=None,
    )
