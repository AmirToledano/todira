"""Tests for onboarding.py's use of gemini_client's needs_human_help field — Gemini already reads
every onboarding message semantically to extract search criteria, so this reuses that same call
to also recognize a support request phrased in any way (not just keyword matches), at no extra
API cost. See handlers/support.py's docstring and gemini_client.py's needs_human_help schema field
for the real report this fixes (2026-09-01).
"""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.onboarding as onboarding


def _make_update(text: str):
    user = SimpleNamespace(id=555, first_name="Amir", username="amirt")
    chat = SimpleNamespace(id=555)
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    return SimpleNamespace(effective_user=user, effective_chat=chat, message=message)


def _make_context():
    return SimpleNamespace(
        user_data={},
        bot=SimpleNamespace(
            send_chat_action=AsyncMock(), send_message=AsyncMock()
        ),
    )


def test_needs_human_help_escalates_and_skips_the_reprompt():
    update = _make_update("למה זה לוקח כל כך הרבה זמן")
    context = _make_context()

    gemini_result = {
        "deal_type": None,
        "cities": [],
        "missing_required": ["deal_type", "cities"],
        "response_message": "באיזו עיר ואיזה סוג עסקה?",  # would be the WRONG reply here
        "needs_human_help": True,
    }

    with patch.object(onboarding.gemini_client, "parse_onboarding_message", return_value=gemini_result), \
         patch.object(onboarding, "escalate_to_owner", AsyncMock(return_value=True)) as mock_escalate:
        result = asyncio.run(onboarding._handle_freetext(update, context))

    mock_escalate.assert_awaited_once()
    assert result == onboarding.AWAIT_FREETEXT
    # the wrong, off-topic Gemini reply must NOT have been sent
    sent_texts = [c.args[0] for c in update.message.reply_text.await_args_list]
    assert "באיזו עיר ואיזה סוג עסקה?" not in sent_texts


def test_normal_criteria_message_does_not_escalate():
    update = _make_update("מחפש שכירות בתל אביב")
    context = _make_context()

    gemini_result = {
        "deal_type": "rent",
        "cities": ["תל אביב"],
        "missing_required": [],
        "response_message": "מעולה, רשמתי!",
        "needs_human_help": False,
    }

    # asyncio.to_thread is used twice in this code path now (the Gemini call itself, then the
    # match-count DB lookup further down) — a real to_thread dispatching by function, not a single
    # canned return value, so each call gets the right result instead of the second call's stub
    # accidentally answering the first.
    async def fake_to_thread(func, *args, **kwargs):
        if func is onboarding.gemini_client.parse_onboarding_message:
            return gemini_result
        return (0, [], True)

    with patch.object(onboarding.gemini_client, "parse_onboarding_message", return_value=gemini_result), \
         patch.object(onboarding, "escalate_to_owner", AsyncMock(return_value=True)) as mock_escalate, \
         patch.object(onboarding.asyncio, "to_thread", fake_to_thread):
        asyncio.run(onboarding._handle_freetext(update, context))

    mock_escalate.assert_not_called()
