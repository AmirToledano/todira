"""Tests for bot/handlers/contact_fallback.py — the catch-all that replies to free text no other
handler claimed (see that module's own docstring for why this exists: a user following the
website's "כתוב/י ישירות לבוט" link got total silence before this, found 2026-09-01).

Only messages that actually look like a help/support request (handlers/support.py's
looks_like_help_request) get escalated to the owner — plain small talk or a stray question gets a
friendly redirect to /start instead, no ContactMessage saved (2026-09-02 fix: the owner tested the
bot himself and every message, including "מה שלומך", was wrongly treated as a support ticket).

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

    update = _make_update("אני רוצה לדבר עם נציג בבקשה")
    context = _make_context()

    with patch.object(support, "get_session", fake_get_session):
        _run(contact_fallback.handle_stray_message(update, context))

    assert len(session.added) == 1
    saved = session.added[0]
    assert saved.message == "אני רוצה לדבר עם נציג בבקשה"
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

    update = _make_update("יש לי בעיה טכנית עם הבוט")
    context = _make_context()

    with patch.object(support, "get_session", fake_get_session):
        _run(contact_fallback.handle_stray_message(update, context))

    context.bot.send_message.assert_called_once()
    call_kwargs = context.bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == "999"
    assert "יש לי בעיה טכנית עם הבוט" in call_kwargs["text"]
    assert session.added[0].notified_owner is True
    update.message.reply_text.assert_called_once()


def test_send_failure_does_not_crash_or_mark_notified(monkeypatch):
    monkeypatch.setattr(support, "OWNER_TELEGRAM_USER_ID", "999")
    session = _FakeSession()

    @contextmanager
    def fake_get_session():
        yield session

    update = _make_update("צריך תמיכה בבקשה")
    context = _make_context()
    context.bot.send_message.side_effect = TelegramError("boom")

    with patch.object(support, "get_session", fake_get_session):
        _run(contact_fallback.handle_stray_message(update, context))

    assert not session.added[0].notified_owner
    update.message.reply_text.assert_called_once()


def test_casual_message_does_not_escalate_just_redirects_to_start(monkeypatch):
    # The actual bug report (2026-09-02, live screenshot): the owner sent plain small talk
    # ("מה שלומך") to test the bot and it came back as a support ticket every time. Nothing here
    # should touch support.py's DB or notify the owner - just a friendly redirect. This user has
    # NO filter yet (contact_fallback.get_session returns a session whose Filter lookup is None),
    # so the 2026-09-06 chat feature (tested separately below) doesn't engage either.
    monkeypatch.setattr(support, "OWNER_TELEGRAM_USER_ID", "999")
    context = _make_context()
    no_filter_session = _FakeFilterSession(existing_filter=None)

    for text in ("מה שלומך", "איזה דירות יש לך במבשרת"):
        update = _make_update(text)
        with (
            patch.object(support, "get_session") as get_session_mock,
            patch.object(contact_fallback, "get_session", lambda: no_filter_session),
            patch.object(contact_fallback, "get_or_create_user", lambda s, u: SimpleNamespace(id=1)),
        ):
            _run(contact_fallback.handle_stray_message(update, context))
        get_session_mock.assert_not_called()

    context.bot.send_message.assert_not_called()


def test_casual_message_reply_mentions_start_not_support():
    update = _make_update("מה שלומך")
    context = _make_context()
    no_filter_session = _FakeFilterSession(existing_filter=None)

    with (
        patch.object(contact_fallback, "get_session", lambda: no_filter_session),
        patch.object(contact_fallback, "get_or_create_user", lambda s, u: SimpleNamespace(id=1)),
    ):
        _run(contact_fallback.handle_stray_message(update, context))

    update.message.reply_text.assert_called_once()
    reply = update.message.reply_text.call_args.args[0]
    assert "/start" in reply
    assert "נחזור אליך" not in reply


# --- 2026-09-06: real chat (+ live filter editing) for already-onboarded users ---
# Found live by the owner comparing side-by-side against the reference bot: an already-onboarded
# user's free-text message used to always hit the plain "type /start" redirect above, which
# doesn't even acknowledge they're already registered. Mirrors website/whatsapp_webhook.py's
# identical fix for the same gap on that channel.


class _FakeFilterRow:
    def __init__(self, **kwargs):
        self.deal_type = kwargs.get("deal_type", "rent")
        self.cities = kwargs.get("cities", ["תל אביב יפו"])
        self.rooms_min = kwargs.get("rooms_min")
        self.rooms_max = kwargs.get("rooms_max")
        self.price_min = kwargs.get("price_min")
        self.price_max = kwargs.get("price_max")
        self.keywords = kwargs.get("keywords", [])


class _FakeFilterSession:
    def __init__(self, existing_filter=None):
        self._existing_filter = existing_filter
        self.committed = False

    def scalar(self, stmt):
        return self._existing_filter

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_onboarded_user_casual_message_gets_gemini_chat_reply_not_start_redirect():
    filter_row = _FakeFilterRow()
    session = _FakeFilterSession(existing_filter=filter_row)
    update = _make_update("מה שלומך")
    context = _make_context()

    with (
        patch.object(contact_fallback, "get_session", lambda: session),
        patch.object(contact_fallback, "get_or_create_user", lambda s, u: SimpleNamespace(id=1)),
        patch.object(
            contact_fallback.gemini_client,
            "chat_with_existing_user",
            return_value={"filter_changed": False, "response_message": "הכל מצוין, תודה ששאלת! 😊"},
        ) as chat_mock,
    ):
        _run(contact_fallback.handle_stray_message(update, context))

    chat_mock.assert_called_once()
    call_args = chat_mock.call_args.args
    assert call_args[0] == "מה שלומך"
    assert call_args[3] == "Amir"
    update.message.reply_text.assert_called_once_with("הכל מצוין, תודה ששאלת! 😊")
    assert session.committed is False


def test_onboarded_user_filter_change_message_updates_filter_directly():
    filter_row = _FakeFilterRow(cities=["תל אביב יפו"])
    session = _FakeFilterSession(existing_filter=filter_row)
    update = _make_update("תוסיף לי גם רמת גן")
    context = _make_context()

    with (
        patch.object(contact_fallback, "get_session", lambda: session),
        patch.object(contact_fallback, "get_or_create_user", lambda s, u: SimpleNamespace(id=1)),
        patch.object(
            contact_fallback.gemini_client,
            "chat_with_existing_user",
            return_value={
                "filter_changed": True,
                "cities": ["תל אביב יפו", "רמת גן"],
                "response_message": "הוספתי גם את רמת גן! 🏠",
            },
        ),
    ):
        _run(contact_fallback.handle_stray_message(update, context))

    assert filter_row.cities == ["תל אביב יפו", "רמת גן"]
    assert session.committed is True
    update.message.reply_text.assert_called_once_with("הוספתי גם את רמת גן! 🏠")


def test_onboarded_user_gemini_failure_sends_hiccup_message():
    session = _FakeFilterSession(existing_filter=_FakeFilterRow())
    update = _make_update("משהו")
    context = _make_context()

    with (
        patch.object(contact_fallback, "get_session", lambda: session),
        patch.object(contact_fallback, "get_or_create_user", lambda s, u: SimpleNamespace(id=1)),
        patch.object(contact_fallback.gemini_client, "chat_with_existing_user", return_value=None),
    ):
        _run(contact_fallback.handle_stray_message(update, context))

    update.message.reply_text.assert_called_once()
    assert "תקלה טכנית" in update.message.reply_text.call_args.args[0]
    assert session.committed is False


def test_onboarded_user_help_request_still_escalates_not_chat(monkeypatch):
    """looks_like_help_request must still take priority over the chat feature — an existing filter
    shouldn't change that a real support request gets escalated the same way as before."""
    monkeypatch.setattr(support, "OWNER_TELEGRAM_USER_ID", "999")
    support_session = _FakeSession()
    update = _make_update("יש לי בעיה טכנית עם הבוט")
    context = _make_context()

    @contextmanager
    def fake_support_get_session():
        yield support_session

    with (
        patch.object(support, "get_session", fake_support_get_session),
        patch.object(contact_fallback, "get_session") as chat_get_session_mock,
        patch.object(contact_fallback.gemini_client, "chat_with_existing_user") as chat_mock,
    ):
        _run(contact_fallback.handle_stray_message(update, context))

    chat_get_session_mock.assert_not_called()
    chat_mock.assert_not_called()
    context.bot.send_message.assert_called_once()
