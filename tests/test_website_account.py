"""Tests for website/main.py's /account — the cross-channel linking page (dorin_common/
channel_link.py): shows which channels (Telegram/WhatsApp/Google) are already linked to the
resolved user, and generates a fresh code + deep links for whichever aren't.

Same importlib-loading approach as test_website_paid_access.py (see that file's comment) —
website/main.py shares a basename with scraper/main.py so it can't go through a bare `import main`.
"""
from __future__ import annotations

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
    def __init__(self, id, telegram_user_id=None, whatsapp_phone_number=None, google_sub=None):
        self.id = id
        self.telegram_user_id = telegram_user_id
        self.whatsapp_phone_number = whatsapp_phone_number
        self.google_sub = google_sub


class _FakeSession:
    def __init__(self, users_by_telegram_id=None):
        self._by_telegram_id = users_by_telegram_id or {}
        self.committed = False

    def scalar(self, stmt):
        for user in self._by_telegram_id.values():
            return user
        return None

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

    assert resp.text.count('class="channel-status connected"') == 3  # all 3 channels linked


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
