"""Tests for onboarding.py's _cancel_for_other_command fallback — a real bug fix (2026-09-25).

A user mid-onboarding (AWAIT_FREETEXT) who ran /filter instead of finishing the free-text flow
used to get silently stuck: /filter isn't in onboarding's own ConversationHandler states/fallbacks,
so PTB correctly fell through and let filter_conversation.py's own handler start for that one
command — but onboarding's own per-user conversation state was never cleared, since it never
"handled" that update. Every later plain-text message still matched AWAIT_FREETEXT's own catch-all
MessageHandler (checked first in bot/main.py's registration order), silently routing anything the
user typed into /filter's own prompts into Gemini as onboarding free text instead.

See onboarding.py's own build_onboarding_handler for the real fix: /filter (and the other real bot
commands) are now registered as fallbacks whose callback cleanly ends onboarding's own state.
"""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.onboarding as onboarding


def _make_update():
    user = SimpleNamespace(id=555, first_name="Amir", username="amirt")
    chat = SimpleNamespace(id=555)
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(effective_user=user, effective_chat=chat, message=message)


def test_other_command_ends_onboarding_and_clears_dangling_state():
    update = _make_update()
    context = SimpleNamespace(user_data={"onboarding": dict(onboarding._EMPTY_STATE)})

    result = asyncio.run(onboarding._cancel_for_other_command(update, context))

    assert result == onboarding.ConversationHandler.END
    assert "onboarding" not in context.user_data
    update.message.reply_text.assert_awaited_once()


def test_other_command_fallback_is_registered_for_every_real_bot_command():
    handler = onboarding.build_onboarding_handler()
    fallback_commands: set[str] = set()
    for fb in handler.fallbacks:
        fallback_commands.update(fb.commands)

    for cmd in ("start", "filter", "setfilter", "apartments", "liked", "hidden", "profile"):
        assert cmd in fallback_commands, f"/{cmd} must end onboarding's dangling state, not get swallowed"
