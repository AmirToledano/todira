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


# --- 2026-09-06: ack-Meta-first fix (the slow/duplicate-reply bug) ---
#
# Live symptom the owner reported: a real WhatsApp message got TWO different bot replies (or a
# ~1-minute-late "technical hiccup" reply). Root cause: the whole onboarding turn (DB + Gemini)
# used to run INSIDE the request/response cycle, so a slow Gemini call meant Meta's own webhook
# retry fired before we ever answered. The fix moves that work into a FastAPI BackgroundTask that
# only runs AFTER the 200 is already on the wire, plus a message-id dedup as a second line of
# defense against Meta's documented at-least-once delivery.


def test_post_webhook_processes_a_real_text_message(monkeypatch, client):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{"wa_id": "9725500000", "profile": {"name": "Amir"}}],
                    "messages": [{
                        "id": "wamid.FIRST",
                        "from": "9725500000",
                        "type": "text",
                        "text": {"body": "שלום"},
                    }],
                }
            }]
        }]
    }
    import json as _json

    body = _json.dumps(payload).encode()
    digest = hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()

    with (
        patch.object(whatsapp_webhook, "get_session", lambda: _FakeSession(existing_filter=_FakeFilter())),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: _fake_user()),
        patch.object(
            whatsapp_webhook.gemini_client,
            "chat_with_existing_user",
            return_value={"filter_changed": False, "response_message": "היי! מה שלומך? 😊"},
        ),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_mock,
    ):
        resp = client.post(
            "/webhook/whatsapp",
            content=body,
            headers={"content-type": "application/json", "x-hub-signature-256": f"sha256={digest}"},
        )

    assert resp.status_code == 200
    send_mock.assert_called_once()  # BackgroundTasks ran before TestClient returned the response


def test_a_redelivered_message_id_is_not_processed_twice(monkeypatch, client):
    """Simulates exactly what Meta does when it doesn't get a fast-enough ack: POSTs the SAME
    message id a second time. The dedup guard must stop the second delivery from producing a
    second reply."""
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{"wa_id": "9725500001", "profile": {"name": "Amir"}}],
                    "messages": [{
                        "id": "wamid.REDELIVERED-TEST",
                        "from": "9725500001",
                        "type": "text",
                        "text": {"body": "שלום שוב"},
                    }],
                }
            }]
        }]
    }
    import json as _json

    body = _json.dumps(payload).encode()
    digest = hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    headers = {"content-type": "application/json", "x-hub-signature-256": f"sha256={digest}"}

    with (
        patch.object(whatsapp_webhook, "get_session", lambda: _FakeSession(existing_filter=_FakeFilter())),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: _fake_user()),
        patch.object(
            whatsapp_webhook.gemini_client,
            "chat_with_existing_user",
            return_value={"filter_changed": False, "response_message": "שוב שלום! 😊"},
        ),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_mock,
    ):
        first = client.post("/webhook/whatsapp", content=body, headers=headers)
        second = client.post("/webhook/whatsapp", content=body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    send_mock.assert_called_once()


def test_already_processed_dedup_helper():
    assert whatsapp_webhook._already_processed("wamid.unit-test-1") is False
    assert whatsapp_webhook._already_processed("wamid.unit-test-1") is True
    assert whatsapp_webhook._already_processed(None) is False


# --- 2026-09-06: WhatsApp "typing…" indicator, requested after a live side-by-side comparison
# against a competitor's bot that shows one — doesn't make Gemini faster, but makes the same wait
# feel like "it's working" instead of "did this even arrive?"


def test_post_webhook_fires_typing_indicator_for_a_text_message(monkeypatch, client):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{"wa_id": "9725500002", "profile": {"name": "Amir"}}],
                    "messages": [{
                        "id": "wamid.TYPING-TEST",
                        "from": "9725500002",
                        "type": "text",
                        "text": {"body": "שלום"},
                    }],
                }
            }]
        }]
    }
    import json as _json

    body = _json.dumps(payload).encode()
    digest = hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()

    with (
        patch.object(whatsapp_webhook, "get_session", lambda: _FakeSession(existing_filter=_FakeFilter())),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: _fake_user()),
        patch.object(
            whatsapp_webhook.gemini_client,
            "chat_with_existing_user",
            return_value={"filter_changed": False, "response_message": "היי! 😊"},
        ),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message"),
        patch.object(whatsapp_webhook, "_fire_typing_indicator") as typing_mock,
    ):
        resp = client.post(
            "/webhook/whatsapp",
            content=body,
            headers={"content-type": "application/json", "x-hub-signature-256": f"sha256={digest}"},
        )

    assert resp.status_code == 200
    typing_mock.assert_called_once_with("wamid.TYPING-TEST")


def test_fire_typing_indicator_runs_on_a_background_thread():
    calls = []
    with (
        patch.object(
            whatsapp_webhook.whatsapp_client,
            "mark_as_read_with_typing_indicator",
            lambda mid: calls.append(mid),
        ),
    ):
        whatsapp_webhook._fire_typing_indicator("wamid.direct-test")
        # Thread.start() is async by nature — give it a moment to actually run.
        import time

        for _ in range(50):
            if calls:
                break
            time.sleep(0.01)

    assert calls == ["wamid.direct-test"]


# --- _handle_incoming_text_sync: the onboarding state machine ---


class _FakeFilter:
    """Stands in for a real Filter row — `_handle_incoming_text_sync`'s existing-filter branch
    reads these attributes to build the `current_filter` dict it hands to
    gemini_client.chat_with_existing_user, and (on filter_changed=True) setattr()s some of them
    back."""

    def __init__(self, **kwargs):
        self.deal_type = kwargs.get("deal_type", "rent")
        self.cities = kwargs.get("cities", ["תל אביב יפו"])
        self.rooms_min = kwargs.get("rooms_min")
        self.rooms_max = kwargs.get("rooms_max")
        self.price_min = kwargs.get("price_min")
        self.price_max = kwargs.get("price_max")
        self.keywords = kwargs.get("keywords", [])


class _FakeSession:
    def __init__(self, existing_filter=None):
        self._existing_filter = existing_filter
        self.added: list = []
        self.committed = False

    def scalar(self, stmt):
        return self._existing_filter

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


class _QueuedScalarSession:
    """`scalar()` returns queued results in call order — used for the channel-linking tests below,
    where _handle_incoming_text_sync's conflict check does its own raw `session.scalar(select(User)
    ...)` call (resolve_link_code itself is mocked out, so it never touches this session)."""

    def __init__(self, results):
        self._results = list(results)
        self.committed = False

    def scalar(self, stmt):
        return self._results.pop(0) if self._results else None

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# --- _handle_incoming_text_sync: channel linking (a `ref_xxxxxx` code sent as a plain message) ---


def test_link_code_attaches_this_whatsapp_number_to_the_code_owner():
    code_user = SimpleNamespace(id=5, whatsapp_phone_number=None, first_name=None)
    session = _QueuedScalarSession(results=[None])  # conflict check: nobody else has this number
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "resolve_link_code", lambda s, t: code_user),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user") as get_or_create_mock,
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "ref_abc123")

    assert code_user.whatsapp_phone_number == "9725500000"
    assert code_user.first_name == "Amir"
    assert session.committed is True
    get_or_create_mock.assert_not_called()  # never creates a separate new user row
    send_mock.assert_called_once()
    assert "חיברתי" in send_mock.call_args[0][1]


def test_link_code_does_not_overwrite_an_existing_first_name():
    code_user = SimpleNamespace(id=5, whatsapp_phone_number=None, first_name="שם קיים")
    session = _QueuedScalarSession(results=[None])
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "resolve_link_code", lambda s, t: code_user),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user"),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message"),
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "ref_abc123")

    assert code_user.first_name == "שם קיים"


def test_link_code_conflict_when_whatsapp_number_already_has_a_different_account():
    code_user = SimpleNamespace(id=5, whatsapp_phone_number=None, first_name=None)
    other_existing_user = SimpleNamespace(id=42)  # a DIFFERENT row already using this wa_id
    session = _QueuedScalarSession(results=[other_existing_user])
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "resolve_link_code", lambda s, t: code_user),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user") as get_or_create_mock,
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "ref_abc123")

    assert code_user.whatsapp_phone_number is None  # untouched — no merge happened
    assert session.committed is False
    get_or_create_mock.assert_not_called()
    send_mock.assert_called_once()
    assert "חשבון נפרד" in send_mock.call_args[0][1]


def test_ref_prefixed_but_unknown_code_falls_through_to_normal_onboarding():
    session = _FakeSession(existing_filter=_FakeFilter())
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "resolve_link_code", lambda s, t: None),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: _fake_user()),
        patch.object(
            whatsapp_webhook.gemini_client,
            "chat_with_existing_user",
            return_value={"filter_changed": False, "response_message": "לא הכרתי את הקוד הזה 🙂"},
        ) as chat_mock,
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as text_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "ref_expiredcode")

    chat_mock.assert_called_once()
    text_mock.assert_called_once_with("9725500000", "לא הכרתי את הקוד הזה 🙂")


def test_existing_filter_user_gets_chat_reply_via_gemini_no_canned_block():
    """2026-09-06: replaces sending the exact same 3-message "edit your filter" block on EVERY
    free-text message from an already-onboarded user regardless of content — found live by the
    owner comparing against the reference bot, whose already-onboarded users get real, varied,
    contextual replies. A plain chit-chat message with no filter-change intent now gets Gemini's
    own natural reply and nothing else."""
    filter_row = _FakeFilter(cities=["תל אביב יפו"], price_max=6000)
    session = _FakeSession(existing_filter=filter_row)
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: _fake_user()),
        patch.object(
            whatsapp_webhook.gemini_client,
            "chat_with_existing_user",
            return_value={"filter_changed": False, "response_message": "הכל מצוין, תודה ששאלת! 😊"},
        ) as chat_mock,
        patch.object(whatsapp_webhook.whatsapp_client, "send_cta_url_message") as cta_mock,
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as text_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "מה שלומך")

    chat_mock.assert_called_once()
    call_args, call_kwargs = chat_mock.call_args
    assert call_args[0] == "מה שלומך"
    assert call_args[1]["cities"] == ["תל אביב יפו"]
    assert call_args[1]["price_max"] == 6000
    assert call_args[3] == "Amir"
    text_mock.assert_called_once_with("9725500000", "הכל מצוין, תודה ששאלת! 😊")
    cta_mock.assert_not_called()  # no canned CTA block on plain chit-chat
    assert not session.added
    assert session.committed is False  # nothing changed, nothing to save


def test_existing_filter_user_message_that_changes_the_filter_updates_it_directly():
    filter_row = _FakeFilter(cities=["תל אביב יפו"], price_max=6000)
    session = _FakeSession(existing_filter=filter_row)
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: _fake_user()),
        patch.object(
            whatsapp_webhook.gemini_client,
            "chat_with_existing_user",
            return_value={
                "filter_changed": True,
                "cities": ["תל אביב יפו", "רמת גן"],
                "price_max": 6000,
                "response_message": "הוספתי גם את רמת גן לחיפוש! 🏠",
            },
        ),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as text_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "תוסיף לי גם רמת גן")

    assert filter_row.cities == ["תל אביב יפו", "רמת גן"]
    assert session.committed is True
    text_mock.assert_called_once_with("9725500000", "הוספתי גם את רמת גן לחיפוש! 🏠")


def test_existing_filter_user_gemini_failure_sends_hiccup_message():
    session = _FakeSession(existing_filter=_FakeFilter())
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: _fake_user()),
        patch.object(whatsapp_webhook.gemini_client, "chat_with_existing_user", return_value=None),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "משהו")

    send_mock.assert_called_once()
    assert "תקלה טכנית" in send_mock.call_args[0][1]
    assert session.committed is False


def test_gemini_failure_sends_hiccup_message():
    session = _FakeSession(existing_filter=None)
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
    session = _FakeSession(existing_filter=None)
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
    session = _FakeSession(existing_filter=None)
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
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_text_mock,
        patch.object(whatsapp_webhook.whatsapp_client, "send_cta_url_message") as send_cta_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "תל אביב, עד 7000, 2 חדרים")

    assert len(session.added) == 1
    saved_filter = session.added[0]
    assert saved_filter.deal_type == "rent"
    assert saved_filter.cities == ["תל אביב יפו"]
    assert saved_filter.price_max == 7000
    assert user.pending_onboarding_state is None
    assert session.committed
    # 2026-09-06 fix: the registration confirmation now ends with the same 3-message filter-edit
    # prompt (a real tappable button, then 2 follow-ups, matching the reference competitor bot's
    # own flow one to one) instead of a bare link, so the very first WhatsApp-only user never even
    # hits the "how do I change this?" dead end. send_text_message fires 4 times total: the Gemini
    # response_message, the "נרשמת!" confirmation, then the prompt's own 2 follow-ups.
    assert send_text_mock.call_count == 4
    assert send_text_mock.call_args_list[0][0] == ("9725500000", "מעולה, קיבלתי הכל!")
    assert send_text_mock.call_args_list[1][0][0] == "9725500000"
    assert "נרשמת" in send_text_mock.call_args_list[1][0][1]
    assert send_text_mock.call_args_list[2][0][1] == whatsapp_webhook._FILTER_EDIT_FOLLOWUP_1
    assert send_text_mock.call_args_list[3][0][1] == whatsapp_webhook._FILTER_EDIT_FOLLOWUP_2
    send_cta_mock.assert_called_once()
    assert send_cta_mock.call_args[0][3] == f"{whatsapp_webhook.WEBSITE_URL}/filter?wid=9725500000"


# --- Help/support requests (2026-09-07) — checked before both the existing-filter chat branch and
# onboarding parsing, mirroring bot/handlers/contact_fallback.py's own precedence on Telegram, so
# "תמיכה" et al. never gets reinterpreted as apartment criteria or routed through the free-chat
# reply that used to just describe the contact page in words with no real link. ---


class _FakeHelpSession:
    """Supports add/commit/get (ContactMessage lookups) on top of _FakeSession's scalar, since
    _handle_help_request's own helpers each open their own `with get_session()` — all patched to
    return this same instance."""

    def __init__(self, existing_filter=None):
        self._existing_filter = existing_filter
        self.added: list = []
        self.committed = False
        self._next_id = 1

    def scalar(self, stmt):
        return self._existing_filter

    def add(self, obj):
        obj.id = self._next_id
        self._next_id += 1
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def get(self, model, pk):
        for row in self.added:
            if row.id == pk:
                return row
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_help_request_saves_message_notifies_owner_and_sends_contact_button(monkeypatch):
    monkeypatch.setattr(whatsapp_webhook, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(whatsapp_webhook, "OWNER_TELEGRAM_USER_ID", "999")

    session = _FakeHelpSession(existing_filter=_FakeFilter())
    user = _fake_user()

    class _FakeResponse:
        status_code = 200

    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: user),
        patch.object(whatsapp_webhook.httpx, "post", return_value=_FakeResponse()) as post_mock,
        patch.object(whatsapp_webhook.gemini_client, "chat_with_existing_user") as chat_mock,
        patch.object(whatsapp_webhook.whatsapp_client, "send_cta_url_message") as send_cta_mock,
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_text_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "אני צריך תמיכה טכנית")

    # Never fell through to the free-chat reply that would otherwise fire for an already-onboarded
    # user's free text.
    chat_mock.assert_not_called()

    assert len(session.added) == 1
    saved = session.added[0]
    assert saved.source == "whatsapp_bot"
    assert "אני צריך תמיכה טכנית" in saved.message
    assert "9725500000" in saved.message
    assert saved.notified_owner is True

    post_mock.assert_called_once()
    assert post_mock.call_args[0][0] == "https://api.telegram.org/bottest-token/sendMessage"
    assert post_mock.call_args[1]["json"]["chat_id"] == "999"

    send_cta_mock.assert_called_once_with(
        "9725500000",
        whatsapp_webhook._HELP_REQUEST_BODY,
        whatsapp_webhook._HELP_REQUEST_BUTTON_TEXT,
        f"{whatsapp_webhook.WEBSITE_URL}/contact",
    )
    send_text_mock.assert_not_called()


def test_help_request_checked_before_onboarding_too(monkeypatch):
    """A not-yet-onboarded user (no Filter) typing a help request must also escalate — not get
    reinterpreted as onboarding free text by parse_onboarding_message."""
    monkeypatch.setattr(whatsapp_webhook, "TELEGRAM_BOT_TOKEN", None)
    monkeypatch.setattr(whatsapp_webhook, "OWNER_TELEGRAM_USER_ID", None)

    session = _FakeHelpSession(existing_filter=None)
    user = _fake_user()

    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: user),
        patch.object(whatsapp_webhook.gemini_client, "parse_onboarding_message") as onboarding_mock,
        patch.object(whatsapp_webhook.whatsapp_client, "send_cta_url_message") as send_cta_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", None, "אפשר לדבר עם נציג?")

    onboarding_mock.assert_not_called()
    assert len(session.added) == 1
    # no TELEGRAM_BOT_TOKEN configured, so _mark_help_request_notified_sync never runs — the ORM
    # column default (False) only applies on a real flush, so this stays unset (None) here.
    assert session.added[0].notified_owner is not True
    send_cta_mock.assert_called_once()
