"""Tests for bot/handlers/apartments.py's /apartments command.

2026-09-15: replaces the old test_apartments_photos.py, which tested that each match was sent as
its own Telegram card via send_listing_card. That whole behavior is gone — a real owner complaint
the same day: a broad filter (thousands of matches) flooded the chat with an arbitrary 10-card
subset (the old RESULT_LIMIT) and never told the user how many really matched. /apartments now
reports the true total match count and points at the website's own /apartments?uid=... view
instead of sending anything itself, the same fix direction filter_conversation._handle_save
already got earlier the same day.
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
    with patch.object(apartments_module, "_count_matches_sync", return_value=None):
        asyncio.run(apartments_module.apartments(update, context))
    update.message.reply_text.assert_awaited_once()
    assert "/filter" in update.message.reply_text.await_args.args[0]


def test_no_matches_tells_user_none_found_currently_and_still_links_the_website():
    update = _make_update()
    context = _make_context()
    with patch.object(apartments_module, "_count_matches_sync", return_value=0):
        asyncio.run(apartments_module.apartments(update, context))
    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.await_args.args[0]
    assert "לא נמצאו" in text
    assert "/apartments?uid=555" in text


def test_matches_sends_true_total_count_and_website_link_not_cards():
    # the real bug this fixes: a broad filter with e.g. 3794 matches must report 3794, not an
    # arbitrary capped subset, and must never call send_listing_card at all anymore.
    update = _make_update()
    context = _make_context()
    with patch.object(apartments_module, "_count_matches_sync", return_value=3794):
        asyncio.run(apartments_module.apartments(update, context))
    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.await_args.args[0]
    assert "3794" in text
    assert "/apartments?uid=555" in text


def test_count_matches_sync_returns_none_when_no_filter_saved(monkeypatch):
    class _FakeSession:
        def scalar(self, *_args, **_kwargs):
            return None  # no User row at all

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(apartments_module, "get_session", _FakeSession)
    tg_user = SimpleNamespace(id=555)

    assert apartments_module._count_matches_sync(tg_user) is None


def test_count_matches_sync_returns_true_uncapped_total(monkeypatch):
    fake_user = SimpleNamespace(id=1)
    fake_filter = SimpleNamespace(id=1)

    class _FakeSession:
        def __init__(self):
            self._calls = 0

        def scalar(self, *_args, **_kwargs):
            self._calls += 1
            return fake_user if self._calls == 1 else fake_filter

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(apartments_module, "get_session", _FakeSession)
    monkeypatch.setattr(
        apartments_module, "find_matching_listings", lambda *a, **kw: list(range(3794))
    )
    tg_user = SimpleNamespace(id=555)

    assert apartments_module._count_matches_sync(tg_user) == 3794
