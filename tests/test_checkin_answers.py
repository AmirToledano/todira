"""2026-10-31: the four answers to the morning "is the search still right?" message."""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import checkin as scraper_checkin  # noqa: E402
from handlers import checkin, filter_conversation  # noqa: E402

from todira_common.bot_strings import bot_text  # noqa: E402


def _update(data):
    query = SimpleNamespace(data=data, answer=AsyncMock(), edit_message_reply_markup=AsyncMock(), message=SimpleNamespace())
    return SimpleNamespace(
        callback_query=query, effective_user=SimpleNamespace(id=555), effective_chat=SimpleNamespace(id=555), message=None
    )


def test_the_approved_wording_and_buttons():
    assert bot_text("checkin.text", "he", days=3, count=27) == (
        "היי 👋 ב־3 הימים האחרונים שלחתי לך 27 דירות. החיפוש עדיין מתאים לך?"
    )
    rows = scraper_checkin.checkin_markup("he").inline_keyboard
    assert [(row[0].text, row[0].callback_data) for row in rows] == [
        ("✅ כן, הכל טוב", "ci:ok"), ("✏️ לשנות חיפוש", "ci:edit"), ("⏸️ להשהות", "ci:pause"), ("🎉 מצאתי דירה", "ci:found"),
    ]


def test_yes_changes_nothing():
    update = _update("ci:ok")
    with patch.object(checkin, "_pause_sync") as pause:
        asyncio.run(checkin._answer(update, SimpleNamespace(bot=None)))
    pause.assert_not_called()
    update.callback_query.answer.assert_awaited_once_with("👍")
    update.callback_query.edit_message_reply_markup.assert_awaited_once()


def test_pause_pauses_and_asks_whether_they_found_one():
    update = _update("ci:pause")
    with (
        patch.object(checkin, "_pause_sync", return_value=(7, "he")),
        patch.object(checkin, "ask_found", AsyncMock()) as ask,
    ):
        asyncio.run(checkin._answer(update, SimpleNamespace(bot="bot")))
    update.callback_query.answer.assert_awaited_once_with(bot_text("checkin.paused", "he"), show_alert=True)
    ask.assert_awaited_once_with("bot", 555, 7, "he")


def test_found_pauses_and_asks_for_a_few_words():
    update = _update("ci:found")
    with (
        patch.object(checkin, "_pause_sync", return_value=(7, "he")),
        patch.object(checkin, "ask_for_testimonial", AsyncMock()) as ask,
    ):
        asyncio.run(checkin._answer(update, SimpleNamespace(bot="bot")))
    update.callback_query.answer.assert_awaited_once_with(bot_text("liked.found_paused", "he"), show_alert=True)
    ask.assert_awaited_once()


def test_change_the_search_opens_the_filter_menu():
    update = _update("ci:edit")
    with patch.object(filter_conversation, "filter_start", AsyncMock(return_value="MENU")) as start:
        result = asyncio.run(filter_conversation._filter_start_from_checkin(update, SimpleNamespace()))
    assert result == "MENU"
    start.assert_awaited_once()
    update.callback_query.edit_message_reply_markup.assert_awaited_once()
