"""Tests for the Takbull payment-gateway path (website/main.py + website/takbull_client.py): the
real recurring ₪49.90/month subscription API (2026-09-21, tried first in /upgrade's fallback
chain), plus /webhooks/takbull/{secret} — the server-to-server confirmation that actually grants
access, for both the initial charge and a renewal cycle.

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
from decimal import Decimal
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
        self.takbull_subscription_uniqid = overrides.get("takbull_subscription_uniqid")
        self.cancel_at_period_end = overrides.get("cancel_at_period_end", False)


class _FakePayment:
    _next_id = 1

    def __init__(self, **kwargs):
        self.id = kwargs.get("id") or _FakePayment._next_id
        _FakePayment._next_id += 1
        self.user_id = kwargs.get("user_id")
        self.plan = kwargs.get("plan")
        self.amount_ils = kwargs.get("amount_ils")
        self.status = kwargs.get("status", "pending")
        self.gateway = kwargs.get("gateway")
        self.gateway_transaction_id = kwargs.get("gateway_transaction_id")
        self.webhook_token = kwargs.get("webhook_token")
        self.paid_at = kwargs.get("paid_at")
        self.subscription_uniqid = kwargs.get("subscription_uniqid")


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


# --- /upgrade: the real recurring Takbull API path ---


def test_upgrade_submit_uses_recurring_takbull_when_configured(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main.takbull_client, "recurring_api_configured", lambda: True),
        patch.object(
            website_main.takbull_client,
            "create_subscription_checkout_url",
            lambda **kw: ("https://api.takbull.co.il/PaymentGateway?orderUniqId=sub-123", "sub-123"),
        ),
        patch.object(website_main, "Payment", _FakePayment),
    ):
        resp = client.post(
            "/upgrade", data={"plan": "monthly_subscription", "uid": "222", "terms_agreed": "on"}
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "https://api.takbull.co.il/PaymentGateway?orderUniqId=sub-123"
    assert user.paid_until is None  # NOT granted yet — only the webhook does that
    payment = fake_session.added[0]
    assert payment.status == "pending"
    assert payment.gateway == "takbull"
    assert payment.amount_ils == Decimal("49.90")
    assert payment.subscription_uniqid == "sub-123"


def test_upgrade_submit_refuses_a_second_order_for_a_user_with_an_existing_subscription(client):
    """2026-09-24 real bug fix: a user whose subscription was cancelled but hasn't lapsed yet
    (cancel_at_period_end=True) still has a REAL, still-billing Takbull subscription — Takbull's
    own side isn't cancelled until the period actually ends (see account_cancel_subscription's own
    comment). Letting them open a SECOND recurring order here would orphan the first one (the
    webhook overwrites takbull_subscription_uniqid, losing the only reference this app had to it —
    real, unrecoverable double-billing). Server-side backstop for whatever hid this on the GET page
    (see that route's own has_active_subscription fix) not catching it — same "don't trust the
    client alone" reasoning as the terms_agreed check just above this one in main.py."""
    user = _FakeUser(
        id=2, telegram_user_id=222, takbull_subscription_uniqid="already-subscribed-uniqid",
        cancel_at_period_end=True,
    )
    fake_session = _FakeSession(users_by_telegram_id={222: user})

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main.takbull_client, "recurring_api_configured", lambda: True),
        patch.object(
            website_main.takbull_client,
            "create_subscription_checkout_url",
            lambda **kw: pytest.fail("must never open a new order for an already-subscribed user"),
        ),
    ):
        resp = client.post(
            "/upgrade", data={"plan": "monthly_subscription", "uid": "222", "terms_agreed": "on"}
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/account?uid=222"
    assert fake_session.added == []  # no new Payment ever created


def test_upgrade_submit_marks_payment_failed_and_502s_when_takbull_call_fails(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main.takbull_client, "recurring_api_configured", lambda: True),
        patch.object(website_main.takbull_client, "create_subscription_checkout_url", lambda **kw: None),
        patch.object(website_main, "Payment", _FakePayment),
    ):
        resp = client.post(
            "/upgrade", data={"plan": "monthly_subscription", "uid": "222", "terms_agreed": "on"}
        )

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


# --- /webhooks/takbull/{secret} GET — the REAL Takbull IPN mechanism (found live 2026-09-21) ---


def test_webhook_get_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    resp = client.get("/webhooks/takbull/wrong-secret", params={"uniqId": "x", "order_reference": "1"})
    assert resp.status_code == 404


def test_webhook_get_grants_access_via_validate_notification(client, monkeypatch):
    # The GET IPN itself carries no amount — this confirms the full real flow: statusCode=0 from
    # the IPN query params triggers a ValidateNotification call, and ITS response's amount/
    # isSubscriptionPayment are what actually get trusted for crediting.
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=None)
    payment = _FakePayment(
        user_id=2,
        plan="monthly_subscription",
        amount_ils=Decimal("49.90"),
        status="pending",
        gateway="takbull",
        subscription_uniqid="sub-123",
    )
    fake_session = _FakeSession(scalar_results=[payment], get_map={(website_main.User, 2): user})

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(
            website_main.takbull_client,
            "validate_notification",
            lambda uniqid: {"amount": "49.90", "isSubscriptionPayment": True, "orderStatus": 2},
        ),
    ):
        resp = client.get(
            "/webhooks/takbull/real-secret",
            params={
                "uniqId": "a1b2c3",
                "order_reference": str(payment.id),
                "statusCode": "0",
                "transactionInternalNumber": "000001003",
            },
        )

    assert resp.status_code == 200
    assert payment.status == "paid"
    assert payment.gateway_transaction_id == "a1b2c3"
    assert user.paid_until is not None
    assert user.takbull_subscription_uniqid == "sub-123"


def test_webhook_get_ignores_nonzero_status_code(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    fake_session = _FakeSession()

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main.takbull_client, "validate_notification") as mock_validate,
    ):
        resp = client.get(
            "/webhooks/takbull/real-secret",
            params={"uniqId": "a1b2c3", "order_reference": "1", "statusCode": "1"},
        )

    assert resp.status_code == 200
    mock_validate.assert_not_called()
    assert fake_session.committed is False


def test_webhook_get_leaves_pending_when_validate_notification_fails(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    payment = _FakePayment(
        user_id=2, plan="monthly_subscription", amount_ils=Decimal("49.90"), status="pending", gateway="takbull"
    )
    fake_session = _FakeSession(scalar_results=[payment])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main.takbull_client, "validate_notification", lambda uniqid: None),
    ):
        resp = client.get(
            "/webhooks/takbull/real-secret",
            params={"uniqId": "a1b2c3", "order_reference": str(payment.id), "statusCode": "0"},
        )

    assert resp.status_code == 200
    assert payment.status == "pending"
    assert fake_session.committed is False


def test_webhook_get_ignores_missing_uniq_id_or_order_reference(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    fake_session = _FakeSession()

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/webhooks/takbull/real-secret", params={"statusCode": "0"})

    assert resp.status_code == 200
    assert fake_session.committed is False


def test_webhook_grants_access_on_recognized_success_payload_and_stores_subscription(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=None)
    payment = _FakePayment(
        user_id=2,
        plan="monthly_subscription",
        amount_ils=Decimal("49.90"),
        status="pending",
        gateway="takbull",
        subscription_uniqid="sub-123",
    )
    fake_session = _FakeSession(scalar_results=[payment], get_map={(website_main.User, 2): user})

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={
                "order_reference": str(payment.id),
                "StatusDescription": "Success",
                "StatusCode": 0,
                "OrderStatus": 2,
                "OrderTotalSum": "49.90",
                "uniqId": "a1b2c3",
            },
        )

    assert resp.status_code == 200
    assert payment.status == "paid"
    assert payment.gateway_transaction_id == "a1b2c3"
    assert user.paid_until is not None
    assert user.paid_until > _NOW + dt.timedelta(days=28)
    assert user.takbull_subscription_uniqid == "sub-123"
    assert fake_session.committed is True


def test_webhook_accepts_decimal_order_total_now_that_amount_ils_is_numeric(client, monkeypatch):
    # Found live 2026-09-07, fixed 2026-09-21: a whole-shekel amount arriving as a decimal string
    # (e.g. "40.00") used to raise ValueError under int() parsing and get treated as "leave
    # pending" — the real bug this guarded against. Now that amount_ils is Numeric and the webhook
    # parses OrderTotalSum as Decimal, "40.00" correctly equals 40 and grants access, which matters
    # a lot more now that a real recurring price ("49.90") is never a whole number to begin with.
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=None)
    payment = _FakePayment(
        user_id=2, plan="monthly_subscription", amount_ils=Decimal("40"), status="pending", gateway="takbull"
    )
    fake_session = _FakeSession(scalar_results=[payment], get_map={(website_main.User, 2): user})

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={
                "order_reference": str(payment.id),
                "StatusDescription": "Success",
                "OrderTotalSum": "40.00",
            },
        )

    assert resp.status_code == 200
    assert payment.status == "paid"


def test_webhook_leaves_payment_pending_on_unparseable_order_total_instead_of_crashing(client, monkeypatch):
    # A truly malformed value (not just a decimal string) must still fail safe, not crash or grant.
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    payment = _FakePayment(
        user_id=2, plan="monthly_subscription", amount_ils=Decimal("49.90"), status="pending", gateway="takbull"
    )
    fake_session = _FakeSession(scalar_results=[payment])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={
                "order_reference": str(payment.id),
                "StatusDescription": "Success",
                "OrderTotalSum": "not-a-number",
            },
        )

    assert resp.status_code == 200
    assert payment.status == "pending"
    assert fake_session.committed is False


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


def test_webhook_leaves_payment_pending_when_order_total_missing_entirely(client, monkeypatch):
    # Takbull's own documented order-success payload always includes OrderTotalSum — a payload
    # missing it is itself suspicious, not something to trust our own pre-recorded amount for.
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    payment = _FakePayment(
        user_id=2, plan="monthly_subscription", amount_ils=Decimal("49.90"), status="pending", gateway="takbull"
    )
    fake_session = _FakeSession(scalar_results=[payment])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={"order_reference": str(payment.id), "StatusDescription": "Success"},
        )

    assert resp.status_code == 200
    assert payment.status == "pending"
    assert fake_session.committed is False


def test_webhook_leaves_payment_pending_when_no_success_signal_recognized(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    payment = _FakePayment(
        user_id=2, plan="monthly_subscription", amount_ils=Decimal("49.90"), status="pending", gateway="takbull"
    )
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
    payment = _FakePayment(
        user_id=2, plan="monthly_subscription", amount_ils=Decimal("49.90"), status="pending", gateway="takbull"
    )
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


def test_webhook_does_not_double_credit_an_already_paid_payment_with_no_subscription(client, monkeypatch):
    """A replayed/duplicate webhook for an already-"paid", non-subscription payment finds nothing
    to act on: the pending-query misses (already paid) and the renewal-lookup requires a non-null
    subscription_uniqid, which a one-time-plan payment never has."""
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    fake_session = _FakeSession(scalar_results=[None, None])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={"order_reference": "1", "StatusDescription": "Success"},
        )

    assert resp.status_code == 200
    assert fake_session.committed is False


# --- renewal charges (month 2+, Takbull's own recurring engine firing automatically) ---


def test_webhook_grants_a_renewal_charge_as_a_new_payment_row(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=_NOW + dt.timedelta(days=2))
    original = _FakePayment(
        id=7,
        user_id=2,
        plan="monthly_subscription",
        amount_ils=Decimal("49.90"),
        status="paid",
        gateway="takbull",
        subscription_uniqid="sub-123",
        gateway_transaction_id="first-charge-id",
    )
    # First scalar() call is the "pending" lookup (misses, already paid); second is the
    # renewal-eligible "paid" lookup (matches); third is the idempotency check by
    # gateway_transaction_id (misses — this is a genuinely new transaction id).
    fake_session = _FakeSession(
        scalar_results=[None, original, None], get_map={(website_main.User, 2): user}
    )

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={
                "order_reference": str(original.id),
                "StatusDescription": "Success",
                "OrderTotalSum": "49.90",
                "IsSubscriptionPayment": True,
                "uniqId": "renewal-charge-id",
            },
        )

    assert resp.status_code == 200
    assert fake_session.committed is True
    assert len(fake_session.added) == 1
    renewal = fake_session.added[0]
    assert renewal.status == "paid"
    assert renewal.gateway_transaction_id == "renewal-charge-id"
    assert renewal.subscription_uniqid == "sub-123"
    # extend_paid_until stacks on top of the existing future paid_until, not from "now"
    assert user.paid_until > _NOW + dt.timedelta(days=29)


def test_webhook_ignores_a_replayed_renewal_webhook_for_the_same_cycle(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=_NOW + dt.timedelta(days=2))
    original = _FakePayment(
        id=7,
        user_id=2,
        plan="monthly_subscription",
        amount_ils=Decimal("49.90"),
        status="paid",
        gateway="takbull",
        subscription_uniqid="sub-123",
    )
    already_processed = _FakePayment(
        id=8,
        user_id=2,
        plan="monthly_subscription",
        amount_ils=Decimal("49.90"),
        status="paid",
        gateway="takbull",
        subscription_uniqid="sub-123",
        gateway_transaction_id="renewal-charge-id",
    )
    fake_session = _FakeSession(
        scalar_results=[None, original, already_processed],
        get_map={(website_main.User, 2): user},
    )

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={
                "order_reference": str(original.id),
                "StatusDescription": "Success",
                "OrderTotalSum": "49.90",
                "IsSubscriptionPayment": True,
                "uniqId": "renewal-charge-id",
            },
        )

    assert resp.status_code == 200
    assert fake_session.committed is False
    assert fake_session.added == []


def test_webhook_ignores_renewal_flagged_payload_when_no_matching_subscription_found(client, monkeypatch):
    """IsSubscriptionPayment=true alone isn't enough — without a matching "paid" +
    subscription_uniqid row to attach the renewal to (the real query's own WHERE clause, not
    reproducible at this fake-session mocking layer, is what actually enforces that shape; this
    confirms the route's own fallback when that lookup comes back empty either way)."""
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    fake_session = _FakeSession(scalar_results=[None, None])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={
                "order_reference": "5",
                "StatusDescription": "Success",
                "OrderTotalSum": "49.90",
                "IsSubscriptionPayment": True,
            },
        )

    assert resp.status_code == 200
    assert fake_session.committed is False
