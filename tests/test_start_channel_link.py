"""Tests for bot/handlers/start.py's channel-linking path — reached when /start carries a
`ref_xxxxxx` payload from a `t.me/<bot>?start=ref_xxxxxx` deep link generated on the website's
/account page (see dorin_common/channel_link.py). Covers _upsert_or_link_user_sync's three
outcomes directly (pure sync logic, no event loop needed) and start()'s own reply selection.
"""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.start as start_module


class _QueuedScalarSession:
    """`scalar()` returns queued results in call order — matches the same pattern used across
    the website auth tests (see test_website_auth_google.py's own comment)."""

    def __init__(self, results):
        self._results = list(results)
        self.committed = False

    def scalar(self, stmt):
        return self._results.pop(0) if self._results else None

    def add(self, obj):
        pass

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _tg_user(id=555, username="amirt", first_name="Amir"):
    return SimpleNamespace(id=id, username=username, first_name=first_name)


# --- _upsert_or_link_user_sync ---


def test_valid_link_code_attaches_telegram_id_to_the_code_owner():
    code_user = SimpleNamespace(id=9, telegram_user_id=None, telegram_username=None,
                                 first_name=None, is_active=False)
    # resolve_link_code succeeds; then the "does this telegram id already have its own account"
    # lookup finds nobody.
    session = _QueuedScalarSession(results=[None])
    with (
        patch.object(start_module, "get_session", lambda: session),
        patch.object(start_module, "resolve_link_code", lambda s, code: code_user),
    ):
        outcome = start_module._upsert_or_link_user_sync(_tg_user(), "ref_abc123")

    assert outcome == "linked"
    assert code_user.telegram_user_id == 555
    assert code_user.telegram_username == "amirt"
    assert code_user.is_active is True
    assert session.committed is True


def test_link_code_keeps_existing_first_name_if_code_owner_already_has_one():
    code_user = SimpleNamespace(id=9, telegram_user_id=None, telegram_username=None,
                                 first_name="שם קיים", is_active=False)
    session = _QueuedScalarSession(results=[None])
    with (
        patch.object(start_module, "get_session", lambda: session),
        patch.object(start_module, "resolve_link_code", lambda s, code: code_user),
    ):
        start_module._upsert_or_link_user_sync(_tg_user(first_name="Amir"), "ref_abc123")

    assert code_user.first_name == "שם קיים"


def test_link_code_conflict_when_telegram_id_already_has_its_own_account():
    code_user = SimpleNamespace(id=9, telegram_user_id=None)
    other_existing_user = SimpleNamespace(id=42)  # a DIFFERENT row, already tied to this tg id
    session = _QueuedScalarSession(results=[other_existing_user])
    with (
        patch.object(start_module, "get_session", lambda: session),
        patch.object(start_module, "resolve_link_code", lambda s, code: code_user),
    ):
        outcome = start_module._upsert_or_link_user_sync(_tg_user(), "ref_abc123")

    assert outcome == "conflict"
    assert code_user.telegram_user_id is None  # untouched — no merge happened
    assert session.committed is False


def test_unknown_or_expired_code_falls_through_to_normal_upsert():
    session = _QueuedScalarSession(results=[None])  # normal by-telegram-id lookup finds nobody
    with (
        patch.object(start_module, "get_session", lambda: session),
        patch.object(start_module, "resolve_link_code", lambda s, code: None),
    ):
        outcome = start_module._upsert_or_link_user_sync(_tg_user(), "ref_expired")

    assert outcome == "normal"
    assert session.committed is True


def test_plain_start_with_no_code_is_unaffected():
    session = _QueuedScalarSession(results=[None])
    with patch.object(start_module, "get_session", lambda: session):
        outcome = start_module._upsert_or_link_user_sync(_tg_user(), None)

    assert outcome == "normal"


# --- start(): reply selection off the outcome ---


def _make_update():
    user = _tg_user()
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(effective_user=user, message=message)


def _make_context(args):
    return SimpleNamespace(args=args)


def test_start_replies_with_linked_message():
    update = _make_update()
    with patch.object(start_module, "_upsert_or_link_user_sync", lambda tg_user, code: "linked"):
        asyncio.run(start_module.start(update, _make_context(["ref_abc123"])))
    update.message.reply_text.assert_called_once_with(start_module.LINKED)


def test_start_replies_with_conflict_message():
    update = _make_update()
    with patch.object(
        start_module, "_upsert_or_link_user_sync", lambda tg_user, code: "conflict"
    ):
        asyncio.run(start_module.start(update, _make_context(["ref_abc123"])))
    update.message.reply_text.assert_called_once_with(start_module.LINK_CONFLICT)


def test_start_replies_with_normal_welcome_when_no_args():
    update = _make_update()
    with patch.object(start_module, "_upsert_or_link_user_sync", lambda tg_user, code: "normal"):
        asyncio.run(start_module.start(update, _make_context([])))
    update.message.reply_text.assert_called_once_with(start_module.WELCOME.format(name="Amir"))
