"""Tests for filter_conversation.py's escape hatch when a value the menu asked for ("הקלד/י מחיר
מינימלי") fails to parse and looks like a real sentence rather than a bad number/date attempt — see
handlers/support.py's looks_like_a_sentence docstring and filter_conversation.py's
_reply_parse_failure_or_escalate for the real report this fixes (2026-09-01: a tester asked for
support mid-/filter and just got "לא הצלחתי לפרש מספר, נסה שוב" on repeat).
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


def _make_context(awaiting: str, draft: dict | None = None):
    return SimpleNamespace(
        user_data={"awaiting": awaiting, "draft": draft or filter_conversation._default_draft()},
        bot=SimpleNamespace(send_message=AsyncMock()),
    )


def test_sentence_at_a_numeric_prompt_escalates_and_keeps_waiting():
    update = _make_update("כמה זמן זה בדרך כלל לוקח")
    context = _make_context("price_min")

    with patch.object(filter_conversation, "escalate_to_owner", AsyncMock(return_value=True)) as mock_escalate:
        result = asyncio.run(filter_conversation.text_input(update, context))

    mock_escalate.assert_awaited_once()
    assert result == filter_conversation.AWAIT_TEXT
    assert context.user_data["awaiting"] == "price_min"  # still waiting for the same field
    update.message.reply_text.assert_awaited_once()


def test_single_token_typo_at_a_numeric_prompt_does_not_escalate():
    update = _make_update("abc")
    context = _make_context("price_min")

    with patch.object(filter_conversation, "escalate_to_owner", AsyncMock(return_value=True)) as mock_escalate:
        result = asyncio.run(filter_conversation.text_input(update, context))

    mock_escalate.assert_not_called()
    assert result == filter_conversation.AWAIT_TEXT
    assert context.user_data["awaiting"] == "price_min"
