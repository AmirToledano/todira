"""Tests for the website's /contact form (website/main.py) and its best-effort Telegram push to
the owner (_notify_owner_sync).

website/main.py is loaded via importlib under an explicit name rather than `sys.path.insert` +
`import main`, since scraper/main.py is also named main.py — see conftest.py's comment. website/
itself still needs to be on sys.path so main.py's own `from i18n import ...` resolves.
"""
from __future__ import annotations

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

_spec = importlib.util.spec_from_file_location("website_main", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


class _FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeSession:
    def __init__(self):
        self.added: list = []
        self.committed = False

    def scalar(self, stmt):
        return None

    def scalars(self, stmt):
        return _FakeScalars([])

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True


@pytest.fixture
def fake_session():
    return _FakeSession()


@pytest.fixture
def client(fake_session):
    @contextmanager
    def _fake_get_session():
        yield fake_session

    with patch.object(website_main, "get_session", _fake_get_session):
        yield TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_contact_get_renders_form(client):
    resp = client.get("/contact")
    assert resp.status_code == 200
    assert 'action="/contact"' in resp.text


def test_contact_post_saves_message_and_redirects(client, fake_session):
    with patch.object(website_main, "_notify_owner_sync", return_value=True) as notify:
        resp = client.post(
            "/contact",
            data={"name": "Amir", "email": "amir@example.com", "message": "יש לי שאלה", "uid": "123456"},
        )

    assert resp.status_code == 303
    assert "sent=1" in resp.headers["location"]
    assert fake_session.committed
    assert len(fake_session.added) == 1
    saved = fake_session.added[0]
    assert saved.name == "Amir"
    assert saved.email == "amir@example.com"
    assert saved.message == "יש לי שאלה"
    assert saved.telegram_user_id == 123456
    notify.assert_called_once()


def test_contact_post_empty_message_is_rejected_without_saving(client, fake_session):
    resp = client.post("/contact", data={"name": "Amir", "message": "   "})

    assert resp.status_code == 200
    assert not fake_session.added
    assert not fake_session.committed


def test_contact_post_without_uid_stores_no_telegram_user_id(client, fake_session):
    with patch.object(website_main, "_notify_owner_sync", return_value=False):
        client.post("/contact", data={"message": "hello"})

    assert fake_session.added[0].telegram_user_id is None


def test_notify_owner_sync_returns_false_when_unconfigured():
    with patch.object(website_main, "TELEGRAM_BOT_TOKEN", None), patch.object(
        website_main, "OWNER_TELEGRAM_USER_ID", None
    ):
        assert website_main._notify_owner_sync("Amir", "a@b.com", "hi", 1) is False


def test_notify_owner_sync_posts_to_telegram_when_configured():
    class _FakeResponse:
        status_code = 200

    with patch.object(website_main, "TELEGRAM_BOT_TOKEN", "fake-token"), patch.object(
        website_main, "OWNER_TELEGRAM_USER_ID", "999"
    ), patch.object(website_main.httpx, "post", return_value=_FakeResponse()) as post:
        result = website_main._notify_owner_sync("Amir", "a@b.com", "hi", 123)

    assert result is True
    call_kwargs = post.call_args.kwargs
    assert call_kwargs["json"]["chat_id"] == "999"
    assert "hi" in call_kwargs["json"]["text"]


def test_notify_owner_sync_never_raises_on_network_error():
    import httpx

    with patch.object(website_main, "TELEGRAM_BOT_TOKEN", "fake-token"), patch.object(
        website_main, "OWNER_TELEGRAM_USER_ID", "999"
    ), patch.object(website_main.httpx, "post", side_effect=httpx.ConnectError("boom")):
        result = website_main._notify_owner_sync("Amir", "a@b.com", "hi", None)

    assert result is False
