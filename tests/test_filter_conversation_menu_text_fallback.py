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
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    return SimpleNamespace(effective_user=user, message=message)


def _make_context():
    return SimpleNamespace(user_data={}, bot=SimpleNamespace(send_message=AsyncMock()))


def test_ordinary_stray_text_gets_a_helpful_nudge_not_silence():
    update = _make_update("תל אביב")
    context = _make_context()

    with patch.object(filter_conversation, "escalate_to_owner", AsyncMock()) as mock_escalate:
        result = asyncio.run(filter_conversation.menu_text_fallback(update, context))

    mock_escalate.assert_not_called()
    update.message.reply_text.assert_awaited_once()
    assert result == filter_conversation.MENU


def test_help_request_while_menu_open_still_escalates():
    update = _make_update("אני צריך תמיכה טכנית בבקשה")
    context = _make_context()

    with patch.object(filter_conversation, "escalate_to_owner", AsyncMock(return_value=True)) as mock_escalate:
        result = asyncio.run(filter_conversation.menu_text_fallback(update, context))

    mock_escalate.assert_awaited_once()
    update.message.reply_text.assert_awaited_once()
    assert result == filter_conversation.MENU
