"""Tests for the quick-pick numeric picker (price/rooms/floor min & max) and the ForceReply-based
"custom value" fallback, added 2026-09-15 for a real owner complaint: tapping a min/max field used
to edit the existing inline-keyboard message with a plain text prompt, and Telegram's
editMessageText can only attach an InlineKeyboardMarkup to a message, never a ForceReply — so the
device keyboard never opened on its own, and typing every value by hand was slow. Presets now cover
the common case with zero typing; "✏️ ערך אחר..." falls back to a freshly SENT message with a
ForceReply, the one reply_markup type Telegram will auto-open the keyboard for.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram import ForceReply

import keyboards as kb
import handlers.filter_conversation as filter_conversation
from handlers.filter_conversation import AWAIT_TEXT, MENU, _default_draft


def _make_context(draft: dict | None = None):
    return SimpleNamespace(
        user_data={"draft": draft or _default_draft()},
        bot=SimpleNamespace(send_message=AsyncMock()),
    )


def _make_query(data: str):
    return SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        message=SimpleNamespace(chat_id=999),
    )


def test_numeric_preset_keyboard_marks_current_value():
    markup = kb.numeric_preset_keyboard("price_min", 2000, "price", "he")
    buttons = [b for row in markup.inline_keyboard for b in row]
    picked = next(b for b in buttons if b.callback_data == "f:pick:price_min:2")
    assert picked.text.startswith("✅")


def test_numeric_preset_keyboard_omits_clear_button_when_unset():
    markup = kb.numeric_preset_keyboard("price_min", None, "price", "he")
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert not any(b.callback_data == "f:pick:price_min:clear" for b in buttons)


def test_numeric_preset_keyboard_shows_clear_button_when_set():
    markup = kb.numeric_preset_keyboard("price_min", 2000, "price", "he")
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert any(b.callback_data == "f:pick:price_min:clear" for b in buttons)


def test_numeric_preset_keyboard_has_custom_and_back_buttons():
    markup = kb.numeric_preset_keyboard("rooms_max", None, "rooms", "he")
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert any(b.callback_data == "f:pick:rooms_max:custom" for b in buttons)
    assert any(b.callback_data == "f:cat:rooms" for b in buttons)


def test_menu_callback_price_min_shows_numeric_picker_not_text_prompt():
    query = _make_query("f:price:min")
    update = SimpleNamespace(callback_query=query)
    context = _make_context()

    result = asyncio.run(filter_conversation.menu_callback(update, context))

    assert result == MENU
    query.edit_message_text.assert_awaited_once()
    _, kwargs = query.edit_message_text.call_args
    assert kwargs["reply_markup"].inline_keyboard  # the picker grid, not a plain text prompt
    assert "awaiting" not in context.user_data  # no text-input state entered yet


def test_menu_callback_pick_sets_preset_value_and_returns_to_price_category():
    query = _make_query("f:pick:price_min:2")  # index 2 -> 2000, see kb.NUMERIC_PRESETS
    update = SimpleNamespace(callback_query=query)
    context = _make_context()

    result = asyncio.run(filter_conversation.menu_callback(update, context))

    assert result == MENU
    assert context.user_data["draft"]["price_min"] == kb.NUMERIC_PRESETS["price_min"][2]
    # back on the price category screen (has the min/max buttons), not the picker
    _, kwargs = query.edit_message_text.call_args
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert any(b.callback_data == "f:price:min" for b in buttons)


def test_menu_callback_pick_clear_resets_field_to_none():
    draft = _default_draft()
    draft["floor_max"] = 5
    query = _make_query("f:pick:floor_max:clear")
    update = SimpleNamespace(callback_query=query)
    context = _make_context(draft=draft)

    result = asyncio.run(filter_conversation.menu_callback(update, context))

    assert result == MENU
    assert context.user_data["draft"]["floor_max"] is None


def test_menu_callback_pick_custom_sends_force_reply_and_clears_old_keyboard():
    query = _make_query("f:pick:rooms_min:custom")
    update = SimpleNamespace(callback_query=query)
    context = _make_context()

    result = asyncio.run(filter_conversation.menu_callback(update, context))

    assert result == AWAIT_TEXT
    assert context.user_data["awaiting"] == "rooms_min"
    # old inline keyboard removed so a stray tap during AWAIT_TEXT can't go anywhere
    query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
    # a NEW message was sent (not an edit) carrying a ForceReply, the only way to auto-open the
    # device keyboard
    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert kwargs["chat_id"] == 999
    assert isinstance(kwargs["reply_markup"], ForceReply)


def test_menu_callback_loc_addcity_also_uses_force_reply():
    # part of the same fix's scope: every remaining typed-value prompt (city search, keywords,
    # area, move-in dates), not just the numeric picker's custom fallback.
    query = _make_query("f:loc:addcity")
    update = SimpleNamespace(callback_query=query)
    context = _make_context()

    result = asyncio.run(filter_conversation.menu_callback(update, context))

    assert result == AWAIT_TEXT
    assert context.user_data["awaiting"] == "city"
    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert isinstance(kwargs["reply_markup"], ForceReply)
