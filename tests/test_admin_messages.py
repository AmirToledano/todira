"""Tests for /admin/messages (website/main.py) — the owner-only inbox merging both contact
channels (website /contact + the bot's contact-fallback). Reuses website_main via the same
importlib trick test_website_contact.py uses (see that file's comment on the name collision with
scraper/main.py).

Builds a real signed session cookie (matching starlette.middleware.sessions.SessionMiddleware's
own itsdangerous.TimestampSigner + base64(json) format) instead of mocking the session, so the
actual auth-gating logic (_is_owner_id, the session_user_id lookup) runs for real, not just the
DB-mocked parts.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from base64 import b64encode
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import itsdangerous
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_admin", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


def _session_cookie(data: dict) -> str:
    signer = itsdangerous.TimestampSigner(website_main.SESSION_SECRET_KEY)
    encoded = b64encode(json.dumps(data).encode("utf-8"))
    return signer.sign(encoded).decode("utf-8")


class _FakeSession:
    def __init__(self, user=None, messages=None):
        self._user = user
        self._messages = messages or []

    def get(self, model_cls, obj_id):
        return self._user if self._user is not None and self._user.id == obj_id else None

    def scalars(self, stmt):
        return SimpleNamespace(all=lambda: self._messages)

    def execute(self, stmt):
        # Only ever called here by _current_user_summary's column-only select — reuse the same
        # fake user for that lookup so the header's login-state rendering doesn't itself blow up.
        row = self._user
        return SimpleNamespace(first=lambda: row)


@pytest.fixture
def client():
    with patch.object(website_main, "OWNER_TELEGRAM_USER_ID", "111"):
        yield TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def _fake_user(user_id, telegram_user_id):
    return SimpleNamespace(
        id=user_id,
        telegram_user_id=telegram_user_id,
        first_name="Amir",
        telegram_username="amir",
    )


def test_no_session_returns_404(client):
    with patch.object(
        website_main, "get_session", lambda: _wrap(_FakeSession(user=None))
    ):
        resp = client.get("/admin/messages")
    assert resp.status_code == 404


def test_logged_in_non_owner_returns_404(client):
    non_owner = _fake_user(user_id=1, telegram_user_id=222)
    with patch.object(website_main, "get_session", lambda: _wrap(_FakeSession(user=non_owner))):
        resp = client.get(
            "/admin/messages", cookies={"session": _session_cookie({"user_id": 1})}
        )
    assert resp.status_code == 404


def test_owner_sees_messages(client):
    owner = _fake_user(user_id=1, telegram_user_id=111)
    messages = [
        SimpleNamespace(
            source="website", name="Amir", email="a@b.com", telegram_user_id=None,
            message="שלום מהאתר", notified_owner=True,
            created_at=__import__("datetime").datetime(2026, 9, 1, 10, 0),
        ),
        SimpleNamespace(
            source="telegram_bot", name="Amir", email=None, telegram_user_id=999,
            message="שלום מהבוט", notified_owner=False,
            created_at=__import__("datetime").datetime(2026, 9, 1, 11, 0),
        ),
    ]
    with patch.object(
        website_main, "get_session", lambda: _wrap(_FakeSession(user=owner, messages=messages))
    ):
        resp = client.get(
            "/admin/messages", cookies={"session": _session_cookie({"user_id": 1})}
        )
    assert resp.status_code == 200
    assert "שלום מהאתר" in resp.text
    assert "שלום מהבוט" in resp.text
    assert "🌐 אתר" in resp.text
    assert "🤖 בוט" in resp.text


@contextmanager
def _wrap(fake_session):
    yield fake_session
