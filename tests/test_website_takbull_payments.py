"""Tests for the Takbull payment-gateway path (website/main.py + website/takbull_client.py): a
₪0/month alternative to Grow (see takbull_client.py's module docstring for why), tried first in
/upgrade's fallback chain. Covers /upgrade when Takbull is configured and /webhooks/takbull/{secret}
— the server-to-server confirmation that actually grants access.

Same importlib-loading approach and fake-session pattern as test_website_grow_payments.py (see
that file's comment) — kept as its own module rather than sharing fakes, matching this repo's
existing per-file-isolation convention for these website tests.
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

_spec = importlib.util.spec_from_file_location("website_main_takbull_payments", _WEBSITE_DIR / "main.py")
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


# --- /upgrade: the Takbull path (tried before Grow) ---


def test_upgrade_submit_prefers_takbull_over_grow_when_both_configured(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main.takbull_client, "is_configured", lambda: True),
        patch.object(
            website_main.takbull_client,
            "build_checkout_url",
            lambda **kw: "https://paypage.takbull.co.il/4BPyx?order_reference=1",
        ),
        patch.object(website_main.grow_client, "is_configured", lambda: True),
        patch.object(website_main, "Payment", _FakePayment),
    ):
        resp = client.post("/upgrade", data={"plan": "weekly", "uid": "222"})

    assert resp.status_code == 303
    assert resp.headers["location"] == "https://paypage.takbull.co.il/4BPyx?order_reference=1"
    assert user.paid_until is None  # NOT granted yet — only the webhook does that
    payment = fake_session.added[0]
    assert payment.status == "pending"
    assert payment.gateway == "takbull"
    assert payment.amount_ils == 1  # TEMPORARY 2026-09-06, see access.py


def test_upgrade_submit_marks_payment_failed_and_502s_when_takbull_url_build_fails(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main.takbull_client, "is_configured", lambda: True),
        patch.object(website_main.takbull_client, "build_checkout_url", lambda **kw: None),
        patch.object(website_main, "Payment", _FakePayment),
    ):
        resp = client.post("/upgrade", data={"plan": "monthly", "uid": "222"})

    assert resp.status_code == 502
    payment = fake_session.added[0]
    assert payment.status == "failed"


# --- /webhooks/takbull/{secret} ---


def test_webhook_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    resp = client.post("/webhooks/takbull/wrong-secret", json={"order_reference": "1"})
    assert resp.status_code == 404


def test_webhook_rejects_when_secret_not_configured(client, monkeypatch):
    monkeypatch.delenv("TAKBULL_WEBHOOK_SECRET", raising=False)
    resp = client.post("/webhooks/takbull/anything", json={"order_reference": "1"})
    assert resp.status_code == 404


def test_webhook_grants_access_on_recognized_success_payload(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=None)
    payment = _FakePayment(user_id=2, plan="weekly", amount_ils=15, status="pending", gateway="takbull")
    fake_session = _FakeSession(scalar_results=[payment], get_map={(website_main.User, 2): user})

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={
                "order_reference": str(payment.id),
                "StatusDescription": "Success",
                "StatusCode": 0,
                "OrderStatus": 2,
                "OrderTotalSum": 15,
                "uniqId": "a1b2c3",
            },
        )

    assert resp.status_code == 200
    assert payment.status == "paid"
    assert payment.gateway_transaction_id == "a1b2c3"
    assert user.paid_until is not None
    assert user.paid_until > _NOW + dt.timedelta(days=6)
    assert fake_session.committed is True


def test_webhook_ignores_missing_order_reference(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    fake_session = _FakeSession()

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret", json={"StatusDescription": "Success"}
        )

    assert resp.status_code == 200
    assert fake_session.committed is False


def test_webhook_ignores_unknown_order_reference(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    fake_session = _FakeSession(scalar_results=[None])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={"order_reference": "999", "StatusDescription": "Success"},
        )

    assert resp.status_code == 200
    assert fake_session.committed is False


def test_webhook_leaves_payment_pending_when_no_success_signal_recognized(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    payment = _FakePayment(user_id=2, plan="weekly", amount_ils=15, status="pending", gateway="takbull")
    fake_session = _FakeSession(scalar_results=[payment])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={"order_reference": str(payment.id), "StatusDescription": "Pending"},
        )

    assert resp.status_code == 200
    assert payment.status == "pending"
    assert fake_session.committed is False


def test_webhook_leaves_payment_pending_when_amount_does_not_match(client, monkeypatch):
    """The customer picks their own item on Takbull's shared multi-plan page — if what they
    actually paid doesn't match what this payment row expects, grant nothing rather than guess."""
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    payment = _FakePayment(user_id=2, plan="weekly", amount_ils=15, status="pending", gateway="takbull")
    fake_session = _FakeSession(scalar_results=[payment])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={
                "order_reference": str(payment.id),
                "StatusDescription": "Success",
                "OrderTotalSum": 40,
            },
        )

    assert resp.status_code == 200
    assert payment.status == "pending"
    assert fake_session.committed is False


def test_webhook_does_not_double_credit_an_already_paid_payment(client, monkeypatch):
    """A replayed/duplicate webhook for an already-"paid" payment finds nothing to act on — the
    fake session's queued scalar_results=[None] stands in for the real query's own
    `Payment.status == "pending"` filter no longer matching."""
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    fake_session = _FakeSession(scalar_results=[None])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={"order_reference": "1", "StatusDescription": "Success"},
        )

    assert resp.status_code == 200
    assert fake_session.committed is False
