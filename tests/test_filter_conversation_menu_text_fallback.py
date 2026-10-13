"""Tests for filter_conversation.py's menu_text_fallback — before this existed, MENU only had a
CallbackQueryHandler for the inline buttons, so a user who typed plain text while the /filter menu
was open (instead of tapping a button) matched nothing in the ConversationHandler's states dict at
all: total silence, no reply. Found live 2026-09-07 auditing the conversation's own state wiring.
"""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.filter_conversation as filter_conversation


def _make_update(text: str):
    user = SimpleNamespace(id=555, first_name="Amir", username="amirt")
    message = SimpleNamespace(
        text=text, chat_id=555, reply_text=AsyncMock(return_value=SimpleNamespace(message_id=42))
    )
    return SimpleNamespace(effective_user=user, message=message)


def _make_context():
    return SimpleNamespace(
        user_data={}, bot=SimpleNamespace(send_message=AsyncMock(), edit_message_reply_markup=AsyncMock())
    )


def test_ordinary_stray_text_gets_a_helpful_nudge_not_silence():
    update = _make_update("תל אביב")
    context = _make_context()

    with patch.object(filter_conversation, "escalate_to_owner", AsyncMock()) as mock_escalate:
        result = asyncio.run(filter_conversation.menu_text_fallback(update, context))

    mock_escalate.assert_not_called()
    # 2026-10-13: the city is written into the draft and the menu is sent again right below (note + menu).
    assert update.message.reply_text.await_count == 2
    assert context.user_data["draft"]["cities"] == ["תל אביב יפו"]
    assert context.user_data["menu_message_id"] == 42
    assert result == filter_conversation.MENU


def test_a_typed_search_updates_the_draft_and_resends_the_buttons_below():
    # the owner's own message from the report
    update = _make_update("דירה 3.5 חדרים עד 8 אלף עם מרפסת")
    context = _make_context()
    context.user_data["draft"] = filter_conversation._default_draft()

    result = asyncio.run(filter_conversation.menu_text_fallback(update, context))

    draft = context.user_data["draft"]
    assert (draft["rooms_min"], draft["rooms_max"], draft["price_max"]) == (3.5, 3.5, 8000)
    assert draft["require_balcony"] is True
    note, menu = update.message.reply_text.await_args_list
    assert note.args[0].startswith("עדכנתי בחיפוש: 3.5 חדרים · עד ₪8,000 · מרפסת")
    assert menu.kwargs["reply_markup"] is not None  # the buttons, right under the user's message
    assert result == filter_conversation.MENU
    filter_conversation.FilterData(**draft)  # still a valid filter to save


def test_text_with_nothing_to_read_still_brings_the_buttons_back_below():
    update = _make_update("איפה הכפתורים")
    context = _make_context()
    asyncio.run(filter_conversation.menu_text_fallback(update, context))
    note, menu = update.message.reply_text.await_args_list
    assert note.args[0] == filter_conversation.bot_text("filter.use_buttons_below", "he")
    assert menu.kwargs["reply_markup"] is not None


def test_help_request_while_menu_open_still_escalates():
    update = _make_update("אני צריך תמיכה טכנית בבקשה")
    context = _make_context()

    with patch.object(filter_conversation, "escalate_to_owner", AsyncMock(return_value=True)) as mock_escalate:
        result = asyncio.run(filter_conversation.menu_text_fallback(update, context))

    mock_escalate.assert_awaited_once()
    update.message.reply_text.assert_awaited_once()
    assert result == filter_conversation.MENU
