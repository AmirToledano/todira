"""Catch-all for free-text messages that don't match any active conversation or command — e.g. a
user who followed the website's "כתוב/י ישירות לבוט" link and just typed a question. Before this,
such a message silently vanished: neither onboarding.py's nor filter_conversation.py's
ConversationHandler was in an active state for that user, no command matched, and there was no
other handler registered to catch it — the bot simply never replied (found 2026-09-01, the owner
tried it himself via the website's Telegram-contact link and got nothing back).

Registered LAST in bot/main.py's default handler group (group=0) — python-telegram-bot tries
handlers within a group in registration order and stops at the first match, so this only fires
once every other handler (both ConversationHandlers, every CommandHandler) has already declined
the update. Saves a ContactMessage row (same table/shape the website's /contact form uses — see
website/main.py) so a message is never lost even if the Telegram push to the owner fails, then
best-effort notifies the owner directly via context.bot.send_message (no extra HTTP client needed,
unlike website/main.py's _notify_owner_sync — we're already inside the bot's own Application).
"""
from __future__ import annotations

import asyncio
import logging
import os

from dorin_common.db import get_session
from dorin_common.models import ContactMessage
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes, MessageHandler
from telegram.ext import filters as tg_filters

logger = logging.getLogger(__name__)

OWNER_TELEGRAM_USER_ID = os.environ.get("OWNER_TELEGRAM_USER_ID")


def _save_contact_message_sync(name: str | None, telegram_user_id: int, message: str) -> int:
    with get_session() as session:
        row = ContactMessage(
            name=name,
            message=message,
            telegram_user_id=telegram_user_id,
            source="telegram_bot",
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


async def handle_stray_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = update.message.text or ""

    contact_message_id = await asyncio.to_thread(
        _save_contact_message_sync, user.first_name, user.id, text
    )

    notified = False
    if OWNER_TELEGRAM_USER_ID:
        try:
            username_part = f" (@{user.username})" if user.username else ""
            await context.bot.send_message(
                chat_id=OWNER_TELEGRAM_USER_ID,
                text=(
                    f"📬 <b>הודעה חדשה מהבוט</b>\n"
                    f"מאת: {user.first_name or 'משתמש'}{username_part} "
                    f"(Telegram user ID: {user.id})\n\n{text}"
                ),
                parse_mode=ParseMode.HTML,
            )
            notified = True
        except TelegramError:
            logger.exception("Failed to forward stray bot message to the owner")

    if notified:
        await asyncio.to_thread(_mark_notified_sync, contact_message_id)

    await update.message.reply_text(
        "תודה שכתבת! ההודעה שלך התקבלה ואנחנו נחזור אליך בהקדם 🙏\n\n"
        "לחיפוש דירות: /start"
    )


def build_contact_fallback_handler() -> MessageHandler:
    return MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, handle_stray_message)
