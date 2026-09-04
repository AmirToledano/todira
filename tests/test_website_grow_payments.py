"""Tests for the website's real payment-gateway paths (website/main.py): /upgrade when Grow is
configured (creates a pending Payment + redirects to a real checkout URL, instead of the informal
click-trust flow covered in test_website_paid_access.py), /upgrade/success, and /webhooks/grow —
the server-to-server confirmation that actually grants access. See grow_client.py's module
docstring for why the exact Grow payload shapes involved are provisional/unverified.

Same importlib-loading approach as test_website_paid_access.py (see that file's comment).
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

_spec = importlib.util.spec_from_file_location("website_main_grow_payments", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402

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
        self.trial_ends_at = overrides.get("trial_ends_at", _NOW - dt.timedelta(days=1))
        self.paid_until = overrides.get("paid_until")
        self.free_access_granted = overrides.get("free_access_granted", False)


class _FakePayment:
    _next_id = 1

    def __init__(self, **kwargs):
        self.id = _FakePayment._next_id
        _FakePayment._next_id += 1
        self.user_id = kwargs.get("user_id")
        self.plan = kwargs.get("plan")
        self.amount_ils = kwargs.get("amount_ils")
        self.status = kwargs.get("status", "pending")
        self.gateway = kwargs.get("gateway")
        self.gateway_transaction_id = kwargs.get("gateway_transaction_id")
        self.webhook_token = kwargs.get("webhook_token")
        self.paid_at = kwargs.get("paid_at")


class _FakeSession:
    """`scalar()` returns queued results in call order (matches the pattern used across the
    website auth tests); `.get()` looks up by an explicit id map covering both Users and Payments,
    keyed by (model, pk) so the same fake session serves both."""

    def __init__(self, users_by_telegram_id=None, get_map=None, scalar_results=None):
        self._by_telegram_id = users_by_telegram_id or {}
        self._get_map = get_map or {}
        self._scalar_results = list(scalar_results or [])
        self.committed = False
        self.added: list = []

    def scalar(self, stmt):
        if self._scalar_results:
            return self._scalar_results.pop(0)
        for user in self._by_telegram_id.values():
            return user
        return None

    def get(self, model, pk):
        return self._get_map.get((model, pk))

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, _FakePayment):
            self._get_map[(website_main.Payment, obj.id)] = obj

    def commit(self):
        self.committed = True


def _fake_get_session(session):
    @contextmanager
    def _inner():
        yield session

    return _inner


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


# --- /upgrade: the real-gateway path ---


def test_upgrade_submit_creates_pending_payment_and_redirects_to_grow_checkout(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main.grow_client, "is_configured", lambda: True),
        patch.object(
            website_main.grow_client, "create_checkout_url", lambda **kw: "https://grow.example/checkout/abc"
        ),
        patch.object(website_main, "Payment", _FakePayment),
    ):
        resp = client.post("/upgrade", data={"plan": "monthly", "uid": "222"})

    assert resp.status_code == 303
    assert resp.headers["location"] == "https://grow.example/checkout/abc"
    assert user.paid_until is None  # NOT granted yet — only the webhook does that
    assert len(fake_session.added) == 1
    payment = fake_session.added[0]
    assert payment.status == "pending"
    assert payment.gateway == "grow"
    assert payment.amount_ils == 40
    assert payment.webhook_token  # a real per-payment secret was generated


def test_upgrade_submit_marks_payment_failed_and_502s_when_grow_call_fails(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main.grow_client, "is_configured", lambda: True),
        patch.object(website_main.grow_client, "create_checkout_url", lambda **kw: None),
        patch.object(website_main, "Payment", _FakePayment),
    ):
        resp = client.post("/upgrade", data={"plan": "monthly", "uid": "222"})

    assert resp.status_code == 502
    payment = fake_session.added[0]
    assert payment.status == "failed"


# --- /upgrade/success ---


def test_upgrade_success_page_reports_paid(client):
    payment = _FakePayment(status="paid")
    fake_session = _FakeSession(get_map={(website_main.Payment, payment.id): payment})

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/upgrade/success", params={"payment_id": payment.id})

    assert resp.status_code == 200
    assert "התשלום התקבל" in resp.text


def test_upgrade_success_page_reports_still_pending(client):
    payment = _FakePayment(status="pending")
    fake_session = _FakeSession(get_map={(website_main.Payment, payment.id): payment})

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/upgrade/success", params={"payment_id": payment.id})

    assert resp.status_code == 200
    assert "מעבדים את התשלום" in resp.text


# --- /webhooks/grow ---


def test_webhook_grants_access_on_recognized_success_payload(client):
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=None)
    payment = _FakePayment(user_id=2, plan="weekly", status="pending", webhook_token="secrettoken")
    fake_session = _FakeSession(
        scalar_results=[payment],
        get_map={(website_main.User, 2): user},
    )

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/grow",
            params={"token": "secrettoken"},
            json={"status": "success", "transactionId": "tx-abc"},
        )

    assert resp.status_code == 200
    assert payment.status == "paid"
    assert payment.gateway_transaction_id == "tx-abc"
    assert user.paid_until is not None
    assert user.paid_until > _NOW + dt.timedelta(days=6)
    assert fake_session.committed is True


def test_webhook_ignores_missing_token(client):
    fake_session = _FakeSession()
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post("/webhooks/grow", json={"status": "success"})

    assert resp.status_code == 200
    assert fake_session.committed is False


def test_webhook_ignores_unknown_token(client):
    fake_session = _FakeSession(scalar_results=[None])
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post("/webhooks/grow", params={"token": "nope"}, json={"status": "success"})

    assert resp.status_code == 200
    assert fake_session.committed is False


def test_webhook_leaves_payment_pending_when_no_success_signal_recognized(client):
    payment = _FakePayment(user_id=2, plan="weekly", status="pending", webhook_token="secrettoken")
    fake_session = _FakeSession(scalar_results=[payment])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/grow", params={"token": "secrettoken"}, json={"something": "unrecognized"}
        )

    assert resp.status_code == 200
    assert payment.status == "pending"  # left as-is, not guessed at
    assert fake_session.committed is False


def test_webhook_does_not_double_credit_an_already_paid_payment():
    """A replayed/duplicate webhook call for a payment that's already "paid" should find nothing
    to act on — the fake session's queued scalar_results=[None] here stands in for the real
    query's own `Payment.status == "pending"` filter no longer matching."""
    fake_session = _FakeSession(scalar_results=[None])
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        c = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = c.post(
            "/webhooks/grow", params={"token": "secrettoken"}, json={"status": "success"}
        )

    assert resp.status_code == 200
    assert fake_session.committed is False
