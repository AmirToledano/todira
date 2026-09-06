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
import logging
import os

from dorin_common.db import get_session
from dorin_common.models import ContactMessage
from dorin_common.support import looks_like_help_request
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
    try:
        username_part = f" (@{user.username})" if user.username else ""
        await context.bot.send_message(
            chat_id=OWNER_TELEGRAM_USER_ID,
            text=(
                f"🙋 <b>בקשת תמיכה תוך כדי שיחה עם הבוט</b>\n"
                f"מאת: {user.first_name or 'משתמש'}{username_part} "
                f"(Telegram user ID: {user.id})\n\n{text}"
            ),
            parse_mode=ParseMode.HTML,
        )
    except TelegramError:
        logger.exception("Failed to forward mid-conversation help request to the owner")
        return False

    await asyncio.to_thread(_mark_notified_sync, contact_message_id)
    return True
