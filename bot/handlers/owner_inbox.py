"""The owner's inbox group (2026-10-20, owner: "send what people write to me somewhere else, the bot chat is muted
because of the apartment alerts").

When the owner adds the bot to a Telegram group, the bot remembers that group (todira_common/owner_inbox.py) and from
then on messages people send (the site's contact form and feedback, help requests in the bot) and payment alerts go
there; apartment alerts stay in his private chat with the bot. Added by anyone else, the bot leaves the group at once.
Removed from the inbox group, it forgets it and everything goes back to the private chat. Groups are only an inbox:
nothing posted in a group reaches the bot's other handlers.
"""
from __future__ import annotations

import asyncio
import logging
import os

from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, ChatMemberHandler, ContextTypes, MessageHandler, TypeHandler, filters
from todira_common import owner_inbox
from todira_common.db import get_session

logger = logging.getLogger(__name__)

_GROUPS = (ChatType.GROUP, ChatType.SUPERGROUP)
_IN = (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR)
_OUT = (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)

WELCOME = (
    "מעכשיו הפניות יגיעו לקבוצה הזו: הודעות מטופס צור קשר ומהמשוב באתר, בקשות עזרה מהבוט, והתראות על תשלומים.\n"
    "התראות על דירות ימשיכו להגיע בצ׳אט הפרטי עם הבוט."
)


def _owner_id() -> str:
    return os.environ.get("OWNER_TELEGRAM_USER_ID", "").strip()


def _save(chat_id: int | None) -> None:
    with get_session() as session:
        owner_inbox.set_inbox_chat_id(session, chat_id)


def _current() -> str | None:
    return owner_inbox.inbox_chat_id(fresh=True)


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    change = update.my_chat_member
    chat = change.chat
    if chat.type not in _GROUPS:
        return
    old, new = change.old_chat_member.status, change.new_chat_member.status
    if new in _IN:
        if not _owner_id() or str(change.from_user.id) != _owner_id():
            logger.info("Added to a group by someone who is not the owner - leaving it")
            try:
                await context.bot.leave_chat(chat.id)
            except TelegramError:
                logger.exception("Could not leave a group the owner did not add the bot to")
            return
        await asyncio.to_thread(_save, chat.id)
        if old in _OUT:
            await context.bot.send_message(chat_id=chat.id, text=WELCOME)
    elif new in _OUT and await asyncio.to_thread(_current) == str(chat.id):
        await asyncio.to_thread(_save, None)
        logger.info("Removed from the owner's inbox group - messages go to the private chat again")


async def on_group_upgraded(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A group turned into a supergroup gets a new id; follow it."""
    msg = update.effective_message
    if msg.migrate_to_chat_id:
        old, new = msg.chat.id, msg.migrate_to_chat_id
    else:
        old, new = msg.migrate_from_chat_id, msg.chat.id
    if await asyncio.to_thread(_current) == str(old):
        await asyncio.to_thread(_save, new)


async def ignore_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Nothing written in a group goes on to the bot's own conversations (onboarding, search, the catch-all reply)."""
    chat = update.effective_chat
    if chat is not None and chat.type != ChatType.PRIVATE and update.my_chat_member is None:
        raise ApplicationHandlerStop


def build_owner_inbox_handlers() -> list[tuple[object, int]]:
    """(handler, group) pairs: the upgrade follower runs first, then the group guard, before every other handler."""
    return [
        (MessageHandler(filters.StatusUpdate.MIGRATE, on_group_upgraded), -3),
        (TypeHandler(Update, ignore_groups), -2),
        (ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER), 0),
    ]
