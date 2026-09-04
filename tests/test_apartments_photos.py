"""Tests for bot/handlers/apartments.py's /apartments command — specifically that each match is
sent via the shared send_listing_card helper (dorin_common/cards.py, added 2026-09-02 for real
Yad2 photos), not the old plain reply_text(caption, reply_markup=...) path it replaced.
"""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.apartments as apartments_module


def _make_update():
    user = SimpleNamespace(id=555)
    chat = SimpleNamespace(id=555)
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(effective_user=user, effective_chat=chat, message=message)


def _make_context():
    return SimpleNamespace(bot=SimpleNamespace())


def test_no_filter_tells_user_to_set_one_up():
    update = _make_update()
    context = _make_context()
    with patch.object(apartments_module, "_load_matches_sync", return_value=None):
        asyncio.run(apartments_module.apartments(update, context))
    update.message.reply_text.assert_awaited_once()
    assert "/filter" in update.message.reply_text.await_args.args[0]


def test_no_matches_tells_user_none_found_currently():
    update = _make_update()
    context = _make_context()
    with patch.object(apartments_module, "_load_matches_sync", return_value=(True, [])):
        asyncio.run(apartments_module.apartments(update, context))
    update.message.reply_text.assert_awaited_once()


def test_each_match_sent_via_send_listing_card_not_plain_reply_text():
    update = _make_update()
    context = _make_context()
    listing_a = SimpleNamespace(id=1)
    listing_b = SimpleNamespace(id=2)

    with patch.object(
        apartments_module, "_load_matches_sync", return_value=(True, [listing_a, listing_b])
    ), patch.object(
        apartments_module, "send_listing_card", AsyncMock()
    ) as mock_send, patch.object(
        apartments_module,
        "format_caption",
        side_effect=lambda listing, **kw: f"caption-{listing.id}",
    ):
        asyncio.run(apartments_module.apartments(update, context))

    assert mock_send.await_count == 2
    mock_send.assert_any_await(context.bot, 555, listing_a, "caption-1")
    mock_send.assert_any_await(context.bot, 555, listing_b, "caption-2")
    update.message.reply_text.assert_not_awaited()
