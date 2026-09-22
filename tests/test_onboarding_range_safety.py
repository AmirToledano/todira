"""Tests for onboarding.py's use of safe_range_update on rooms/price across multi-turn merges.

Found live-code-review 2026-09-22: _handle_freetext used to merge each Gemini-extracted field
independently, with no cross-field validation — unlike filter_conversation.py (Pydantic) and
contact_fallback.py/whatsapp_webhook.py (safe_range_update), which both already guard the
identical Gemini-driven merge. A multi-turn onboarding conversation ("up to 3000" then later
"actually not less than 5000") could merge into price_min=5000, price_max=3000 with nothing
catching it before _save_filter_sync ever wrote it — an inverted range that hard-fails every
listing forever, indistinguishable from "no current matches".
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
        bot=SimpleNamespace(send_chat_action=AsyncMock(), send_message=AsyncMock()),
    )


def _base_result(**overrides) -> dict:
    result = {
        "deal_type": None,
        "cities": [],
        "missing_required": ["deal_type", "cities"],
        "response_message": "רשמתי!",
        "needs_human_help": False,
    }
    result.update(overrides)
    return result


def test_a_later_turn_proposing_an_inverted_price_range_is_refused():
    update = _make_update("עד 3000 בבקשה")
    context = _make_context()

    turn_1 = _base_result(price_max=3000)
    with patch.object(onboarding.gemini_client, "parse_onboarding_message", return_value=turn_1):
        asyncio.run(onboarding._handle_freetext(update, context))

    state = context.user_data["onboarding"]
    assert state["price_min"] is None
    assert state["price_max"] == 3000

    # Second turn: "actually not less than 5000" - proposes ONLY price_min, which combined with
    # the already-accumulated price_max=3000 would be an inverted (min > max) range.
    turn_2 = _base_result(price_min=5000)
    with patch.object(onboarding.gemini_client, "parse_onboarding_message", return_value=turn_2):
        asyncio.run(onboarding._handle_freetext(update, context))

    # Refused entirely - the state must stay exactly as it was before this turn's proposal,
    # never a silently-inverted price_min=5000/price_max=3000.
    assert state["price_min"] is None
    assert state["price_max"] == 3000


def test_a_later_turn_proposing_a_coherent_price_range_is_applied():
    update = _make_update("עד 3000 בבקשה")
    context = _make_context()

    turn_1 = _base_result(price_max=3000)
    with patch.object(onboarding.gemini_client, "parse_onboarding_message", return_value=turn_1):
        asyncio.run(onboarding._handle_freetext(update, context))

    turn_2 = _base_result(price_min=1000)  # coherent: 1000 <= 3000
    with patch.object(onboarding.gemini_client, "parse_onboarding_message", return_value=turn_2):
        asyncio.run(onboarding._handle_freetext(update, context))

    state = context.user_data["onboarding"]
    assert state["price_min"] == 1000
    assert state["price_max"] == 3000


def test_a_later_turn_proposing_an_inverted_rooms_range_is_refused():
    update = _make_update("לפחות 4 חדרים")
    context = _make_context()

    turn_1 = _base_result(rooms_min=4)
    with patch.object(onboarding.gemini_client, "parse_onboarding_message", return_value=turn_1):
        asyncio.run(onboarding._handle_freetext(update, context))

    turn_2 = _base_result(rooms_max=2)  # inverted against the already-accumulated rooms_min=4
    with patch.object(onboarding.gemini_client, "parse_onboarding_message", return_value=turn_2):
        asyncio.run(onboarding._handle_freetext(update, context))

    state = context.user_data["onboarding"]
    assert state["rooms_min"] == 4
    assert state["rooms_max"] is None
