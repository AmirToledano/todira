"""Counts each private message and button press (todira_common/activity.py, 2026-10-21) - never its text."""
from __future__ import annotations

import asyncio
import re

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes, TypeHandler

from todira_common import activity

_FROM_SITE = re.compile(r"^/start\s+(site_[a-z]{1,20})$")


async def count_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat, user = update.effective_chat, update.effective_user
    if user is None or chat is None or chat.type != ChatType.PRIVATE:
        return
    kind = activity.BOT_BUTTON if update.callback_query is not None else activity.BOT_MESSAGE
    if kind == activity.BOT_MESSAGE and update.message is None:
        return
    await asyncio.to_thread(activity.record, kind, f"t{user.id}")
    # 2026-10-22: the site's bot buttons open t.me/<bot>?start=site_<where> - count who really arrived, and from where
    text = (update.message.text or "") if update.message is not None else ""
    match = _FROM_SITE.match(text)
    if match:
        await asyncio.to_thread(activity.record, f"bot_start_{match.group(1)}", f"t{user.id}")


def build_activity_handler() -> tuple[TypeHandler, int]:
    """(handler, group): runs before every other handler and never stops the update from reaching them."""
    return TypeHandler(Update, count_activity), -3
