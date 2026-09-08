"""Tests for website/main.py's /account — the cross-channel linking page (dorin_common/
channel_link.py): shows which channels (Telegram/WhatsApp/Google) are already linked to the
resolved user, and generates a fresh code + deep links for whichever aren't.

Same importlib-loading approach as test_website_paid_access.py (see that file's comment) —
website/main.py shares a basename with scraper/main.py so it can't go through a bare `import main`.
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

_spec = importlib.util.spec_from_file_location("website_main_account", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402

_FIXED_CODE = "ref_test01"


class _FakeUser:
    def __init__(
        self,
        id,
        telegram_user_id=None,
        whatsapp_phone_number=None,
        google_sub=None,
        free_access_granted=False,
        trial_ends_at=None,
        paid_until=None,
        notifications_enabled=True,
        whatsapp_notifications_opted_in=False,
    ):
        self.id = id
        self.telegram_user_id = telegram_user_id
        self.whatsapp_phone_number = whatsapp_phone_number
        self.google_sub = google_sub
        self.free_access_granted = free_access_granted
        self.trial_ends_at = trial_ends_at
        self.paid_until = paid_until
        self.notifications_enabled = notifications_enabled
        self.whatsapp_notifications_opted_in = whatsapp_notifications_opted_in


class _FakeSession:
    def __init__(self, users_by_telegram_id=None, payments=None):
        self._by_telegram_id = users_by_telegram_id or {}
        self._payments = payments or []
        self.committed = False

    def scalar(self, stmt):
        for user in self._by_telegram_id.values():
            return user
        return None

    def scalars(self, stmt):
        return self._payments

    def commit(self):
        self.committed = True


@pytest.fixture
def client():
    with patch.object(website_main, "generate_link_code", lambda session, user: _FIXED_CODE):
        yield TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def _fake_get_session(session):
    @contextmanager
    def _inner():
        yield session

    return _inner


class _FakePayment:
    def __init__(self, plan, amount_ils, status, created_at, paid_at=None):
        self.plan = plan
        self.amount_ils = amount_ils
        self.status = status
        self.created_at = created_at
        self.paid_at = paid_at


def test_account_requires_a_resolvable_user(client):
    fake_session = _FakeSession()
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 999999})

    assert resp.status_code == 200
    assert "טודירה" in resp.text  # need_uid.html rendered, not a crash


def test_account_generates_a_code_when_a_channel_is_missing(client):
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number=None, google_sub=None)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert resp.status_code == 200
    assert _FIXED_CODE in resp.text
    assert f"https://t.me/AmirDirotBot?start={_FIXED_CODE}" not in resp.text  # telegram already linked


def test_account_shows_whatsapp_link_when_public_number_configured(client):
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number=None)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "WHATSAPP_PUBLIC_NUMBER", "972500000000"),
    ):
        resp = client.get("/account", params={"uid": 222})

    assert f"https://wa.me/972500000000?text={_FIXED_CODE}" in resp.text


def test_account_hides_whatsapp_link_when_public_number_not_configured(client):
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number=None)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "WHATSAPP_PUBLIC_NUMBER", ""),
    ):
        resp = client.get("/account", params={"uid": 222})

    assert "wa.me" not in resp.text


def test_account_google_link_button_carries_a_real_uid_query_param(client):
    """2026-09-05 real bug found live: the template hand-wrote '&amp;uid=' inside a Jinja
    expression, which Jinja's own autoescaping then escaped AGAIN into '&amp;amp;uid=' — a browser
    HTML-decodes that once into the literal string '&amp;uid=123', so the actual query string sent
    to the server was 'next=/account&amp;uid=123', parsed as a param literally named 'amp;uid',
    never 'uid'. Every "🔗 קשר את Google לחשבון" click therefore silently lost its uid server-side,
    which is why linking kept landing on the "we don't recognize this account" page no matter how
    many times it was retried. Asserts the real, single-escaped, correctly-parseable href."""
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number="9725500000", google_sub=None)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert 'href="/auth/google/start?next=/account&amp;uid=222"' in resp.text
    assert "&amp;amp;" not in resp.text  # the double-escape signature itself, never again


def test_account_shows_real_brand_logos_and_english_channel_names(client):
    """2026-09-06: the owner asked for real brand logos + English channel names (Telegram/
    WhatsApp/Google) instead of the plain ✅/⭕ emoji + Hebrew labels this page used before."""
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number=None, google_sub=None)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert ">Telegram<" in resp.text
    assert ">WhatsApp<" in resp.text
    assert ">Google<" in resp.text
    # brand colors from each channel's SVG icon
    assert "#229ED9" in resp.text  # Telegram blue
    assert "#25D366" in resp.text  # WhatsApp green
    assert "#4285F4" in resp.text  # Google blue (part of the 4-color G logo)
    assert "⭕" not in resp.text  # the old plain-circle placeholder is gone


def test_account_connected_channel_shows_status_not_plain_checkmark(client):
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number="9725500000", google_sub="sub123")
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    # 3 linked channels + the notifications tile (also "connected" while enabled, the default)
    assert resp.text.count('class="channel-status connected"') == 4


def test_account_does_not_generate_a_code_once_telegram_and_whatsapp_are_both_linked(client):
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number="9725500000")
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(
        website_main, "generate_link_code"
    ) as generate_mock, patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    generate_mock.assert_not_called()
    assert resp.status_code == 200
    assert _FIXED_CODE not in resp.text


def test_account_shows_active_subscription_status_when_paid_until_is_future(client):
    paid_until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=10)
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number="9725500000", paid_until=paid_until)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert "המנוי שלי 👑" in resp.text
    assert "✅ פעיל, בתוקף עד" in resp.text
    assert paid_until.strftime("%d/%m/%Y") in resp.text


def test_account_shows_trial_subscription_status_when_trial_still_open(client):
    trial_ends_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number="9725500000", trial_ends_at=trial_ends_at)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert "⏳ תקופת ניסיון, עד" in resp.text
    assert trial_ends_at.strftime("%d/%m/%Y") in resp.text


def test_account_shows_expired_subscription_status_when_no_trial_or_paid(client):
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number="9725500000")
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert "תקופת הניסיון הסתיימה ⚠️" in resp.text


def test_account_hides_subscription_card_for_the_owner(client):
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number="9725500000")
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "OWNER_TELEGRAM_USER_ID", "222"),
    ):
        resp = client.get("/account", params={"uid": 222})

    assert "המנוי שלי 👑" not in resp.text
    assert "התראות 🔔" in resp.text  # notifications tile stays visible for the owner too


def test_account_notifications_toggle_flips_and_redirects_with_uid(client):
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number="9725500000", notifications_enabled=True)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post("/account/notifications", data={"uid": 222})

    assert resp.status_code == 303
    assert resp.headers["location"] == "/account?uid=222"
    assert user.notifications_enabled is False
    assert fake_session.committed is True


def test_account_notifications_toggle_falls_back_to_wid_when_no_uid(client):
    user = _FakeUser(id=2, whatsapp_phone_number="9725500000", notifications_enabled=False)

    class _WidSession(_FakeSession):
        def scalar(self, stmt):
            return None

    fake_session = _WidSession()
    with patch.object(website_main, "_get_user_by_wid", lambda session, wid: user):
        with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
            resp = client.post("/account/notifications", data={"wid": "9725500000"})

    assert resp.status_code == 303
    assert resp.headers["location"] == "/account?wid=9725500000"
    assert user.notifications_enabled is True


def test_account_renders_payment_history_when_payments_exist(client):
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number="9725500000")
    payments = [
        _FakePayment(
            "monthly", 40, "paid", dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
            paid_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
        ),
        _FakePayment("weekly", 15, "pending", dt.datetime(2026, 8, 15, tzinfo=dt.timezone.utc)),
    ]
    fake_session = _FakeSession(users_by_telegram_id={222: user}, payments=payments)
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert "היסטוריית תשלומים 📄" in resp.text
    assert "חודשי — ₪40" in resp.text
    assert "₪40" in resp.text
    assert "01/08/2026" in resp.text
    assert "✅ שולם" in resp.text
    assert "⏳ ממתין" in resp.text
    assert "15/08/2026" in resp.text


def test_account_hides_payment_history_section_when_no_payments(client):
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number="9725500000")
    fake_session = _FakeSession(users_by_telegram_id={222: user}, payments=[])
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert "היסטוריית תשלומים 📄" not in resp.text


# --- WhatsApp Message Template notification opt-in (2026-09-08) ---


def test_account_hides_whatsapp_notifications_toggle_when_whatsapp_not_linked(client):
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number=None)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert "התראות בווטסאפ" not in resp.text
    assert "/account/whatsapp-notifications" not in resp.text


def test_account_shows_whatsapp_notifications_toggle_off_by_default_when_whatsapp_linked(client):
    """Default False on a brand-new whatsapp_phone_number row — see models.py's own docstring on
    why this can't just inherit notifications_enabled's default-True."""
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number="9725500000")
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert "התראות בווטסאפ 💬" in resp.text
    assert "🔕 כבויות" in resp.text
    assert "הפעל התראות בווטסאפ" in resp.text


def test_account_shows_whatsapp_notifications_toggle_on_when_opted_in(client):
    user = _FakeUser(
        id=2, telegram_user_id=222, whatsapp_phone_number="9725500000",
        whatsapp_notifications_opted_in=True,
    )
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert "🔔 מופעלות" in resp.text
    assert "כבה התראות בווטסאפ" in resp.text


def test_account_whatsapp_notifications_toggle_flips_and_redirects_with_uid(client):
    user = _FakeUser(
        id=2, telegram_user_id=222, whatsapp_phone_number="9725500000",
        whatsapp_notifications_opted_in=False,
    )
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post("/account/whatsapp-notifications", data={"uid": 222})

    assert resp.status_code == 303
    assert resp.headers["location"] == "/account?uid=222"
    assert user.whatsapp_notifications_opted_in is True
    assert fake_session.committed is True


def test_account_whatsapp_notifications_toggle_falls_back_to_wid_when_no_uid(client):
    user = _FakeUser(id=2, whatsapp_phone_number="9725500000", whatsapp_notifications_opted_in=True)

    class _WidSession(_FakeSession):
        def scalar(self, stmt):
            return None

    fake_session = _WidSession()
    with patch.object(website_main, "_get_user_by_wid", lambda session, wid: user):
        with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
            resp = client.post("/account/whatsapp-notifications", data={"wid": "9725500000"})

    assert resp.status_code == 303
    assert resp.headers["location"] == "/account?wid=9725500000"
    assert user.whatsapp_notifications_opted_in is False


# --- i18n (2026-09-08 fix): this whole page was hardcoded Hebrew-only, unlike every other
# customer-facing page, so a non-Hebrew visitor saw a fully-Hebrew /account regardless of their
# own language setting. Confirms the fix actually renders translated content, not just that the
# Hebrew default (every other test above) is unchanged.


def test_account_renders_in_english_when_lang_param_is_set(client):
    user = _FakeUser(
        id=2, telegram_user_id=222, whatsapp_phone_number="9725500000",
        trial_ends_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2),
    )
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222, "lang": "en"})

    assert resp.status_code == 200
    assert "My Account" in resp.text
    assert "Notifications" in resp.text
    assert "Connected Channels" in resp.text
    assert "Trial period, until" in resp.text
    # the old hardcoded Hebrew strings must not leak through regardless of the chosen language
    assert "החשבון שלי" not in resp.text
    assert "התראות 🔔" not in resp.text


def test_account_renders_in_arabic_when_lang_param_is_set(client):
    user = _FakeUser(id=2, telegram_user_id=222, whatsapp_phone_number="9725500000")
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222, "lang": "ar"})

    assert resp.status_code == 200
    assert "حسابي" in resp.text
    assert "القنوات المرتبطة" in resp.text
