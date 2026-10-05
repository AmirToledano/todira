"""The FREE Takbull flow (2026-10-05, owner decision: no paid Takbull package for now): one hosted payment page
(₪49.90 = 30 days, no auto-renewal), confirmed by Takbull's free automation webhook. Covers takbull_client's URL
building, /upgrade's hosted-page branch, the webhook's matching tiers and the owner alert for an unmatched charge."""
from __future__ import annotations

import importlib.util
import os
import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))
_spec = importlib.util.spec_from_file_location("website_main_takbull_free_flow", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)
takbull_client = website_main.takbull_client

_PAGE = "https://paypage.takbull.co.il/abcde"


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


class _Sess:
    """scalar() pops queued results; scalars() returns the queued 'waiting' list; add()/commit() are recorded."""

    def __init__(self, scalar_results=None, waiting=None, user=None):
        self._scalar = list(scalar_results or [])
        self._waiting = waiting or []
        self.user = user
        self.added = []
        self.committed = False

    def scalar(self, stmt):
        return self._scalar.pop(0) if self._scalar else None

    def scalars(self, stmt):
        return SimpleNamespace(all=lambda: list(self._waiting))

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = 77

    def commit(self):
        self.committed = True


def _payment(**kw):
    return SimpleNamespace(
        id=kw.get("id", 5), user_id=kw.get("user_id", 2), status=kw.get("status", "pending"),
        amount_ils=kw.get("amount_ils", Decimal("49.90")), subscription_uniqid=None, gateway="takbull",
    )


# --- takbull_client ---


def test_hosted_page_needs_page_url_and_secret_but_no_api_key(monkeypatch):
    monkeypatch.delenv("TAKBULL_API_KEY", raising=False)
    monkeypatch.delenv("TAKBULL_API_SECRET", raising=False)
    monkeypatch.delenv(takbull_client.PAYMENT_PAGE_URL_ENV_VAR, raising=False)
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "s")
    assert takbull_client.hosted_page_configured() is False
    monkeypatch.setenv(takbull_client.PAYMENT_PAGE_URL_ENV_VAR, _PAGE)
    assert takbull_client.hosted_page_configured() is True
    assert takbull_client.recurring_api_configured() is False  # the paid flow stays off


def test_build_hosted_checkout_url_carries_reference_and_encoded_email(monkeypatch):
    monkeypatch.setenv(takbull_client.PAYMENT_PAGE_URL_ENV_VAR, _PAGE)
    url = takbull_client.build_hosted_checkout_url(payment_id=12, email="a+b@example.com")
    assert url == f"{_PAGE}?order_reference=12&email=a%2Bb%40example.com"
    assert takbull_client.build_hosted_checkout_url(payment_id=12, email=None) == f"{_PAGE}?order_reference=12"
    monkeypatch.setenv(takbull_client.PAYMENT_PAGE_URL_ENV_VAR, _PAGE + "?x=1")
    assert takbull_client.build_hosted_checkout_url(payment_id=3, email=None) == _PAGE + "?x=1&order_reference=3"
    monkeypatch.delenv(takbull_client.PAYMENT_PAGE_URL_ENV_VAR)
    assert takbull_client.build_hosted_checkout_url(payment_id=3, email=None) is None


# --- /upgrade ---


def test_upgrade_submit_sends_the_user_to_the_hosted_page_with_a_pending_payment(client, monkeypatch):
    monkeypatch.setenv(takbull_client.PAYMENT_PAGE_URL_ENV_VAR, _PAGE)
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "s")
    monkeypatch.delenv("TAKBULL_API_KEY", raising=False)
    user = SimpleNamespace(id=2, telegram_user_id=222, google_email="me@example.com", takbull_subscription_uniqid=None,
                           paid_until=None)
    sess = _Sess(scalar_results=[user])
    pay = lambda **kw: SimpleNamespace(id=None, **kw)  # noqa: E731

    @contextmanager
    def _gs():
        yield sess

    with (
        patch.object(website_main, "get_session", _gs),
        patch.object(website_main, "_resolve_user", lambda *a, **k: user),
        patch.object(website_main, "Payment", pay),
    ):
        resp = client.post("/upgrade", data={"plan": "monthly_subscription", "uid": "222", "terms_agreed": "on"})

    assert resp.status_code == 303
    assert resp.headers["location"] == f"{_PAGE}?order_reference=77&email=me%40example.com"
    created = sess.added[0]
    assert created.status == "pending" and created.gateway == "takbull" and created.amount_ils == Decimal("49.90")
    assert user.paid_until is None  # access only ever comes from the webhook


# --- webhook matching ---


def test_reference_is_matched_only_by_itself_and_a_stray_reference_is_not_guessed():
    p = _payment()
    assert website_main._match_takbull_payment(_Sess([p]), {}, 5) == (p, False)
    assert website_main._match_takbull_payment(_Sess([None, None]), {"CustomerEmail": "x@y.z"}, 99) == (None, False)


def test_without_a_reference_the_payers_email_finds_that_users_pending_payment():
    p = _payment()
    user = SimpleNamespace(id=2)
    sess = _Sess(scalar_results=[None, user, p])  # [transaction seen?, user by email, newest pending]
    body = {"CustomerEmail": "Me@Example.com", "OrderTotalSum": "49.90", "uniqId": "t1"}
    assert website_main._match_takbull_payment(sess, body, None) == (p, False)


def test_without_reference_or_email_the_single_waiting_payment_of_that_amount_is_matched():
    p = _payment()
    sess = _Sess(scalar_results=[None], waiting=[p])
    assert website_main._match_takbull_payment(sess, {"OrderTotalSum": "49.90"}, None) == (p, False)


def test_two_waiting_payments_are_never_guessed():
    sess = _Sess(scalar_results=[None], waiting=[_payment(id=5), _payment(id=6)])
    assert website_main._match_takbull_payment(sess, {"OrderTotalSum": "49.90"}, None) == (None, False)


def test_a_transaction_id_we_already_recorded_is_never_matched_again():
    sess = _Sess(scalar_results=[123], waiting=[_payment()])  # the "seen already" lookup finds a payment
    assert website_main._match_takbull_payment(sess, {"uniqId": "t1", "OrderTotalSum": "49.90"}, None) == (None, False)


def test_no_amount_and_no_match_means_nothing_is_matched():
    assert website_main._match_takbull_payment(_Sess([None]), {}, None) == (None, False)


# --- the owner is told about a paid-looking charge nobody could be matched to ---


def test_an_unmatched_successful_charge_alerts_the_owner_and_grants_nothing(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    sess = _Sess()

    @contextmanager
    def _gs():
        yield sess

    alerts = []
    with (
        patch.object(website_main, "get_session", _gs),
        patch.object(website_main, "_match_takbull_payment", lambda *a, **k: (None, False)),
        patch.object(website_main, "_notify_owner_sync", lambda *a, **k: alerts.append(a)),
    ):
        resp = client.post(
            "/webhooks/takbull/real-secret",
            json={"StatusDescription": "Success", "OrderTotalSum": "49.90", "CustomerEmail": "who@example.com"},
        )
    assert resp.status_code == 200
    assert len(alerts) == 1 and "49.90" in alerts[0][2] and alerts[0][3] is None
    assert sess.committed is False


def test_an_unmatched_failure_payload_does_not_alert(client, monkeypatch):
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    sess = _Sess()

    @contextmanager
    def _gs():
        yield sess

    alerts = []
    with (
        patch.object(website_main, "get_session", _gs),
        patch.object(website_main, "_match_takbull_payment", lambda *a, **k: (None, False)),
        patch.object(website_main, "_notify_owner_sync", lambda *a, **k: alerts.append(a)),
    ):
        resp = client.post("/webhooks/takbull/real-secret", json={"StatusDescription": "Declined"})
    assert resp.status_code == 200 and alerts == []


# --- the thank-you page reports the real status for a known user ---


def _success_resp(client, latest, user):
    sess = _Sess(scalar_results=[latest])

    @contextmanager
    def _gs():
        yield sess

    with patch.object(website_main, "get_session", _gs), patch.object(website_main, "_resolve_user", lambda *a, **k: user):
        return client.get("/upgrade/success")


def test_thank_you_page_waits_for_a_still_pending_payment_and_confirms_a_paid_one(client):
    user = SimpleNamespace(id=2, telegram_user_id=222, language="he")
    assert "http-equiv=\"refresh\"" in _success_resp(client, _payment(status="pending"), user).text
    assert "http-equiv=\"refresh\"" not in _success_resp(client, _payment(status="paid"), user).text
