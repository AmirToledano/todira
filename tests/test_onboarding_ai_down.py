"""2026-10-13 owner report: a brand-new user sent /start, described the search, and only ever got "technical hiccup".
The free-text reader (Gemini) was out of prepaid credit (HTTP 402 on every model), and onboarding stayed in
AWAIT_FREETEXT, so every later message hit the same failing call. Now a failed read ends onboarding and points to
/filter (the button-driven setup, no AI)."""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.onboarding as onboarding
from telegram.ext import ConversationHandler
from todira_common.bot_strings import bot_text


def test_a_failed_ai_read_ends_onboarding_and_points_to_filter():
    message = SimpleNamespace(text="מחפש שכירות בתל אביב עד 7000", reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=555, first_name="A", username=None),
        effective_chat=SimpleNamespace(id=555),
        message=message,
    )
    context = SimpleNamespace(
        user_data={"onboarding_lang": "he", "onboarding": dict(onboarding._EMPTY_STATE)},
        bot=SimpleNamespace(send_chat_action=AsyncMock(), send_message=AsyncMock()),
    )

    with patch.object(onboarding.gemini_client, "parse_onboarding_message", return_value=None):
        result = asyncio.run(onboarding._handle_freetext(update, context))

    assert result == ConversationHandler.END
    assert "onboarding" not in context.user_data
    sent = [c.args[0] for c in message.reply_text.await_args_list]
    assert sent[-1] == bot_text("onboarding.error", "he") and "/filter" in sent[-1]


def test_the_ai_down_message_points_to_filter_in_every_language():
    for lang in ("he", "en", "ru", "fr", "ar"):
        assert "/filter" in bot_text("onboarding.error", lang)
