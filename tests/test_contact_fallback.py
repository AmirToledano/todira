"""Tests for bot/handlers/contact_fallback.py — the catch-all that replies to free text no other
handler claimed (see that module's own docstring for why this exists: a user following the
website's "כתוב/י ישירות לבוט" link got total silence before this, found 2026-09-01).

The actual save+notify logic lives in handlers/support.py (shared with onboarding.py and
filter_conversation.py, see that module's docstring) — contact_fallback.py just calls it and
replies, so these tests patch handlers.support's OWNER_TELEGRAM_USER_ID/get_session, not
contact_fallback's own (it no longer has copies of either).

Uses lightweight SimpleNamespace/AsyncMock stand-ins for the Update/Context objects rather than
full real python-telegram-bot objects — handle_stray_message only touches a handful of attributes
(update.effective_user, update.message.text/.reply_text, context.bot.send_message), all easy to
fake directly without needing a real Bot instance.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.contact_fallback as contact_fallback
import handlers.support as support
from telegram.error import TelegramError


class _FakeSession:
    def __init__(self):
        self.added: list = []
        self.committed = False
        self._next_id = 1

    def add(self, obj):
        obj.id = self._next_id
        self._next_id += 1
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def get(self, model_cls, obj_id):
        for obj in self.added:
            if getattr(obj, "id", None) == obj_id:
                return obj
        return None


def _make_update(text: str, user_id: int = 555, first_name: str = "Amir", username: str | None = "amirt"):
    user = SimpleNamespace(id=user_id, first_name=first_name, username=username)
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    return SimpleNamespace(effective_user=user, message=message)


def _make_context():
    return SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))


def _run(coro):
    # asyncio.run() (not get_event_loop().run_until_complete()) — the latter breaks when run
    # after another test in the suite has already closed/replaced the thread's default event
    # loop (observed when this file runs as part of the full `pytest tests/` suite, not alone).
    return asyncio.run(coro)


def test_saves_message_and_replies_even_without_owner_id_configured(monkeypatch):
    monkeypatch.setattr(support, "OWNER_TELEGRAM_USER_ID", None)
    session = _FakeSession()

    @contextmanager
    def fake_get_session():
        yield session

    update = _make_update("היי איך אפשר לפנות לבעלים")
    context = _make_context()

    with patch.object(support, "get_session", fake_get_session):
        _run(contact_fallback.handle_stray_message(update, context))

    assert len(session.added) == 1
    saved = session.added[0]
    assert saved.message == "היי איך אפשר לפנות לבעלים"
    assert saved.telegram_user_id == 555
    assert not saved.notified_owner
    context.bot.send_message.assert_not_called()
    update.message.reply_text.assert_called_once()


def test_notifies_owner_and_marks_notified_when_configured(monkeypatch):
    monkeypatch.setattr(support, "OWNER_TELEGRAM_USER_ID", "999")
    session = _FakeSession()

    @contextmanager
    def fake_get_session():
        yield session

    update = _make_update("שאלה על המחירים")
    context = _make_context()

    with patch.object(support, "get_session", fake_get_session):
        _run(contact_fallback.handle_stray_message(update, context))

    context.bot.send_message.assert_called_once()
    call_kwargs = context.bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == "999"
    assert "שאלה על המחירים" in call_kwargs["text"]
    assert session.added[0].notified_owner is True
    update.message.reply_text.assert_called_once()


def test_send_failure_does_not_crash_or_mark_notified(monkeypatch):
    monkeypatch.setattr(support, "OWNER_TELEGRAM_USER_ID", "999")
    session = _FakeSession()

    @contextmanager
    def fake_get_session():
        yield session

    update = _make_update("הודעה כלשהי")
    context = _make_context()
    context.bot.send_message.side_effect = TelegramError("boom")

    with patch.object(support, "get_session", fake_get_session):
        _run(contact_fallback.handle_stray_message(update, context))

    assert not session.added[0].notified_owner
    update.message.reply_text.assert_called_once()
