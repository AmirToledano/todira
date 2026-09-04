"""Tests for the owner's 2026-09-05 self-service "preview as a regular user" mode
(website/main.py's /preview/toggle + _effective_access/_display_is_owner/_preview_as_free).

The owner asked to see exactly what a brand-new, never-subscribed visitor sees — the real gated
listing cards and the real /upgrade paywall — without anyone touching his own account's
trial_ends_at/paid_until row or the OWNER_TELEGRAM_USER_ID secret (neither of which this sandbox
can reach directly — no live DB/kubectl access to production). The fix is a session-scoped flag,
toggled by the owner himself via /preview/toggle, that overrides the owner bypass for display and
access-gating purposes only — actual authorization (admin routes) is untouched, see main.py's own
comments on _display_is_owner/_effective_access.

Same importlib-loading approach as the other website test files (see test_website_paid_access.py's
own comment) — website/main.py shares a basename with scraper/main.py so it can't go through a
bare `import main`.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_preview_mode", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from starlette.requests import Request as StarletteRequest  # noqa: E402

_OWNER_TG_ID = 111
_NOW = dt.datetime.now(dt.timezone.utc)


class _FakeUser:
    def __init__(self, id, telegram_user_id=None, **overrides):
        self.id = id
        self.telegram_user_id = telegram_user_id
        self.first_name = overrides.get("first_name", "Amir")
        self.telegram_username = overrides.get("telegram_username")
        self.trial_ends_at = overrides.get("trial_ends_at")
        self.paid_until = overrides.get("paid_until")
        self.free_access_granted = overrides.get("free_access_granted", False)


def _request(session_dict: dict, path: str = "/") -> StarletteRequest:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "session": session_dict,
        "query_string": b"",
        "headers": [],
        "app": website_main.app,
    }
    return StarletteRequest(scope)


@pytest.fixture
def owner_env():
    with patch.object(website_main, "OWNER_TELEGRAM_USER_ID", str(_OWNER_TG_ID)):
        yield


# ---------------------------------------------------------------------------
# _preview_as_free / _display_is_owner / _effective_access — pure session-flag logic
# ---------------------------------------------------------------------------


def test_preview_as_free_defaults_to_false():
    assert website_main._preview_as_free(_request({})) is False


def test_preview_as_free_true_once_flagged():
    assert website_main._preview_as_free(_request({"preview_as_free": True})) is True


def test_display_is_owner_true_for_real_owner_without_preview(owner_env):
    assert website_main._display_is_owner(_request({}), _OWNER_TG_ID) is True


def test_display_is_owner_false_while_previewing(owner_env):
    request = _request({"preview_as_free": True})
    assert website_main._display_is_owner(request, _OWNER_TG_ID) is False


def test_display_is_owner_false_for_a_non_owner_regardless(owner_env):
    assert website_main._display_is_owner(_request({}), 222) is False


def test_effective_access_forced_false_while_previewing_even_for_the_owner(owner_env):
    owner = _FakeUser(id=1, telegram_user_id=_OWNER_TG_ID, paid_until=_NOW + dt.timedelta(days=30))
    request = _request({"preview_as_free": True})
    assert website_main._effective_access(request, owner) is False


def test_effective_access_forced_false_even_if_trial_is_still_technically_valid(owner_env):
    """The whole point: the owner's own trial/paid state must not leak through during a preview —
    forced to "no subscription at all" regardless of what the row actually says."""
    owner = _FakeUser(id=1, telegram_user_id=_OWNER_TG_ID, trial_ends_at=_NOW + dt.timedelta(days=2))
    request = _request({"preview_as_free": True})
    assert website_main._effective_access(request, owner) is False


def test_effective_access_matches_has_full_access_when_not_previewing(owner_env):
    owner = _FakeUser(id=1, telegram_user_id=_OWNER_TG_ID)  # no trial/paid row at all
    request = _request({})
    assert website_main._effective_access(request, owner) is True  # owner bypass still applies

    non_owner_no_access = _FakeUser(id=2, telegram_user_id=222)
    assert website_main._effective_access(request, non_owner_no_access) is False


# ---------------------------------------------------------------------------
# /preview/toggle route
# ---------------------------------------------------------------------------


def test_preview_toggle_rejects_a_visitor_with_no_session_at_all():
    resp = website_main.preview_toggle(_request({}))
    assert resp.status_code == 404


def test_preview_toggle_flips_the_flag_for_the_real_owner_and_redirects(owner_env):
    owner_row = _FakeUser(id=1, telegram_user_id=_OWNER_TG_ID)

    class _FakeDBSession:
        def execute(self, stmt):
            class _Result:
                def first(self_inner):
                    return owner_row

            return _Result()

    @contextmanager
    def _fake_get_session():
        yield _FakeDBSession()

    request = _request({"user_id": 1})
    with patch.object(website_main, "get_session", _fake_get_session):
        resp = website_main.preview_toggle(request, next="/account")

    assert resp.status_code == 303
    assert resp.headers["location"] == "/account"
    assert request.session.get("preview_as_free") is True

    with patch.object(website_main, "get_session", _fake_get_session):
        website_main.preview_toggle(request, next="/account")
    assert request.session.get("preview_as_free") is False


def test_preview_toggle_rejected_for_a_logged_in_non_owner(owner_env):
    other_row = _FakeUser(id=2, telegram_user_id=222)

    class _FakeDBSession:
        def execute(self, stmt):
            class _Result:
                def first(self_inner):
                    return other_row

            return _Result()

    @contextmanager
    def _fake_get_session():
        yield _FakeDBSession()

    request = _request({"user_id": 2})
    with patch.object(website_main, "get_session", _fake_get_session):
        resp = website_main.preview_toggle(request)

    assert resp.status_code == 404
    assert "preview_as_free" not in request.session
