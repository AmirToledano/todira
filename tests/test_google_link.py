"""Tests for common/dorin_common/google_link.py — the `gl_xxxxx` token generation/consumption
behind cross-BROWSER-CONTEXT Google account linking (see the module's own docstring for why this
exists: Telegram's in-app browser is a separate cookie jar from wherever the Google sign-in
started, which is why the earlier session-cookie-only approach kept failing live). Consumers:
website/main.py's auth_google_callback (generation) and bot/handlers/start.py (consumption).
"""
from __future__ import annotations

import datetime as dt
import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from dorin_common.google_link import (
    TOKEN_PREFIX,
    generate_google_link_token,
    resolve_google_link_token,
)
from dorin_common.models import PendingGoogleLink

_NOW = dt.datetime.now(dt.timezone.utc)


class _FakeSession:
    def __init__(self, scalar_result=None):
        self._scalar_result = scalar_result
        self.committed = False
        self.added: list = []
        self.deleted: list = []

    def scalar(self, stmt):
        return self._scalar_result

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.committed = True


def _pending(**overrides):
    defaults = {
        "token": TOKEN_PREFIX + "abc123",
        "google_sub": "google-sub-1",
        "expires_at": _NOW + dt.timedelta(minutes=5),
    }
    defaults.update(overrides)
    return PendingGoogleLink(**defaults)


def test_generate_google_link_token_prefixes_and_stores_the_google_sub():
    session = _FakeSession()

    token = generate_google_link_token(session, "google-sub-xyz")

    assert token.startswith(TOKEN_PREFIX)
    assert len(session.added) == 1
    row = session.added[0]
    assert row.token == token
    assert row.google_sub == "google-sub-xyz"
    assert row.expires_at > _NOW
    assert session.committed is True


def test_generate_google_link_token_is_unique_across_calls():
    session = _FakeSession()
    token1 = generate_google_link_token(session, "sub-a")
    token2 = generate_google_link_token(session, "sub-b")
    assert token1 != token2


def test_resolve_google_link_token_returns_none_for_non_gl_text():
    session = _FakeSession(scalar_result=_pending())  # would match if we even queried
    assert resolve_google_link_token(session, "ref_abc123") is None
    assert resolve_google_link_token(session, "") is None
    assert session.deleted == []  # never touched the DB for an obviously-wrong prefix


def test_resolve_google_link_token_returns_none_for_unknown_token():
    session = _FakeSession(scalar_result=None)
    assert resolve_google_link_token(session, TOKEN_PREFIX + "doesnotexist") is None


def test_resolve_google_link_token_returns_none_and_deletes_an_expired_token():
    expired = _pending(expires_at=_NOW - dt.timedelta(minutes=1))
    session = _FakeSession(scalar_result=expired)

    result = resolve_google_link_token(session, expired.token)

    assert result is None
    # Unlike channel_link_code (lives on the user row, left alone on expiry to avoid clobbering a
    # fresh regen), a PendingGoogleLink is its own standalone row — cleaning up an expired one
    # immediately is safe and avoids the table accumulating dead rows forever.
    assert expired in session.deleted
    assert session.committed is True


def test_resolve_google_link_token_consumes_a_valid_token_so_it_cannot_be_replayed():
    pending = _pending(google_sub="google-sub-real")
    session = _FakeSession(scalar_result=pending)

    result = resolve_google_link_token(session, pending.token)

    assert result == "google-sub-real"
    assert pending in session.deleted
    assert session.committed is True


def test_resolve_google_link_token_strips_whitespace_before_matching():
    pending = _pending()
    session = _FakeSession(scalar_result=pending)

    result = resolve_google_link_token(session, f"  {pending.token}  ")

    assert result == pending.google_sub
