"""Tests for the website's paid-access surfaces (website/main.py): /admin/users (owner-only free-
access toggle) and /upgrade (self-service weekly/monthly plan selection).

Same importlib-loading approach as test_website_auth.py (see that file's comment) — website/
main.py shares a basename with scraper/main.py so it can't go through a bare `import main`.
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

_spec = importlib.util.spec_from_file_location("website_main_paid_access", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402

_OWNER_TG_ID = 111
_NOW = dt.datetime.now(dt.timezone.utc)


class _FakeUser:
    def __init__(self, id, telegram_user_id=None, **overrides):
        self.id = id
        self.telegram_user_id = telegram_user_id
        self.whatsapp_phone_number = overrides.get("whatsapp_phone_number")
        self.google_sub = overrides.get("google_sub")
        self.first_name = overrides.get("first_name", "Test")
        self.telegram_username = overrides.get("telegram_username")
        self.created_at = overrides.get("created_at", _NOW)
        self.trial_ends_at = overrides.get("trial_ends_at", _NOW + dt.timedelta(days=1))
        self.paid_until = overrides.get("paid_until")
        self.free_access_granted = overrides.get("free_access_granted", False)


class _FakeSession:
    def __init__(self, users_by_pk=None, users_by_telegram_id=None, all_users=None):
        self._by_pk = users_by_pk or {}
        self._by_telegram_id = users_by_telegram_id or {}
        self._all = all_users or []
        self.committed = False
        self.added: list = []

    def get(self, model, pk):
        return self._by_pk.get(pk)

    def scalar(self, stmt):
        for user in self._by_telegram_id.values():
            return user
        return None

    def scalars(self, stmt):
        class _Scalars:
            def __init__(self, items):
                self._items = items

            def all(self):
                return self._items

        return _Scalars(self._all)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True


@pytest.fixture
def client():
    with patch.object(website_main, "OWNER_TELEGRAM_USER_ID", str(_OWNER_TG_ID)):
        yield TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_admin_users_requires_owner_session_not_uid(client):
    resp = client.get("/admin/users", params={"uid": _OWNER_TG_ID})
    assert resp.status_code == 404


def test_admin_users_lists_and_shows_access_state_for_owner():
    owner = _FakeUser(id=1, telegram_user_id=_OWNER_TG_ID)
    other = _FakeUser(id=2, telegram_user_id=222, trial_ends_at=_NOW - dt.timedelta(days=1))
    fake_session = _FakeSession(users_by_pk={1: owner}, all_users=[owner, other])

    @contextmanager
    def _fake_get_session():
        yield fake_session

    # _require_owner is patched to short-circuit as "owner" — the session-cookie mechanics that
    # actually establish a real login session are already covered by test_website_auth.py; this
    # test is about the ROUTE's own behavior (rendering, gating logic) once ownership is granted.
    with patch.object(website_main, "get_session", _fake_get_session), patch.object(
        website_main, "_require_owner", lambda request, session: owner
    ):
        c = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = c.get("/admin/users")

    assert resp.status_code == 200
    assert "אין גישה" in resp.text  # the expired-trial user shows as having no access


def test_toggle_free_access_flips_the_flag_and_redirects():
    owner = _FakeUser(id=1, telegram_user_id=_OWNER_TG_ID)
    target = _FakeUser(id=2, telegram_user_id=222, free_access_granted=False)
    fake_session = _FakeSession(users_by_pk={1: owner, 2: target})

    @contextmanager
    def _fake_get_session():
        yield fake_session

    with patch.object(website_main, "get_session", _fake_get_session), patch.object(
        website_main, "_require_owner", lambda request, session: owner
    ):
        c = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = c.post("/admin/users/2/toggle-free-access")

    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/users"
    assert target.free_access_granted is True
    assert fake_session.committed is True


def test_toggle_free_access_rejected_for_non_owner():
    fake_session = _FakeSession()

    @contextmanager
    def _fake_get_session():
        yield fake_session

    with patch.object(website_main, "get_session", _fake_get_session):
        c = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = c.post("/admin/users/2/toggle-free-access")

    assert resp.status_code == 404


def test_upgrade_page_requires_a_known_user(client):
    fake_session = _FakeSession()

    @contextmanager
    def _fake_get_session():
        yield fake_session

    with patch.object(website_main, "get_session", _fake_get_session):
        resp = client.get("/upgrade", params={"uid": 999999})

    assert resp.status_code == 200
    assert "טודירה" in resp.text  # sanity: a real page rendered (need_uid.html), not a crash


def test_upgrade_page_shows_plan_options_for_a_real_user():
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})

    @contextmanager
    def _fake_get_session():
        yield fake_session

    with patch.object(website_main, "get_session", _fake_get_session):
        c = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = c.get("/upgrade", params={"uid": 222})

    assert resp.status_code == 200
    assert "₪15" in resp.text
    assert "₪25" in resp.text
    assert "₪40" in resp.text


def test_upgrade_submit_extends_paid_until_and_redirects():
    """Grow isn't configured in these tests (no GROW_* env vars set) — /upgrade falls back to the
    earlier informal click-trust flow, exactly as before this feature shipped. See
    test_website_grow_payments.py for the real-gateway path."""
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=None)
    fake_session = _FakeSession(users_by_telegram_id={222: user})

    @contextmanager
    def _fake_get_session():
        yield fake_session

    with (
        patch.object(website_main, "get_session", _fake_get_session),
        patch.object(website_main.grow_client, "is_configured", lambda: False),
    ):
        c = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = c.post("/upgrade", data={"plan": "weekly", "uid": "222"})

    assert resp.status_code == 303
    assert user.paid_until is not None
    assert user.paid_until > _NOW + dt.timedelta(days=6)
    assert fake_session.committed is True
    assert len(fake_session.added) == 1
    payment = fake_session.added[0]
    assert payment.status == "paid"
    assert payment.gateway is None
    assert payment.amount_ils == 15


def test_upgrade_submit_rejects_unknown_plan():
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})

    @contextmanager
    def _fake_get_session():
        yield fake_session

    with patch.object(website_main, "get_session", _fake_get_session):
        c = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = c.post("/upgrade", data={"plan": "yearly", "uid": "222"})

    assert resp.status_code == 400
