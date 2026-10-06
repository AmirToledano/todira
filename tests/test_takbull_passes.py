"""2026-10-06: the free Takbull flow sells three ONE-TIME access passes (₪19.90 = 7 days, ₪29.90 = 14, ₪49.90 = 30,
no auto-renewal). The amount Takbull actually charged decides the days, whichever item the customer picked."""
from __future__ import annotations

import datetime as dt
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
_spec = importlib.util.spec_from_file_location("website_main_takbull_passes", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)
takbull_client = website_main.takbull_client

from todira_common.access import PASS_PLANS, PLAN_DURATIONS, PLAN_PRICES_ILS, plan_for_amount  # noqa: E402

_PAGE = "https://paypage.takbull.co.il/abcde"


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


@pytest.fixture(autouse=True)
def _free_flow(monkeypatch):
    monkeypatch.setenv(takbull_client.PAYMENT_PAGE_URL_ENV_VAR, _PAGE)
    monkeypatch.setenv("TAKBULL_WEBHOOK_SECRET", "real-secret")
    for name in ("TAKBULL_API_KEY", "TAKBULL_API_SECRET", "TAKBULL_PAYMENT_PAGE_URL_PASS_7",
                 "TAKBULL_PAYMENT_PAGE_URL_PASS_14", "TAKBULL_PAYMENT_PAGE_URL_PASS_30"):
        monkeypatch.delenv(name, raising=False)


def test_the_three_passes_have_the_agreed_prices_and_lengths():
    assert [PLAN_PRICES_ILS[p] for p in PASS_PLANS] == [Decimal("19.90"), Decimal("29.90"), Decimal("49.90")]
    assert [PLAN_DURATIONS[p].days for p in PASS_PLANS] == [7, 14, 30]


def test_plan_for_amount_maps_only_real_pass_prices():
    assert plan_for_amount(Decimal("19.90")) == "pass_7"
    assert plan_for_amount(Decimal("29.90")) == "pass_14"
    assert plan_for_amount(Decimal("49.90")) == "pass_30"
    assert plan_for_amount(Decimal("1")) is None  # the owner's test payment
    assert plan_for_amount(Decimal("40")) is None  # an old price


def test_per_plan_page_urls_are_used_when_set_and_the_generic_page_is_the_fallback(monkeypatch):
    assert takbull_client.build_hosted_checkout_url(payment_id=1, email=None, plan="pass_7") == f"{_PAGE}?order_reference=1"
    monkeypatch.setenv("TAKBULL_PAYMENT_PAGE_URL_PASS_7", "https://paypage.takbull.co.il/week")
    assert takbull_client.build_hosted_checkout_url(payment_id=1, email=None, plan="pass_7") == \
        "https://paypage.takbull.co.il/week?order_reference=1"
    assert takbull_client.build_hosted_checkout_url(payment_id=2, email=None, plan="pass_14") == f"{_PAGE}?order_reference=2"


def test_the_flow_is_on_with_only_per_plan_pages(monkeypatch):
    monkeypatch.delenv(takbull_client.PAYMENT_PAGE_URL_ENV_VAR)
    assert takbull_client.hosted_page_configured() is False
    monkeypatch.setenv("TAKBULL_PAYMENT_PAGE_URL_PASS_30", "https://paypage.takbull.co.il/month")
    assert takbull_client.hosted_page_configured() is True


class _Sess:
    def __init__(self, user=None, scalar_results=None):
        self.user = user
        self._scalar = list(scalar_results or [])
        self.added = []
        self.committed = False

    def scalar(self, stmt):
        return self._scalar.pop(0) if self._scalar else None

    def get(self, model, key):
        return self.user

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = 77

    def commit(self):
        self.committed = True


def _post_upgrade(client, plan, *, terms=True):
    user = SimpleNamespace(id=2, telegram_user_id=222, google_email=None, takbull_subscription_uniqid=None, paid_until=None)
    sess = _Sess(scalar_results=[user])

    @contextmanager
    def _gs():
        yield sess

    data = {"plan": plan, "uid": "222"}
    if terms:
        data["terms_agreed"] = "on"
    with (
        patch.object(website_main, "get_session", _gs),
        patch.object(website_main, "_resolve_user", lambda *a, **k: user),
        patch.object(website_main, "Payment", lambda **kw: SimpleNamespace(id=None, **kw)),
    ):
        return client.post("/upgrade", data=data), sess


@pytest.mark.parametrize("plan,amount", [("pass_7", "19.90"), ("pass_14", "29.90"), ("pass_30", "49.90")])
def test_each_pass_creates_a_pending_payment_for_its_own_price(client, plan, amount):
    resp, sess = _post_upgrade(client, plan)
    assert resp.status_code == 303 and resp.headers["location"].startswith(_PAGE)
    created = sess.added[0]
    assert created.plan == plan and created.amount_ils == Decimal(amount) and created.status == "pending"


def test_an_unknown_plan_or_missing_terms_is_rejected(client):
    assert _post_upgrade(client, "pass_999")[0].status_code == 400
    assert _post_upgrade(client, "pass_7", terms=False)[0].status_code == 400


def _webhook(client, payment, user, body):
    sess = _Sess(user=user)

    @contextmanager
    def _gs():
        yield sess

    with (
        patch.object(website_main, "get_session", _gs),
        patch.object(website_main, "_match_takbull_payment", lambda *a, **k: (payment, False)),
    ):
        resp = client.post("/webhooks/takbull/real-secret", json=body)
    return resp, sess


def _pending(plan="pass_30"):
    return SimpleNamespace(
        id=5, user_id=2, plan=plan, amount_ils=PLAN_PRICES_ILS[plan], status="pending", subscription_uniqid=None,
        gateway="takbull", gateway_transaction_id=None, paid_at=None,
    )


def _user():
    return SimpleNamespace(id=2, paid_until=None, takbull_subscription_uniqid=None, cancel_at_period_end=False)


@pytest.mark.parametrize("paid,days", [("19.90", 7), ("29.90", 14), ("49.90", 30)])
def test_the_amount_paid_decides_the_days_even_if_a_different_pass_was_clicked(client, paid, days):
    payment, user = _pending("pass_30"), _user()  # the customer clicked the 30-day card on our site
    resp, sess = _webhook(client, payment, user, {"StatusDescription": "Success", "OrderTotalSum": paid, "uniqId": "t1"})
    assert resp.status_code == 200 and payment.status == "paid" and sess.committed
    assert payment.amount_ils == Decimal(paid)
    granted = user.paid_until - dt.datetime.now(dt.timezone.utc)
    assert dt.timedelta(days=days) - dt.timedelta(minutes=1) < granted <= dt.timedelta(days=days)


def test_an_amount_that_is_no_pass_grants_nothing_and_stays_pending(client):
    payment, user = _pending("pass_30"), _user()
    resp, sess = _webhook(client, payment, user, {"StatusDescription": "Success", "OrderTotalSum": "1.00", "uniqId": "t2"})
    assert resp.status_code == 200 and payment.status == "pending" and user.paid_until is None and not sess.committed


def test_upgrade_page_shows_three_passes_with_prices_when_the_free_flow_is_on(client):
    user = SimpleNamespace(
        id=2, telegram_user_id=222, language="he", trial_ends_at=None, paid_until=None, takbull_subscription_uniqid=None,
        free_access_granted=False,
    )
    sess = _Sess(scalar_results=[user])

    @contextmanager
    def _gs():
        yield sess

    with (
        patch.object(website_main, "get_session", _gs),
        patch.object(website_main, "_resolve_user", lambda *a, **k: user),
        patch.object(website_main, "_effective_access", lambda *a, **k: False),
    ):
        resp = client.get("/upgrade")
    assert resp.status_code == 200
    for plan in PASS_PLANS:
        assert f'value="{plan}"' in resp.text
    for price in ("19.90", "29.90", "49.90"):
        assert f"₪{price}" in resp.text
    assert "auto-renews" not in resp.text and "מתחדש אוטומטית" not in resp.text.split("upgrade-faq")[0]
