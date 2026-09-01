"""Catch-all for free-text messages that don't match any active conversation or command — e.g. a
user who followed the website's "כתוב/י ישירות לבוט" link and just typed a question. Before this,
such a message silently vanished: neither onboarding.py's nor filter_conversation.py's
ConversationHandler was in an active state for that user, no command matched, and there was no
other handler registered to catch it — the bot simply never replied (found 2026-09-01, the owner
tried it himself via the website's Telegram-contact link and got nothing back).

Registered LAST in bot/main.py's default handler group (group=0) — python-telegram-bot tries
handlers within a group in registration order and stops at the first match, so this only fires
once every other handler (both ConversationHandlers, every CommandHandler) has already declined
the update. Uses handlers/support.py's save+notify (shared with onboarding.py/filter_conversation.py
— see that module's docstring for why the same "reach a human" need shows up in three different
places) so a message is never lost even if the Telegram push to the owner fails.
"""
from __future__ import annotations

from handlers.support import escalate_to_owner
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler
from telegram.ext import filters as tg_filters


async def handle_stray_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    await escalate_to_owner(update, context, text)

    await update.message.reply_text(
        "תודה שכתבת! ההודעה שלך התקבלה ואנחנו נחזור אליך בהקדם 🙏\n\n"
        "לחיפוש דירות: /start"
    )


def build_contact_fallback_handler() -> MessageHandler:
    return MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, handle_stray_message)
