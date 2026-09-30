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
from todira_common.bot_strings import bot_text  # noqa: E402
from todira_common.wid_token import verify_wid_token  # noqa: E402


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


def _fake_user(pending_state=None, language="he"):
    return SimpleNamespace(id=1, pending_onboarding_state=pending_state, language=language)


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


# --- _try_link_code_sync: channel linking (a `ref_xxxxxx` code sent as a plain message) ---
# Checked in _process_payload_sync BEFORE _ensure_language_selected_sync / get_or_create_whatsapp_
# user run (2026-09-27 fix — see its own docstring for the incident that found this), so these test
# _try_link_code_sync directly rather than _handle_incoming_text_sync.


def test_link_code_attaches_this_whatsapp_number_to_the_code_owner():
    code_user = SimpleNamespace(
        id=5, whatsapp_phone_number=None, first_name=None, language="he",
        whatsapp_notifications_opted_in=False, filter=None,
    )
    session = _QueuedScalarSession(results=[None])  # conflict check: nobody else has this number
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "resolve_link_code", lambda s, t: code_user),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_mock,
    ):
        handled = whatsapp_webhook._try_link_code_sync("9725500000", "Amir", "ref_abc123")

    assert handled is True
    assert code_user.whatsapp_phone_number == "9725500000"
    assert code_user.first_name == "Amir"
    assert session.committed is True
    send_mock.assert_called_once()
    assert "חיברתי" in send_mock.call_args[0][1]
    # 2026-09-27 real owner decision: linking WhatsApp auto-enables notifications immediately,
    # no separate /account step — see _try_link_code_sync's own comment on this.
    assert code_user.whatsapp_notifications_opted_in is True


def test_link_code_keeps_opt_in_true_when_already_opted_in():
    code_user = SimpleNamespace(
        id=5, whatsapp_phone_number=None, first_name=None, language="he",
        whatsapp_notifications_opted_in=True, filter=None,
    )
    session = _QueuedScalarSession(results=[None])
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "resolve_link_code", lambda s, t: code_user),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message"),
    ):
        whatsapp_webhook._try_link_code_sync("9725500000", "Amir", "ref_abc123")

    assert code_user.whatsapp_notifications_opted_in is True


def test_link_code_does_not_overwrite_an_existing_first_name():
    code_user = SimpleNamespace(
        id=5, whatsapp_phone_number=None, first_name="שם קיים", language="he",
        whatsapp_notifications_opted_in=False, filter=None,
    )
    session = _QueuedScalarSession(results=[None])
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "resolve_link_code", lambda s, t: code_user),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message"),
    ):
        whatsapp_webhook._try_link_code_sync("9725500000", "Amir", "ref_abc123")

    assert code_user.first_name == "שם קיים"


def test_link_code_sends_one_aggregate_matches_summary_not_per_listing():
    """2026-09-27 real owner report: connecting WhatsApp used to try to push every already-
    matching listing individually, all at once. Linking to an account that already has a filter
    must send exactly ONE extra summary message (on top of the link-success confirmation), not one
    per match — find_new_matches_to_show itself is mocked out here (already covered by its own
    dedicated tests), this just checks _try_link_code_sync wires it up and sends the right text."""
    existing_filter = SimpleNamespace(deal_type="rent", cities=["תל אביב יפו"])
    code_user = SimpleNamespace(
        id=5, whatsapp_phone_number=None, first_name=None, language="he",
        whatsapp_notifications_opted_in=False, filter=existing_filter,
    )
    session = _QueuedScalarSession(results=[None])
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "resolve_link_code", lambda s, t: code_user),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_mock,
        patch.object(
            whatsapp_webhook, "find_new_matches_to_show", return_value=(3, ["a", "b", "c"])
        ) as find_mock,
    ):
        whatsapp_webhook._try_link_code_sync("9725500000", "Amir", "ref_abc123")

    find_mock.assert_called_once_with(session, code_user.id, existing_filter)
    # link-success confirmation, then exactly one aggregate summary — never one send per listing.
    assert send_mock.call_count == 2
    summary_call = send_mock.call_args_list[1][0]
    assert summary_call[0] == "9725500000"
    assert "3" in summary_call[1]
    summary_url = summary_call[1].rsplit("apartments?wid=", 1)[1]
    assert verify_wid_token(summary_url) == "9725500000"


def test_link_code_sends_no_matches_yet_summary_when_filter_has_no_current_matches():
    existing_filter = SimpleNamespace(deal_type="rent", cities=["תל אביב יפו"])
    code_user = SimpleNamespace(
        id=5, whatsapp_phone_number=None, first_name=None, language="he",
        whatsapp_notifications_opted_in=False, filter=existing_filter,
    )
    session = _QueuedScalarSession(results=[None])
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "resolve_link_code", lambda s, t: code_user),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_mock,
        patch.object(whatsapp_webhook, "find_new_matches_to_show", return_value=(0, [])),
    ):
        whatsapp_webhook._try_link_code_sync("9725500000", "Amir", "ref_abc123")

    assert send_mock.call_count == 2
    summary_text = send_mock.call_args_list[1][0][1]
    assert "עדיין אין דירות תואמות כרגע" in summary_text  # onboarding.no_matches_yet's static prefix
    summary_url = summary_text.rsplit("wid=", 1)[1]
    assert verify_wid_token(summary_url) == "9725500000"


def test_link_code_conflict_when_whatsapp_number_already_has_a_different_account():
    code_user = SimpleNamespace(id=5, whatsapp_phone_number=None, first_name=None, language="he")
    other_existing_user = SimpleNamespace(id=42, language="he")  # a DIFFERENT row already using this wa_id
    session = _QueuedScalarSession(results=[other_existing_user])
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "resolve_link_code", lambda s, t: code_user),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as send_mock,
    ):
        handled = whatsapp_webhook._try_link_code_sync("9725500000", "Amir", "ref_abc123")

    assert handled is True  # still "handled" — a conflict reply was sent, no merge happened
    assert code_user.whatsapp_phone_number is None  # untouched — no merge happened
    assert session.committed is False
    send_mock.assert_called_once()
    assert "חשבון נפרד" in send_mock.call_args[0][1]


def test_unknown_or_expired_code_is_not_handled_here():
    session = _QueuedScalarSession(results=[])
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "resolve_link_code", lambda s, t: None),
    ):
        handled = whatsapp_webhook._try_link_code_sync("9725500000", "Amir", "ref_expiredcode")

    assert handled is False  # caller falls through to the language picker / normal chat flow


def test_first_message_ever_that_is_a_valid_link_code_never_reaches_get_or_create_whatsapp_user():
    """The exact 2026-09-27 live incident: a genuinely first-time WhatsApp sender's very first
    message IS their link code. Regression guard for _process_payload_sync's own ordering — the
    language picker's get_or_create_whatsapp_user must never run for this message, or a spurious,
    disconnected user row gets created and the code is silently swallowed."""
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "9725500000", "profile": {"name": "Amir"}}],
                            "messages": [
                                {"id": "m1", "from": "9725500000", "type": "text", "text": {"body": "ref_b9zg13"}}
                            ],
                        }
                    }
                ]
            }
        ]
    }
    with (
        patch.object(whatsapp_webhook, "_already_processed", return_value=False),
        patch.object(whatsapp_webhook, "_try_link_code_sync", return_value=True) as link_mock,
        patch.object(whatsapp_webhook, "_ensure_language_selected_sync") as lang_mock,
        patch.object(whatsapp_webhook, "_handle_incoming_text_sync") as handle_mock,
    ):
        whatsapp_webhook._process_payload_sync(payload)

    link_mock.assert_called_once_with("9725500000", "Amir", "ref_b9zg13")
    lang_mock.assert_not_called()
    handle_mock.assert_not_called()


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


def test_existing_filter_user_inverted_room_range_change_is_rejected():
    # Found live 2026-09-07: Gemini decides both sides of a min/max range from freeform chat text
    # with no structured re-prompt available to catch a garbled range before it's saved - an
    # inverted range hard-fails every listing forever. Mirrors
    # bot/handlers/contact_fallback.py's identical fix on the Telegram side.
    filter_row = _FakeFilter(cities=["תל אביב יפו"], rooms_min=2, rooms_max=4)
    session = _FakeSession(existing_filter=filter_row)
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: _fake_user()),
        patch.object(
            whatsapp_webhook.gemini_client,
            "chat_with_existing_user",
            return_value={
                "filter_changed": True,
                "rooms_min": 5,
                "rooms_max": 3,
                "response_message": "עדכנתי!",
            },
        ),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message"),
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "רוצה בין 5 ל3 חדרים")

    assert (filter_row.rooms_min, filter_row.rooms_max) == (2, 4)  # unchanged, not inverted


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


def test_later_onboarding_turn_assigns_a_new_dict_so_progress_is_actually_saved():
    # Found 2026-09-30: the handler mutated the JSONB dict loaded from the row and assigned that
    # SAME object back - SQLAlchemy sees no change, emits no UPDATE, and every turn after the first
    # silently lost its progress. The fix copies first; this pins that the stored value is a NEW
    # dict carrying the update while the originally loaded one is left untouched.
    session = _FakeSession(existing_filter=None)
    loaded_state = {
        "deal_type": "rent", "cities": [], "rooms_min": None, "rooms_max": None,
        "price_min": None, "price_max": None, "keywords": [],
    }
    user = _fake_user(pending_state=loaded_state)
    turn_two = {
        "rooms_min": 2, "rooms_max": 3, "missing_required": ["cities"],
        "response_message": "באיזו עיר?",
    }
    with (
        patch.object(whatsapp_webhook, "get_session", lambda: session),
        patch.object(whatsapp_webhook, "get_or_create_whatsapp_user", lambda *a: user),
        patch.object(whatsapp_webhook.gemini_client, "parse_onboarding_message", return_value=turn_two),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message"),
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "2-3 חדרים")

    assert user.pending_onboarding_state is not loaded_state
    assert user.pending_onboarding_state["rooms_min"] == 2
    assert loaded_state["rooms_min"] is None


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
        # 2026-09-27: the aggregate "here's what already matches" summary — covered on its own by
        # test_complete_state_sends_current_matches_summary_after_onboarding below; mocked out here
        # so this test stays focused on the filter-creation/opt-in mechanics it was written for.
        patch.object(whatsapp_webhook, "find_new_matches_to_show", return_value=(0, [])),
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "תל אביב, עד 7000, 2 חדרים")

    assert len(session.added) == 1
    saved_filter = session.added[0]
    assert saved_filter.deal_type == "rent"
    assert saved_filter.cities == ["תל אביב יפו"]
    assert saved_filter.price_max == 7000
    assert user.pending_onboarding_state is None
    assert session.committed
    # 2026-09-27: notifications auto-enable immediately on WhatsApp signup — no separate opt-in
    # step/button anymore, see this module's own docstring for the owner decision behind it.
    assert user.whatsapp_notifications_opted_in is True
    # 2026-09-06 fix: the registration confirmation now ends with the same 3-message filter-edit
    # prompt (a real tappable button, then 2 follow-ups, matching the reference competitor bot's
    # own flow one to one) instead of a bare link, so the very first WhatsApp-only user never even
    # hits the "how do I change this?" dead end. send_text_message fires 5 times total: the Gemini
    # response_message, the "נרשמת!" confirmation, the prompt's own 2 follow-ups, then (2026-09-27)
    # the current-matches summary.
    assert send_text_mock.call_count == 5
    assert send_text_mock.call_args_list[0][0] == ("9725500000", "מעולה, קיבלתי הכל!")
    assert send_text_mock.call_args_list[1][0][0] == "9725500000"
    assert "נרשמת" in send_text_mock.call_args_list[1][0][1]
    assert send_text_mock.call_args_list[2][0][1] == bot_text("whatsapp.filter_edit_followup1", "he")
    assert send_text_mock.call_args_list[3][0][1] == bot_text("whatsapp.filter_edit_followup2", "he")
    # 2026-09-27: the second CTA button (opt-in to notifications on /account) is gone — that's now
    # automatic, see above — only the filter-edit prompt's own CTA button remains.
    assert send_cta_mock.call_count == 1
    # 2026-09-25 security fix: ?wid= now carries a signed, time-limited token, not the bare phone
    # number (see todira_common.wid_token's own module docstring for the account-takeover this
    # closes) — assert the URL decodes back to the right number instead of a literal match.
    filter_wid_url = send_cta_mock.call_args_list[0][0][3]
    assert filter_wid_url.startswith(f"{whatsapp_webhook.WEBSITE_URL}/filter?wid=")
    filter_token = filter_wid_url.rsplit("wid=", 1)[1]
    assert verify_wid_token(filter_token) == "9725500000"


def test_complete_state_sends_current_matches_summary_after_onboarding():
    """The brand-new-signup path gets the exact same one-aggregate-summary treatment as linking an
    existing account (see test_link_code_sends_one_aggregate_matches_summary_not_per_listing) —
    find_new_matches_to_show must be called with the JUST-CREATED filter (not code_user.filter,
    which doesn't apply here — this is a fresh Filter row built from this onboarding message)."""
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
        patch.object(whatsapp_webhook.whatsapp_client, "send_cta_url_message"),
        patch.object(whatsapp_webhook, "find_new_matches_to_show", return_value=(7, [])) as find_mock,
    ):
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "תל אביב, עד 7000, 2 חדרים")

    saved_filter = session.added[0]
    find_mock.assert_called_once_with(session, user.id, saved_filter)
    assert send_text_mock.call_count == 5
    summary_text = send_text_mock.call_args_list[4][0][1]
    assert "7" in summary_text
    summary_url = summary_text.rsplit("wid=", 1)[1]
    assert verify_wid_token(summary_url) == "9725500000"


class _FakeRaceSession:
    """Simulates the DB's own unique-constraint violation on Filter.user_id — a genuine race
    between two concurrent onboarding-completing deliveries for the same new user (see this
    module's own test below for the real report). Only the FIRST commit() call raises, matching a
    real DB: the recovery lookup after rollback succeeds."""

    def __init__(self, recovered_filter):
        self._recovered_filter = recovered_filter
        self.added: list = []
        self.rolled_back = False
        self.commit_calls = 0

    def scalar(self, stmt):
        # Before the race is triggered (the handler's own "does this user already have a filter"
        # check at the very top, deciding onboarding vs. chat mode): None, so onboarding proceeds.
        # After the failed commit (this function's own recovery lookup): the row the OTHER
        # concurrent request just committed.
        return self._recovered_filter if self.commit_calls > 0 else None

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commit_calls += 1
        if self.commit_calls == 1:
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError("insert", {}, Exception("unique violation"))

    def rollback(self):
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_complete_state_recovers_from_a_genuine_concurrent_filter_insert_race():
    """2026-09-25 real bug fix: this webhook is stateless between requests, and Meta can and does
    deliver two rapid messages from the same new user as separate webhook POSTs, each its own
    BackgroundTask. If both independently reach onboarding-completion at nearly the same moment,
    both try to INSERT a Filter for the same user_id (unique) — the loser used to have this whole
    per-message try/except (_process_payload_sync) swallow the IntegrityError silently, so that
    user got no reply at all for that message."""
    session = _FakeRaceSession(recovered_filter=SimpleNamespace(id=1, user_id=1))
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
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message"),
        patch.object(whatsapp_webhook.whatsapp_client, "send_cta_url_message"),
        # recovered_filter above is a bare SimpleNamespace (id/user_id only) — find_new_matches_to_
        # show would blow up reading .deal_type/.cities off it, and that's not what this test is
        # about (the race recovery itself), so it's mocked out same as the test right above this.
        patch.object(whatsapp_webhook, "find_new_matches_to_show", return_value=(0, [])),
    ):
        # Must not raise — the whole point of the fix.
        whatsapp_webhook._handle_incoming_text_sync("9725500000", "Amir", "תל אביב, עד 7000, 2 חדרים")

    assert session.rolled_back is True
    # 2026-09-27: a SECOND commit now always follows (the current-matches-summary bookkeeping, see
    # find_new_matches_to_show's own docstring) — this is the one failed INSERT attempt (the OTHER
    # concurrent request's own commit already saved the Filter row) plus that one real commit.
    assert session.commit_calls == 2


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
        bot_text("whatsapp.help_request_body", "he"),
        bot_text("whatsapp.help_request_button", "he"),
        f"{whatsapp_webhook.WEBSITE_URL}/contact",
    )
    send_text_mock.assert_not_called()


def test_help_request_notification_escapes_html(monkeypatch):
    # Found live 2026-09-07: the WhatsApp sender's profile name and message text are both
    # attacker-controlled and were going straight into a parse_mode=HTML Telegram notification
    # unescaped, same bug class fixed in bot/handlers/support.py and website/main.py.
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
        patch.object(whatsapp_webhook.whatsapp_client, "send_cta_url_message"),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message"),
    ):
        whatsapp_webhook._handle_incoming_text_sync(
            "9725500000", "<b>Evil</b>", "תמיכה טכנית <script>alert(1)</script> & בעיה"
        )

    chat_mock.assert_not_called()
    text = post_mock.call_args[1]["json"]["text"]
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "<b>Evil</b>" not in text
    assert "&lt;b&gt;Evil&lt;/b&gt;" in text


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


def test_process_payload_sync_one_bad_message_does_not_abort_the_rest_of_the_batch():
    # Found live 2026-09-07: the whole batch used to be wrapped in ONE try/except - a real webhook
    # delivery can carry several senders' messages at once (Meta batches them), so one message
    # that blew up aborted every OTHER message in the same batch too, silently dropping unrelated
    # users' messages.
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [
                                {"wa_id": "9725500001", "profile": {"name": "Bad"}},
                                {"wa_id": "9725500002", "profile": {"name": "Good"}},
                            ],
                            "messages": [
                                {"id": "m1", "from": "9725500001", "type": "text", "text": {"body": "boom"}},
                                {"id": "m2", "from": "9725500002", "type": "text", "text": {"body": "hi"}},
                            ],
                        }
                    }
                ]
            }
        ]
    }

    def _fake_handle(wa_id, name, text):
        if wa_id == "9725500001":
            raise RuntimeError("simulated failure processing this one message")
        _fake_handle.calls.append(wa_id)

    _fake_handle.calls = []

    with (
        patch.object(whatsapp_webhook, "_already_processed", return_value=False),
        patch.object(whatsapp_webhook, "_try_link_code_sync", return_value=False),
        patch.object(whatsapp_webhook, "_ensure_language_selected_sync", return_value="he"),
        patch.object(whatsapp_webhook, "_fire_typing_indicator"),
        patch.object(whatsapp_webhook, "_handle_incoming_text_sync", side_effect=_fake_handle),
    ):
        whatsapp_webhook._process_payload_sync(payload)

    # The second (good) message still got processed despite the first one raising.
    assert _fake_handle.calls == ["9725500002"]


def test_failed_delivery_status_is_logged_with_meta_error_but_never_the_recipient(caplog):
    # Found 2026-10-01: statuses used to be dropped silently, so a message Meta accepted (200) but
    # never delivered left no trace at all.
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {
                                    "id": "wamid.SECRET",
                                    "status": "failed",
                                    "recipient_id": "972500000000",
                                    "pricing": {"category": "marketing"},
                                    "errors": [
                                        {
                                            "code": 131049,
                                            "title": "healthy ecosystem engagement",
                                            "error_data": {"details": "not delivered"},
                                        }
                                    ],
                                },
                                {
                                    "id": "wamid.OTHER",
                                    "status": "delivered",
                                    "recipient_id": "972500000000",
                                    "pricing": {"category": "utility"},
                                },
                            ]
                        }
                    }
                ]
            }
        ]
    }
    with caplog.at_level("INFO", logger=whatsapp_webhook.logger.name):
        whatsapp_webhook._process_payload_sync(payload)

    text = caplog.text
    assert "delivery FAILED" in text and "131049" in text and "marketing" in text
    assert "status=delivered" in text and "utility" in text
    assert "972500000000" not in text
    assert "wamid" not in text
