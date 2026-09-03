"""Tests for common/dorin_common/channel_link.py — the `ref_xxxxxx` code generation/consumption
behind cross-channel account linking (see the module's own docstring, and
bot/handlers/start.py + website/whatsapp_webhook.py for the two consumers)."""
from __future__ import annotations

import datetime as dt
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from dorin_common.channel_link import CODE_PREFIX, generate_link_code, resolve_link_code

_NOW = dt.datetime.now(dt.timezone.utc)


class _FakeSession:
    def __init__(self, scalar_result=None):
        self._scalar_result = scalar_result
        self.committed = False

    def scalar(self, stmt):
        return self._scalar_result

    def commit(self):
        self.committed = True


def _user(**overrides):
    defaults = {"id": 1, "channel_link_code": None, "channel_link_code_expires_at": None}
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_generate_link_code_sets_prefixed_code_and_expiry():
    session = _FakeSession()
    user = _user()

    code = generate_link_code(session, user)

    assert code.startswith(CODE_PREFIX)
    assert len(code) == len(CODE_PREFIX) + 6
    assert user.channel_link_code == code
    assert user.channel_link_code_expires_at > _NOW
    assert session.committed is True


def test_generate_link_code_replaces_a_previous_unused_code():
    session = _FakeSession()
    user = _user(channel_link_code="ref_oldold", channel_link_code_expires_at=_NOW)

    code = generate_link_code(session, user)

    assert user.channel_link_code == code
    assert user.channel_link_code != "ref_oldold"


def test_resolve_link_code_returns_none_for_non_ref_text():
    session = _FakeSession(scalar_result=_user())  # would match if we even queried — we shouldn't
    assert resolve_link_code(session, "שלום") is None
    assert resolve_link_code(session, "") is None


def test_resolve_link_code_strips_and_lowercases_before_matching():
    matched_user = _user(
        channel_link_code="ref_abc123", channel_link_code_expires_at=_NOW + dt.timedelta(minutes=5)
    )
    session = _FakeSession(scalar_result=matched_user)

    result = resolve_link_code(session, "  REF_ABC123  ")

    assert result is matched_user


def test_resolve_link_code_returns_none_for_unknown_code():
    session = _FakeSession(scalar_result=None)
    assert resolve_link_code(session, "ref_doesnotexist") is None


def test_resolve_link_code_returns_none_and_does_not_consume_an_expired_code():
    expired_user = _user(
        channel_link_code="ref_expired1",
        channel_link_code_expires_at=_NOW - dt.timedelta(minutes=1),
    )
    session = _FakeSession(scalar_result=expired_user)

    result = resolve_link_code(session, "ref_expired1")

    assert result is None
    # Left as-is — resolve_link_code only clears the code on a SUCCESSFUL match, so a stale code
    # doesn't get silently wiped out from under a user who might still resend it within the TTL
    # of a freshly regenerated one.
    assert expired_user.channel_link_code == "ref_expired1"
    assert session.committed is False


def test_resolve_link_code_consumes_a_valid_code_so_it_cannot_be_replayed():
    user = _user(
        channel_link_code="ref_oncepls",
        channel_link_code_expires_at=_NOW + dt.timedelta(minutes=5),
    )
    session = _FakeSession(scalar_result=user)

    result = resolve_link_code(session, "ref_oncepls")

    assert result is user
    assert user.channel_link_code is None
    assert user.channel_link_code_expires_at is None
    assert session.committed is True
