"""The "fewer messages like this" button under the occasional messages (scraper/nudges.py, 2026-11-08): after it, none
of those messages is sent to this person again. Alerts about flats are not affected."""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, ContextTypes
from todira_common import activity
from todira_common.app_flags import get_flag, set_flag
from todira_common.bot_strings import bot_text
from todira_common.db import get_session
from todira_common.language import DEFAULT_LANG
from todira_common.models import User

logger = logging.getLogger(__name__)

NUDGES_FLAG = "nudges_state"  # the same app_flags key scraper/nudges.py keeps its state in


def _turn_off_sync(telegram_user_id: int) -> str:
    import json

    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
        if user is None:
            return DEFAULT_LANG
        state = json.loads(get_flag(session, NUDGES_FLAG) or "{}")
        state.setdefault(str(user.id), {})["off"] = True
        set_flag(session, NUDGES_FLAG, json.dumps(state))
        return user.language or DEFAULT_LANG


async def _answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    lang = await asyncio.to_thread(_turn_off_sync, update.effective_user.id)
    await asyncio.to_thread(activity.record, "nudge_off", f"t{update.effective_user.id}")
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass
    await query.answer(bot_text("nudge.less_done", lang), show_alert=True)


def build_nudges_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(_answer, pattern=r"^ng:off$")
