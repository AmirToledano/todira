"""Catch-all for free-text messages that don't match any active conversation or command.

Registered LAST in bot/main.py's default handler group (group=0) — python-telegram-bot tries
handlers within a group in registration order and stops at the first match, so this only fires
once every other handler (both ConversationHandlers, every CommandHandler) has already declined
the update.

Three cases, in order:
1. Only ACTUAL support/help requests (handlers/support.py's looks_like_help_request — the same
   keyword check onboarding.py and filter_conversation.py use mid-conversation) get escalated to
   the owner. Plain small talk ("מה שלומך"), a stray apartment question, anything without a
   help/complaint keyword was WRONGLY being treated as a support ticket too before an earlier fix
   (2026-09-02) — that fix is unchanged here, still checked first.
2. 2026-09-06: an already-onboarded user (has a Filter) gets a REAL chat reply via
   gemini_client.chat_with_existing_user instead of the plain "type /start" redirect below — found
   live by the owner comparing against the reference bot, whose already-onboarded users get real,
   contextual, varied replies (and can edit their filter conversationally) instead of a message
   that doesn't even acknowledge they're already registered. Mirrors website/whatsapp_webhook.py's
   identical fix for the same underlying gap on that channel.
3. No filter yet and not a help request — before this fix, such a message silently vanished
   entirely (found 2026-09-01, the owner tried it himself via the website's Telegram-contact link
   and got nothing back); this is the original plain redirect to /start.
"""
from __future__ import annotations

import asyncio

from dorin_common import cities, gemini_client
from dorin_common.db import get_session
from dorin_common.matching import safe_range_update
from dorin_common.models import Filter
from dorin_common.users import get_or_create_user
from handlers.support import escalate_to_owner, looks_like_help_request
from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler
from telegram.ext import filters as tg_filters


def _load_filter_sync(tg_user) -> tuple[int, dict | None]:
    with get_session() as session:
        user = get_or_create_user(session, tg_user)
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user.id))
        if filter_row is None:
            return user.id, None
        current_filter = {
            "deal_type": filter_row.deal_type,
            "cities": filter_row.cities,
            "rooms_min": float(filter_row.rooms_min) if filter_row.rooms_min is not None else None,
            "rooms_max": float(filter_row.rooms_max) if filter_row.rooms_max is not None else None,
            "price_min": filter_row.price_min,
            "price_max": filter_row.price_max,
            "keywords": filter_row.keywords,
        }
        return user.id, current_filter


def _apply_filter_change_sync(user_id: int, result: dict) -> None:
    with get_session() as session:
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user_id))
        if filter_row is None:
            return
        for key in ("deal_type", "cities", "keywords"):
            if key in result:
                setattr(filter_row, key, result[key])
        # safe_range_update refuses to write an inverted min>max range — Gemini decides both
        # sides here from freeform text, not a structured menu, so there's no re-prompt available
        # to catch a garbled range before it's saved (see that function's own docstring; found
        # live 2026-09-07 — an inverted range hard-fails every listing forever, silently).
        if "rooms_min" in result or "rooms_max" in result:
            filter_row.rooms_min, filter_row.rooms_max = safe_range_update(
                filter_row.rooms_min, filter_row.rooms_max,
                result.get("rooms_min"), result.get("rooms_max"),
            )
        if "price_min" in result or "price_max" in result:
            price_min = result.get("price_min")
            price_max = result.get("price_max")
            filter_row.price_min, filter_row.price_max = safe_range_update(
                filter_row.price_min, filter_row.price_max,
                int(price_min) if price_min is not None else None,
                int(price_max) if price_max is not None else None,
            )
        session.commit()


async def handle_stray_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""

    if looks_like_help_request(text):
        await escalate_to_owner(update, context, text)
        await update.message.reply_text(
            "תודה שכתבת! ההודעה שלך התקבלה ואנחנו נחזור אליך בהקדם 🙏\n\n"
            "לחיפוש דירות: /start"
        )
        return

    user_id, current_filter = await asyncio.to_thread(_load_filter_sync, update.effective_user)
    if current_filter is not None:
        result = await asyncio.to_thread(
            gemini_client.chat_with_existing_user,
            text,
            current_filter,
            cities.CITIES,
            update.effective_user.first_name,
        )
        if result is None:
            await update.message.reply_text(
                "מצטער, יש לי תקלה טכנית רגעית 😅 נסה/י לשלוח שוב בעוד רגע."
            )
            return
        if result.get("filter_changed"):
            await asyncio.to_thread(_apply_filter_change_sync, user_id, result)
        await update.message.reply_text(result.get("response_message") or "בסדר! 🙂")
        return

    await update.message.reply_text(
        "היי! 🐶 אני טודירה, בוט חיפוש הדירות. כדי להתחיל לחפש דירה, שלח/י /start."
    )


def build_contact_fallback_handler() -> MessageHandler:
    return MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, handle_stray_message)
