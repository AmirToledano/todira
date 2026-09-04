"""Tests for bot/handlers/start.py: the channel-linking path (a `ref_xxxxxx` payload from a
`t.me/<bot>?start=ref_xxxxxx` deep link generated on the website's /account page — see
dorin_common/channel_link.py) and the expired-access renewal nudge (a returning, already-onboarded
user whose trial/paid access has run out gets a personalized "renew?" message instead of the plain
welcome, matching the reference product's own confirmed /start behavior). Covers
_upsert_or_link_user_sync's outcomes directly (pure sync logic, no event loop needed) and start()'s
own reply selection.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.start as start_module

_NOW = dt.datetime.now(dt.timezone.utc)


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


def _existing_user(**overrides):
    defaults = dict(
        id=2,
        telegram_user_id=555,
        telegram_username="amirt",
        first_name="Amir",
        is_active=False,
        filter=None,
        free_access_granted=False,
        trial_ends_at=_NOW + dt.timedelta(days=1),
        paid_until=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- _upsert_or_link_user_sync: channel linking ---


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
        outcome, reply = start_module._upsert_or_link_user_sync(_tg_user(), "ref_abc123")

    assert outcome == "linked"
    assert reply == start_module.LINKED
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
        outcome, reply = start_module._upsert_or_link_user_sync(_tg_user(), "ref_abc123")

    assert outcome == "conflict"
    assert reply == start_module.LINK_CONFLICT
    assert code_user.telegram_user_id is None  # untouched — no merge happened
    assert session.committed is False


def test_unknown_or_expired_code_falls_through_to_normal_upsert():
    session = _QueuedScalarSession(results=[None])  # normal by-telegram-id lookup finds nobody
    with (
        patch.object(start_module, "get_session", lambda: session),
        patch.object(start_module, "resolve_link_code", lambda s, code: None),
    ):
        outcome, reply = start_module._upsert_or_link_user_sync(_tg_user(), "ref_expired")

    assert outcome == "normal"
    assert reply == start_module.WELCOME.format(name="Amir")
    assert session.committed is True


def test_plain_start_with_no_code_is_unaffected():
    session = _QueuedScalarSession(results=[None])
    with patch.object(start_module, "get_session", lambda: session):
        outcome, _reply = start_module._upsert_or_link_user_sync(_tg_user(), None)

    assert outcome == "normal"


# --- _upsert_or_link_user_sync: expired-access renewal nudge ---


def test_returning_user_within_trial_gets_plain_welcome():
    user = _existing_user(filter=SimpleNamespace(cities=["תל אביב יפו"]))
    session = _QueuedScalarSession(results=[user])
    with patch.object(start_module, "get_session", lambda: session):
        outcome, reply = start_module._upsert_or_link_user_sync(_tg_user(), None)

    assert outcome == "normal"
    assert reply == start_module.WELCOME.format(name="Amir")


def test_returning_user_with_no_filter_yet_gets_plain_welcome_even_if_trial_expired():
    user = _existing_user(filter=None, trial_ends_at=_NOW - dt.timedelta(days=1))
    session = _QueuedScalarSession(results=[user])
    with patch.object(start_module, "get_session", lambda: session):
        outcome, reply = start_module._upsert_or_link_user_sync(_tg_user(), None)

    assert outcome == "normal"
    assert reply == start_module.WELCOME.format(name="Amir")


def test_returning_user_with_expired_access_and_a_filter_gets_renewal_nudge():
    user = _existing_user(
        filter=SimpleNamespace(cities=["ירושלים", "הר גילה", "מבשרת ציון"]),
        trial_ends_at=_NOW - dt.timedelta(days=1),
        paid_until=None,
        free_access_granted=False,
    )
    session = _QueuedScalarSession(results=[user])
    with (
        patch.object(start_module, "get_session", lambda: session),
        patch.object(start_module, "WEBSITE_URL", "https://todira.duckdns.org"),
    ):
        outcome, reply = start_module._upsert_or_link_user_sync(_tg_user(), None)

    assert outcome == "expired"
    assert "ירושלים, הר גילה ומבשרת ציון" in reply
    assert "https://todira.duckdns.org/upgrade?uid=555" in reply


def test_free_access_granted_user_never_gets_the_renewal_nudge():
    user = _existing_user(
        filter=SimpleNamespace(cities=["חיפה"]),
        trial_ends_at=_NOW - dt.timedelta(days=1),
        free_access_granted=True,
    )
    session = _QueuedScalarSession(results=[user])
    with patch.object(start_module, "get_session", lambda: session):
        outcome, _reply = start_module._upsert_or_link_user_sync(_tg_user(), None)

    assert outcome == "normal"


def test_owner_never_gets_the_renewal_nudge():
    user = _existing_user(filter=SimpleNamespace(cities=["חיפה"]), trial_ends_at=_NOW - dt.timedelta(days=1))
    session = _QueuedScalarSession(results=[user])
    with (
        patch.object(start_module, "get_session", lambda: session),
        patch.object(start_module, "OWNER_TELEGRAM_USER_ID", "555"),
    ):
        outcome, _reply = start_module._upsert_or_link_user_sync(_tg_user(id=555), None)

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
    with patch.object(
        start_module, "_upsert_or_link_user_sync", lambda tg_user, code: ("linked", start_module.LINKED)
    ):
        asyncio.run(start_module.start(update, _make_context(["ref_abc123"])))
    update.message.reply_text.assert_called_once_with(start_module.LINKED)


def test_start_replies_with_conflict_message():
    update = _make_update()
    with patch.object(
        start_module,
        "_upsert_or_link_user_sync",
        lambda tg_user, code: ("conflict", start_module.LINK_CONFLICT),
    ):
        asyncio.run(start_module.start(update, _make_context(["ref_abc123"])))
    update.message.reply_text.assert_called_once_with(start_module.LINK_CONFLICT)


def test_start_replies_with_normal_welcome_when_no_args():
    welcome = start_module.WELCOME.format(name="Amir")
    update = _make_update()
    with patch.object(
        start_module, "_upsert_or_link_user_sync", lambda tg_user, code: ("normal", welcome)
    ):
        asyncio.run(start_module.start(update, _make_context([])))
    update.message.reply_text.assert_called_once_with(welcome)
