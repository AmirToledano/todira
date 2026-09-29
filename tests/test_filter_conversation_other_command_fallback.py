"""Tests for filter_conversation.py's _cancel_for_other_command fallback — a real bug fix
(2026-09-28), found via a fresh code-review sweep across bot/ handlers.

Mirrors onboarding.py's own identical fix (test_onboarding_other_command_fallback.py, 2026-09-25)
for the exact same bug class: /filter's own ConversationHandler tracks its per-user state
(MENU/AWAIT_TEXT) independently of every other handler — python-telegram-bot's
ConversationHandler.check_update only re-enters via entry_points when the tracked state is None
(or allow_reentry is set). A user who left the /filter menu open mid-edit and then ran /apartments,
/liked, /hidden, /profile or /start got that OTHER command's own handler correctly, but this
conversation stayed parked in MENU/AWAIT_TEXT — so a later plain-text reply (meant for whatever
they did next) was silently swallowed by menu_text_fallback/text_input instead. Now these commands
are registered as fallbacks whose callback cleanly ends the dangling state.
"""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.filter_conversation as filter_conversation


def _make_update():
    user = SimpleNamespace(id=555, first_name="Amir", username="amirt")
    chat = SimpleNamespace(id=555)
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(effective_user=user, effective_chat=chat, message=message)


def test_other_command_ends_filter_conversation_and_clears_dangling_draft():
    update = _make_update()
    context = SimpleNamespace(user_data={"draft": {"cities": ["תל אביב"]}})

    result = asyncio.run(filter_conversation._cancel_for_other_command(update, context))

    assert result == filter_conversation.ConversationHandler.END
    assert "draft" not in context.user_data
    update.message.reply_text.assert_awaited_once()


def test_other_command_fallback_is_registered_for_every_real_bot_command():
    handler = filter_conversation.build_filter_conversation_handler()
    fallback_commands: set[str] = set()
    for fb in handler.fallbacks:
        fallback_commands.update(fb.commands)

    assert "cancel" in fallback_commands
    for cmd in ("start", "apartments", "liked", "hidden", "profile"):
        assert cmd in fallback_commands, f"/{cmd} must end filter's dangling state, not get swallowed"
