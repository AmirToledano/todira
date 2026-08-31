"""/start — register a new user, or reactivate + refresh a returning one."""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

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


def _upsert_user_sync(tg_user) -> None:
    with get_session() as session:
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    logger.info("/start invoked by telegram_user_id=%s", tg_user.id)
    # asyncio.to_thread so a slow/blocking DB round-trip doesn't freeze the whole bot - PTB
    # processes updates one at a time by default (max_concurrent_updates=1, see main.py), so a
    # synchronous DB call made directly on the event loop blocks every OTHER user's button press
    # and command for its entire duration, not just this one. See PROJECT_STATE.md's 2026-08-31
    # "bot-wide blocking DB calls" entry for the investigation that found this.
    await asyncio.to_thread(_upsert_user_sync, tg_user)
    await update.message.reply_text(WELCOME.format(name=tg_user.first_name or ""))
