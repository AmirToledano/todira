"""2026-10-29 (code review): while /support waits for a message, another command is run instead of swallowed, and a
message long after /support goes to the normal handlers, not to the owner as a ticket."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import time
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.support as support  # noqa: E402
from telegram import Chat, Message, MessageEntity, Update, User  # noqa: E402
from telegram.ext import Application, CommandHandler, MessageHandler, filters  # noqa: E402


def _update(update_id: int, text: str) -> Update:
    entities = [MessageEntity(MessageEntity.BOT_COMMAND, 0, len(text.split()[0]))] if text.startswith("/") else None
    message = Message(update_id, dt.datetime.now(dt.timezone.utc), Chat(5, Chat.PRIVATE), from_user=User(5, "a", False),
                      text=text, entities=entities)
    return Update(update_id, message=message)


def _run(*texts: str, wait_started: float | None = None) -> tuple[list[str], AsyncMock]:
    seen: list[str] = []

    async def other(update, context):
        seen.append(update.message.text)

    async def main():
        app = Application.builder().token("1:test").build()
        handler = support.build_support_handler()
        handler._persistent = False  # the real bot keeps it in a pickle file; not needed here
        app.add_handler(handler)
        app._initialized = True  # initialize() would call Telegram; nothing here talks to it
        app.bot._bot_user = User(1, "bot", True, username="test_bot")
        app.bot._initialized = True
        app.add_handler(CommandHandler("filter", other))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, other))
        for n, text in enumerate(texts, start=1):
            update = _update(n, text)
            update.set_bot(app.bot)
            update.message.set_bot(app.bot)
            await app.process_update(update)
            await asyncio.sleep(0.05)
            if wait_started is not None and text == "/support":
                app.user_data[5]["support_at"] = wait_started

    escalate = AsyncMock()
    with (
        patch.object(support, "_lang_sync", lambda uid: "he"),
        patch.object(support, "escalate_to_owner", escalate),
        patch.object(Message, "reply_text", AsyncMock()),
    ):
        asyncio.run(main())
    return seen, escalate


def test_another_command_during_the_wait_runs():
    seen, escalate = _run("/support", "/filter")
    assert seen == ["/filter"]
    escalate.assert_not_awaited()


def test_a_message_right_after_support_is_the_ticket():
    seen, escalate = _run("/support", "יש לי בעיה")
    assert seen == []
    escalate.assert_awaited_once()


def test_a_message_long_after_support_goes_to_the_normal_handlers():
    seen, escalate = _run("/support", "3 חדרים בחיפה", wait_started=time.time() - support.SUPPORT_WAIT_SECONDS - 5)
    assert seen == ["3 חדרים בחיפה"]
    escalate.assert_not_awaited()
