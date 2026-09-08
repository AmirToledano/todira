"""Tests for the informal Bit/PayBox payment flow (website/main.py's /upgrade/pay and
/upgrade/pay/confirm, 2026-09-05) — used whenever Grow isn't configured. See
test_website_paid_access.py for /upgrade itself creating the pending Payment, and
test_website_grow_payments.py for the real-gateway path this coexists with.

Same importlib-loading approach as the other website test files (see test_website_paid_access.py's
own comment) — website/main.py shares a basename with scraper/main.py so it can't go through a
bare `import main`.
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

_spec = importlib.util.spec_from_file_location(
    "website_main_informal_payment", _WEBSITE_DIR / "main.py"
)
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402

_NOW = dt.datetime.now(dt.timezone.utc)


class _FakeUser:
    def __init__(self, id, telegram_user_id=None, paid_until=None):
        self.id = id
        self.telegram_user_id = telegram_user_id
        self.paid_until = paid_until


class _FakePayment:
    def __init__(self, id, user_id, plan="weekly", amount_ils=15, status="pending"):
        self.id = id
        self.user_id = user_id
        self.plan = plan
        self.amount_ils = amount_ils
        self.status = status
        self.paid_at = None


class _FakeSession:
    def __init__(self, users_by_telegram_id=None, get_map=None):
        self._by_telegram_id = users_by_telegram_id or {}
        self._get_map = get_map or {}
        self.committed = False

    def scalar(self, stmt):
        for user in self._by_telegram_id.values():
            return user
        return None

    def get(self, model, pk):
        return self._get_map.get((model, pk))

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


# --- /upgrade/pay ---


def test_upgrade_pay_shows_amount_and_bit_details(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    payment = _FakePayment(id=9, user_id=2, plan="weekly", amount_ils=15)
    fake_session = _FakeSession(
        users_by_telegram_id={222: user},
        get_map={(website_main.Payment, 9): payment},
    )

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "OWNER_BIT_PHONE", "0501234567"),
    ):
        resp = client.get("/upgrade/pay", params={"payment_id": 9, "uid": 222})

    assert resp.status_code == 200
    assert "₪15" in resp.text
    assert "0501234567" in resp.text


def test_upgrade_pay_renders_in_english_when_lang_param_is_set(client):
    """2026-09-08 fix: /upgrade/pay was hardcoded Hebrew-only, unlike every other customer-facing
    page — confirms the fix actually renders translated content."""
    user = _FakeUser(id=2, telegram_user_id=222)
    payment = _FakePayment(id=9, user_id=2, plan="weekly", amount_ils=15)
    fake_session = _FakeSession(
        users_by_telegram_id={222: user},
        get_map={(website_main.Payment, 9): payment},
    )

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "OWNER_BIT_PHONE", "0501234567"),
    ):
        resp = client.get("/upgrade/pay", params={"payment_id": 9, "uid": 222, "lang": "en"})

    assert resp.status_code == 200
    assert "Complete payment" in resp.text
    assert "Open the Bit app" in resp.text
    assert "confirm access" in resp.text  # "I've" renders as "I&#39;ve" once Jinja autoescapes it
    assert "השלמת התשלום" not in resp.text


def test_upgrade_pay_404s_for_someone_elses_payment(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    payment = _FakePayment(id=9, user_id=999, plan="weekly")  # belongs to a DIFFERENT user
    fake_session = _FakeSession(
        users_by_telegram_id={222: user},
        get_map={(website_main.Payment, 9): payment},
    )

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/upgrade/pay", params={"payment_id": 9, "uid": 222})

    assert resp.status_code == 404


def test_upgrade_pay_404s_for_unknown_payment(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/upgrade/pay", params={"payment_id": 999, "uid": 222})

    assert resp.status_code == 404


# --- /upgrade/pay/confirm ---


def test_confirm_grants_access_and_marks_payment_paid(client):
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=None)
    payment = _FakePayment(id=9, user_id=2, plan="monthly", amount_ils=40, status="pending")
    fake_session = _FakeSession(
        users_by_telegram_id={222: user},
        get_map={(website_main.Payment, 9): payment},
    )

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post("/upgrade/pay/confirm", data={"payment_id": 9, "uid": "222"})

    assert resp.status_code == 303
    assert resp.headers["location"] == "/upgrade/success?payment_id=9&uid=222"
    assert payment.status == "paid"
    assert payment.paid_at is not None
    assert user.paid_until is not None
    assert user.paid_until > _NOW + dt.timedelta(days=29)
    assert fake_session.committed is True


def test_confirm_is_idempotent_for_an_already_paid_payment(client):
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=_NOW + dt.timedelta(days=10))
    already_paid_expiry = user.paid_until
    payment = _FakePayment(id=9, user_id=2, plan="weekly", status="paid")
    fake_session = _FakeSession(
        users_by_telegram_id={222: user},
        get_map={(website_main.Payment, 9): payment},
    )

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post("/upgrade/pay/confirm", data={"payment_id": 9, "uid": "222"})

    assert resp.status_code == 303
    assert user.paid_until == already_paid_expiry  # NOT extended again


def test_confirm_404s_for_someone_elses_payment(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    payment = _FakePayment(id=9, user_id=999, status="pending")
    fake_session = _FakeSession(
        users_by_telegram_id={222: user},
        get_map={(website_main.Payment, 9): payment},
    )

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post("/upgrade/pay/confirm", data={"payment_id": 9, "uid": "222"})

    assert resp.status_code == 404
    assert payment.status == "pending"  # untouched
