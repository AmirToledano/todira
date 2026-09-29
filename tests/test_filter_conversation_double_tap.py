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
from handlers.filter_conversation import (
    MENU,
    _clear_previous_menu_keyboard,
    _default_draft,
    _show_category,
)


def test_show_category_swallows_message_not_modified():
    query = SimpleNamespace(
        edit_message_text=AsyncMock(
            side_effect=BadRequest("Message is not modified: specified new message content...")
        )
    )
    context = SimpleNamespace(user_data={})
    draft = _default_draft()

    result = asyncio.run(_show_category(query, context, draft, "root", "he"))

    assert result == MENU  # returns normally, no exception propagated


def test_show_category_still_raises_a_real_badrequest():
    query = SimpleNamespace(
        edit_message_text=AsyncMock(side_effect=BadRequest("Chat not found"))
    )
    context = SimpleNamespace(user_data={})
    draft = _default_draft()

    with pytest.raises(BadRequest):
        asyncio.run(_show_category(query, context, draft, "root", "he"))


def test_clear_previous_menu_keyboard_is_a_noop_when_nothing_tracked_yet():
    context = SimpleNamespace(user_data={}, bot=SimpleNamespace(edit_message_reply_markup=AsyncMock()))

    asyncio.run(_clear_previous_menu_keyboard(context, 999))

    context.bot.edit_message_reply_markup.assert_not_awaited()


def test_clear_previous_menu_keyboard_swallows_a_failed_edit():
    # Best-effort cosmetic cleanup — an already-cleared/too-old/deleted message must never raise
    # and interrupt the real flow that's trying to send its own next message.
    context = SimpleNamespace(
        user_data={"menu_message_id": 111},
        bot=SimpleNamespace(
            edit_message_reply_markup=AsyncMock(side_effect=BadRequest("Message to edit not found"))
        ),
    )

    asyncio.run(_clear_previous_menu_keyboard(context, 999))  # must not raise

    context.bot.edit_message_reply_markup.assert_awaited_once_with(
        chat_id=999, message_id=111, reply_markup=None
    )


def test_menu_callback_cancel_clears_the_old_keyboard_explicitly():
    # 2026-09-28 real bug fix — editMessageText treats an omitted reply_markup as "leave
    # unchanged" (python-telegram-bot's Bot._post drops None-valued params before the request),
    # so without passing reply_markup=None explicitly here the root menu's own category/Save/
    # Cancel keyboard stayed live and tappable under the "cancelled" text even after the
    # conversation had already ended — tapping any button then just spun forever with no response.
    draft = _default_draft()
    query = SimpleNamespace(
        data="f:cancel",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={"draft": draft, "awaiting": None})

    result = asyncio.run(filter_conversation.menu_callback(update, context))

    assert result == filter_conversation.ConversationHandler.END
    query.edit_message_text.assert_awaited_once()
    assert query.edit_message_text.await_args.kwargs.get("reply_markup") is None
    assert "draft" not in context.user_data


def test_handle_save_success_clears_the_old_keyboard_explicitly(monkeypatch):
    # Same real bug/fix as the cancel case above, on _handle_save's own success-path edit.
    monkeypatch.setattr(filter_conversation, "_save_and_match_sync", lambda *a, **k: 0)
    draft = _default_draft()
    user = SimpleNamespace(id=555)
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(edit_message_text=AsyncMock(), message=message)
    update = SimpleNamespace(callback_query=query, effective_user=user)
    context = SimpleNamespace(user_data={"draft": draft})

    result = asyncio.run(filter_conversation._handle_save(update, context, draft))

    assert result == filter_conversation.ConversationHandler.END
    query.edit_message_text.assert_awaited_once()
    assert query.edit_message_text.await_args.kwargs.get("reply_markup") is None


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
