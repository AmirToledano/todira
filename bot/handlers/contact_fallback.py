"""Catch-all for free-text messages that don't match any active conversation or command — e.g. a
user who followed the website's "כתוב/י ישירות לבוט" link and just typed a question. Before this,
such a message silently vanished: neither onboarding.py's nor filter_conversation.py's
ConversationHandler was in an active state for that user, no command matched, and there was no
other handler registered to catch it — the bot simply never replied (found 2026-09-01, the owner
tried it himself via the website's Telegram-contact link and got nothing back).

Registered LAST in bot/main.py's default handler group (group=0) — python-telegram-bot tries
handlers within a group in registration order and stops at the first match, so this only fires
once every other handler (both ConversationHandlers, every CommandHandler) has already declined
the update.

Only ACTUAL support/help requests (handlers/support.py's looks_like_help_request — the same
keyword check onboarding.py and filter_conversation.py use mid-conversation) get escalated to the
owner. Everything else — plain small talk ("מה שלומך"), a stray apartment question typed outside
any active flow, literally anything without a help/complaint keyword — was WRONGLY being treated
as a support ticket too before this fix: the owner tested the bot himself and every message he
sent, including "מה שלומך", came back with "your message was received, we'll get back to you"
and generated a real support notification (2026-09-02, live screenshot). Fixed by only escalating
on looks_like_help_request; anything else gets a plain redirect to /start instead, no escalation,
no ContactMessage saved — mirrors onboarding.py's own looks_like_help_request branch exactly.
"""
from __future__ import annotations

from handlers.support import escalate_to_owner, looks_like_help_request
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler
from telegram.ext import filters as tg_filters


async def handle_stray_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""

    if looks_like_help_request(text):
        await escalate_to_owner(update, context, text)
        await update.message.reply_text(
            "תודה שכתבת! ההודעה שלך התקבלה ואנחנו נחזור אליך בהקדם 🙏\n\n"
            "לחיפוש דירות: /start"
        )
        return

    await update.message.reply_text(
        "היי! 🐶 אני טודירה, בוט חיפוש הדירות. כדי להתחיל לחפש דירה, שלח/י /start."
    )


def build_contact_fallback_handler() -> MessageHandler:
    return MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, handle_stray_message)
