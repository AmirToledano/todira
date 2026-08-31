"""Tests for website/whatsapp_webhook.py — the GET verification handshake, POST signature
verification (fail-closed), and the onboarding state machine in _handle_incoming_text_sync.

whatsapp_webhook.py has no name collision with anything else on sys.path (unlike main.py, which
needs the importlib trick in test_website_contact.py — see that file's own comment), so a plain
sys.path insert + import is enough here.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

import whatsapp_webhook  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(whatsapp_webhook.router)
    return TestClient(app, raise_server_exceptions=True)


# --- GET verification handshake ---


def test_verify_webhook_succeeds_with_correct_token(monkeypatch, client):
    monkeypatch.setenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "secret-verify-token")
    resp = client.get(
        "/webhook/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "secret-verify-token", "hub.challenge": "12345"},
    )
    assert resp.status_code == 200
    assert resp.text == "12345"


def test_verify_webhook_rejects_wrong_token(monkeypatch, client):
    monkeypatch.setenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "secret-verify-token")
    resp = client.get(
        "/webhook/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"},
    )
    assert resp.status_code == 403


def test_verify_webhook_rejects_when_token_not_configured(monkeypatch, client):
    monkeypatch.delenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", raising=False)
    resp = client.get(
        "/webhook/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "anything", "hub.challenge": "1"},
    )
    assert resp.status_code == 403


# --- Signature verification (_verify_signature) — fail-closed contract ---


def test_signature_rejected_when_app_secret_not_configured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
    assert whatsapp_webhook._verify_signature(b"{}", "sha256=whatever") is False


def test_signature_rejected_when_header_missing(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    assert whatsapp_webhook._verify_signature(b"{}", None) is False


def test_signature_rejected_when_wrong(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    assert whatsapp_webhook._verify_signature(b"{}", "sha256=deadbeef") is False


def test_signature_accepted_when_correct(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    body = b'{"hello":"world"}'
    digest = hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    assert whatsapp_webhook._verify_signature(body, f"sha256={digest}") is True


def test_post_webhook_rejects_unsigned_request(monkeypatch, client):
    monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
    resp = client.post("/webhook/whatsapp", json={"entry": []})
    assert resp.status_code == 403


def test_post_webhook_accepts_correctly_signed_request(monkeypatch, client):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    body = b'{"entry":[]}'
    digest = hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    resp = client.post(
        "/webhook/whatsapp",
        content=body,
        headers={"content-type": "application/json", "x-hub-signature-256": f"sha256={digest}"},
    )
    assert resp.status_code == 200


# --- _handle_incoming_text_sync: the onboarding state machine ---


class _FakeSession:
    def __init__(self, existing_filter_id=None):
        self._existing_filter_id = existing_filter_id
        self.added: list = []
        self.committed = False

    def scalar(self, stmt):
        return self._existing_filter_id

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_user(pending_state=None):
    return SimpleNamespace(id=1, pending_onboarding_state=pending_state)


def test_existing_filter_user_gets_already_registered_reply_no_gemini_call():
    session = _FakeSession(existing_filter_id=99)
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: _fake_user()),
        patch.object(whatsapp_webhook.gemini_client, "parse_onboarding_message") as parse_mock,
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "שלום")

    parse_mock.assert_not_called()
    send_mock.assert_called_once()
    assert "כבר יש לך פילטר" in send_mock.call_args[0][1]
    assert not session.added


def test_gemini_failure_sends_hiccup_message():
    session = _FakeSession(existing_filter_id=None)
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: _fake_user()),
        patch.object(whatsapp_webhook.gemini_client, "parse_onboarding_message", return_value=None),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "בלה")

    send_mock.assert_called_once()
    assert "תקלה טכנית" in send_mock.call_args[0][1]
    assert not session.added


def test_incomplete_state_persists_pending_onboarding_without_creating_filter():
    session = _FakeSession(existing_filter_id=None)
    user = _fake_user()
    partial_result = {
        "deal_type": "rent",
        "cities": [],
        "missing_required": ["cities"],
        "response_message": "איזו עיר מעניינת אותך?",
    }
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: user),
        patch.object(
            whatsapp_webhook.gemini_client, "parse_onboarding_message", return_value=partial_result
        ),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "שכירות")

    send_mock.assert_called_once_with("9725500000", "איזו עיר מעניינת אותך?")
    assert not session.added
    assert session.committed
    assert user.pending_onboarding_state["deal_type"] == "rent"


def test_complete_state_creates_filter_and_clears_pending_state():
    session = _FakeSession(existing_filter_id=None)
    user = _fake_user(pending_state={"deal_type": "rent", "cities": [], "rooms_min": None,
                                      "rooms_max": None, "price_min": None, "price_max": None,
                                      "keywords": []})
    complete_result = {
        "deal_type": "rent",
        "cities": ["תל אביב יפו"],
        "rooms_min": 2,
        "rooms_max": None,
        "price_min": None,
        "price_max": 7000,
        "keywords": [],
        "missing_required": [],
        "response_message": "מעולה, קיבלתי הכל!",
    }
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: user),
        patch.object(
            whatsapp_webhook.gemini_client, "parse_onboarding_message", return_value=complete_result
        ),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "תל אביב, עד 7000, 2 חדרים")

    assert len(session.added) == 1
    saved_filter = session.added[0]
    assert saved_filter.deal_type == "rent"
    assert saved_filter.cities == ["תל אביב יפו"]
    assert saved_filter.price_max == 7000
    assert user.pending_onboarding_state is None
    assert session.committed
    assert send_mock.call_count == 2  # the Gemini response_message, then the registration confirmation
