"""/start — register a new user, reactivate + refresh a returning one, or — when reached via a
`t.me/<bot>?start=ref_xxxxxx` deep link generated on the website's /account page — link this
Telegram account to that SAME existing user instead of creating a separate one. See
dorin_common/channel_link.py for the code itself and website/whatsapp_webhook.py for the WhatsApp
side of the same feature.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from dorin_common.channel_link import resolve_link_code
from dorin_common.db import get_session
from dorin_common.models import User

logger = logging.getLogger(__name__)

WELCOME = (
    "✨ 🏠 היי {name}! אני בוט חיפוש דירות אישי — סורק את שוק הדירות ומודיע לך כשמופיעה דירה "
    "שמתאימה לסינון שלך.\n\n"
    "פקודות:\n"
    "/filter — הגדרת/עדכון הסינון שלך\n"
    "/apartments — הדירות התואמות האחרונות\n"
    "/liked — הדירות ששמרת\n"
    "/profile — הפרופיל וההגדרות שלך"
)

LINKED = "🎉 חיברתי! אתה כבר רשום ומעודכן אצלי במערכת — מעכשיו תקבל עדכונים גם כאן בטלגרם."

LINK_CONFLICT = (
    "לחשבון הטלגרם הזה כבר יש חשבון נפרד אצלי, אז אי אפשר לחבר אותו לחשבון אחר. "
    "אם זו טעות, כתוב/י לנו דרך /contact."
)


def _upsert_or_link_user_sync(tg_user, link_code: str | None) -> str:
    """Returns "linked", "conflict", or "normal" — start() picks the reply off this."""
    with get_session() as session:
        if link_code:
            code_user = resolve_link_code(session, link_code)
            if code_user is not None:
                existing = session.scalar(
                    select(User).where(User.telegram_user_id == tg_user.id)
                )
                if existing is not None and existing.id != code_user.id:
                    # This Telegram account already has its OWN separate account — linking it to
                    # a second one would mean merging two rows' filters/history, which we don't
                    # do automatically. Leave both accounts exactly as they were.
                    return "conflict"
                code_user.telegram_user_id = tg_user.id
                code_user.telegram_username = tg_user.username
                code_user.first_name = code_user.first_name or tg_user.first_name
                code_user.is_active = True
                session.commit()
                return "linked"
            # Unknown/expired code — fall through to the normal /start handling below rather
            # than erroring, since a plain "/start" with no payload hits this same path with
            # link_code=None every time.

        user = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
        if user is None:
            user = User(
                telegram_user_id=tg_user.id,
                telegram_username=tg_user.username,
                first_name=tg_user.first_name,
            )
            session.add(user)
        else:
            # reactivate — mirrors the reference bot re-engaging a paused/"found apartment" user
            user.is_active = True
            user.telegram_username = tg_user.username
            user.first_name = tg_user.first_name
        session.commit()
        return "normal"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    link_code = context.args[0] if context.args else None
    logger.info(
        "/start invoked by telegram_user_id=%s (link_code=%s)", tg_user.id, bool(link_code)
    )
    # asyncio.to_thread so a slow/blocking DB round-trip doesn't freeze the whole bot - PTB
    # processes updates one at a time by default (max_concurrent_updates=1, see main.py), so a
    # synchronous DB call made directly on the event loop blocks every OTHER user's button press
    # and command for its entire duration, not just this one. See PROJECT_STATE.md's 2026-08-31
    # "bot-wide blocking DB calls" entry for the investigation that found this.
    outcome = await asyncio.to_thread(_upsert_or_link_user_sync, tg_user, link_code)
    if outcome == "linked":
        await update.message.reply_text(LINKED)
    elif outcome == "conflict":
        await update.message.reply_text(LINK_CONFLICT)
    else:
        await update.message.reply_text(WELCOME.format(name=tg_user.first_name or ""))
