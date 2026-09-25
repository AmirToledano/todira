"""Tests for _show_category's real bug fix (2026-09-25): a completely harmless double-tap (tapping
"נקה" on an already-empty keywords/dates list, or double-tapping any category-open button before
the first tap's own re-render lands) re-renders byte-for-byte identical title/markup. Telegram's
own API rejects that specific edit with "Bad Request: message is not modified", which used to
bubble up uncaught to bot/main.py's catch-all _error_handler, showing the user a scary
"😅 קרתה תקלה טכנית" for a no-op that isn't a real error at all.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest

import handlers.filter_conversation as filter_conversation
from handlers.filter_conversation import MENU, _default_draft, _show_category


def test_show_category_swallows_message_not_modified():
    query = SimpleNamespace(
        edit_message_text=AsyncMock(
            side_effect=BadRequest("Message is not modified: specified new message content...")
        )
    )
    draft = _default_draft()

    result = asyncio.run(_show_category(query, draft, "root"))

    assert result == MENU  # returns normally, no exception propagated


def test_show_category_still_raises_a_real_badrequest():
    query = SimpleNamespace(
        edit_message_text=AsyncMock(side_effect=BadRequest("Chat not found"))
    )
    draft = _default_draft()

    with pytest.raises(BadRequest):
        asyncio.run(_show_category(query, draft, "root"))


def test_menu_callback_clear_keywords_twice_never_raises():
    """The exact real report this fixes: tapping "נקה" on an already-empty keywords list a second
    time used to surface a scary error message for a completely harmless no-op."""
    draft = _default_draft()
    draft["keywords"] = []

    query = SimpleNamespace(
        data="f:kw:clear",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(
            side_effect=BadRequest("Message is not modified: specified new message content...")
        ),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={"draft": draft, "awaiting": None})

    result = asyncio.run(filter_conversation.menu_callback(update, context))

    assert result == MENU
    assert draft["keywords"] == []
