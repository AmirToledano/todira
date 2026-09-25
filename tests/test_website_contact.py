"""Tests for the website's /contact page (website/main.py) and its best-effort Telegram push to
the owner (_notify_owner_sync).

2026-09-25: /contact became the site's sixth React island (website/landing-react/contact.html) —
unlike the read-only legal pages (about/accessibility/privacy/terms), this one has a real form, so
unlike a native <form method=post> (which only makes sense against a server-rendered page), the
React form submits via fetch to POST /api/contact (JSON in/out) instead. The old form-encoded
POST /contact endpoint was removed along with it — every test below that used to POST form data to
/contact now POSTs JSON to /api/contact, and GET /contact's own tests now check what the server
actually still controls (config injection, the correct per-entry bundle reference), same reasoning
as test_website_privacy.py's own GET tests — rather than server-rendered form/wa.me markup, which
is a frontend concern verified separately (Playwright, during development).

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
        self._next_id = 1

    def scalar(self, stmt):
        return None

    def scalars(self, stmt):
        return _FakeScalars([])

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


def test_contact_get_renders_react_island(client):
    resp = client.get("/contact")

    assert resp.status_code == 200
    assert 'id="root"' in resp.text
    assert "/static/landing/assets/" in resp.text
    assert "/static/landing/assets/contact-" in resp.text  # its OWN entry, not another page's


def test_contact_get_injects_uid_and_whatsapp_number_for_the_react_form(client):
    with patch.object(website_main, "WHATSAPP_PUBLIC_NUMBER", "972500000000"):
        resp = client.get("/contact?uid=123456")

    assert resp.status_code == 200
    assert "uid: 123456" in resp.text
    assert 'whatsappPublicNumber: "972500000000"' in resp.text


def test_contact_get_without_uid_injects_null(client):
    resp = client.get("/contact")

    assert resp.status_code == 200
    assert "uid: null" in resp.text


def test_contact_post_saves_message_and_returns_ok(client, fake_session):
    with patch.object(website_main, "_notify_owner_sync", return_value=True) as notify:
        resp = client.post(
            "/api/contact",
            json={
                "name": "Amir", "email": "amir@example.com", "message": "יש לי שאלה",
                "uid": "123456", "consent": True,
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert fake_session.committed
    assert len(fake_session.added) == 1
    saved = fake_session.added[0]
    assert saved.name == "Amir"
    assert saved.email == "amir@example.com"
    assert saved.message == "יש לי שאלה"
    assert saved.telegram_user_id == 123456
    assert saved.notified_owner is True
    notify.assert_called_once()


def test_contact_post_empty_message_is_rejected_without_saving(client, fake_session):
    resp = client.post("/api/contact", json={"name": "Amir", "message": "   ", "consent": True})

    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "error": "empty"}
    assert not fake_session.added
    assert not fake_session.committed


def test_contact_post_without_consent_is_rejected_without_saving(client, fake_session):
    """2026-09-25 compliance pass: an explicit 'I agree to the privacy policy' checkbox is now
    required, matching the same pattern /upgrade's own terms_agreed checkbox already uses."""
    resp = client.post("/api/contact", json={"name": "Amir", "message": "יש לי שאלה"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "error": "consent"}
    assert not fake_session.added
    assert not fake_session.committed


def test_contact_post_empty_message_wins_over_missing_consent():
    """Matches the original form-encoded route's precedence (message checked before consent) —
    see _process_contact_message's own docstring for why: someone who DID write a message but
    forgot the checkbox should be told about the checkbox, not that their message was empty, so
    the empty-message error must only win when the message really is empty."""
    import asyncio

    result = asyncio.run(
        website_main._process_contact_message("Amir", "", "   ", "", consent=False)
    )
    assert result == {"ok": False, "error": "empty"}


def test_contact_post_without_uid_stores_no_telegram_user_id(client, fake_session):
    with patch.object(website_main, "_notify_owner_sync", return_value=False):
        client.post("/api/contact", json={"message": "hello", "consent": True})

    assert fake_session.added[0].telegram_user_id is None
    assert not fake_session.added[0].notified_owner


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


def test_notify_owner_sync_escapes_html_in_submitted_fields():
    # Found live 2026-09-07: name/email/message are all attacker-controlled (anyone can submit
    # /contact) and were going straight into a parse_mode=HTML Telegram message unescaped.
    class _FakeResponse:
        status_code = 200

    with patch.object(website_main, "TELEGRAM_BOT_TOKEN", "fake-token"), patch.object(
        website_main, "OWNER_TELEGRAM_USER_ID", "999"
    ), patch.object(website_main.httpx, "post", return_value=_FakeResponse()) as post:
        website_main._notify_owner_sync(
            "<b>Amir</b>", "a@b.com", "hello <script>alert(1)</script> & bye", 1
        )

    text = post.call_args.kwargs["json"]["text"]
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "&lt;b&gt;Amir&lt;/b&gt;" in text


def test_notify_owner_sync_never_raises_on_network_error():
    import httpx

    with patch.object(website_main, "TELEGRAM_BOT_TOKEN", "fake-token"), patch.object(
        website_main, "OWNER_TELEGRAM_USER_ID", "999"
    ), patch.object(website_main.httpx, "post", side_effect=httpx.ConnectError("boom")):
        result = website_main._notify_owner_sync("Amir", "a@b.com", "hi", None)

    assert result is False
