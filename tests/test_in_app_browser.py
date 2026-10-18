"""Visitors inside a social app's built-in browser (2026-10-17, the owner linked the site from his Instagram bio):
a banner with a button that opens the same page in the real browser, signed in via a one-time handoff link."""
from __future__ import annotations

import contextlib
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_in_app", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402
from todira_common.uid_token import generate_handoff_token  # noqa: E402

INSTAGRAM_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148 Instagram 350.0.0.0.0 (iPhone15,2; iOS 18_0; he_IL; he; scale=3.00; 1179x2556)"
)
INSTAGRAM_ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
    "Chrome/120.0.0.0 Mobile Safari/537.36 Instagram 350.0.0.0.0 Android"
)
SAFARI = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/18.0 Mobile/15E148 Safari/604.1"
)


class _FakeSession:
    def get(self, model, user_id):
        return object() if user_id == 7 else None


@contextlib.contextmanager
def _fake_get_session():
    yield _FakeSession()


def _client():
    return TestClient(website_main.app, follow_redirects=False)


def test_no_banner_in_a_regular_browser():
    resp = _client().get("/terms", headers={"user-agent": SAFARI})
    assert resp.status_code == 200
    assert "inapp-banner" not in resp.text


def test_instagram_on_iphone_gets_a_banner_that_opens_safari():
    resp = _client().get("/terms", headers={"user-agent": INSTAGRAM_IPHONE})
    assert 'id="inapp-banner"' in resp.text
    assert 'href="x-safari-https://testserver/terms"' in resp.text
    assert "Instagram" in resp.text


def test_instagram_on_android_gets_a_banner_that_opens_chrome():
    resp = _client().get("/terms", headers={"user-agent": INSTAGRAM_ANDROID})
    assert "intent://testserver/terms#Intent;scheme=https;package=com.android.chrome;" in resp.text
    assert "S.browser_fallback_url=https%3A%2F%2Ftestserver%2Fterms;end" in resp.text


def test_the_site_is_hebrew_even_when_the_phone_is_set_to_english():
    resp = _client().get("/terms", headers={"user-agent": INSTAGRAM_IPHONE, "accept-language": "en-US,en;q=0.9"})
    assert 'lang="he"' in resp.text


def test_handoff_signs_the_new_browser_in_once_and_goes_on():
    token = generate_handoff_token(7)
    with patch.object(website_main, "get_session", _fake_get_session):
        first = _client().get(f"/auth/handoff?h={token}&next=/account")
        second = _client().get(f"/auth/handoff?h={token}&next=/account")

    assert first.status_code == 303 and first.headers["location"] == "/account"
    assert "session=" in first.headers.get("set-cookie", "")
    assert second.status_code == 303
    assert "session=" not in second.headers.get("set-cookie", "")  # used tokens never sign in again


def test_handoff_rejects_a_forged_token_and_an_outside_redirect():
    with patch.object(website_main, "get_session", _fake_get_session):
        resp = _client().get("/auth/handoff?h=forged&next=//evil.example")

    assert resp.headers["location"] == "/apartments"
    assert "session=" not in resp.headers.get("set-cookie", "")


def test_signed_in_visitor_gets_a_handoff_link_in_the_banner():
    token = generate_handoff_token(7)
    client = _client()
    with patch.object(website_main, "get_session", _fake_get_session), patch.object(
        website_main, "_current_user_summary", lambda request: {"telegram_user_id": None, "first_name": "x", "telegram_username": None}
    ):
        client.get(f"/auth/handoff?h={token}&next=/terms")
        resp = client.get("/terms", headers={"user-agent": INSTAGRAM_IPHONE})

    assert 'href="x-safari-https://testserver/auth/handoff?h=' in resp.text
    assert "&amp;next=/terms" in resp.text


def test_the_button_also_copies_the_plain_link_and_has_steps_for_when_the_app_blocks_it():
    # 2026-10-18 (owner: "the open in browser button doesn't work"): Instagram on iPhone ignores x-safari-.
    # /terms, not /apartments: no database in CI, and the query string is what matters here
    resp = _client().get("/terms?listing=5", headers={"user-agent": INSTAGRAM_IPHONE})
    assert 'var copyUrl = "https://testserver/terms?listing=5";' in resp.text
    assert 'href="x-safari-https://testserver/terms?listing=5"' in resp.text
    assert 'id="inapp-steps" hidden' in resp.text
    assert "ספארי" in resp.text  # the iPhone steps, not Android's


def test_android_gets_the_android_steps():
    resp = _client().get("/terms", headers={"user-agent": INSTAGRAM_ANDROID})
    assert "⋮" in resp.text and "ספארי" not in resp.text


def test_the_handoff_link_keeps_the_page_query():
    token = generate_handoff_token(7)
    client = _client()
    with patch.object(website_main, "get_session", _fake_get_session), patch.object(
        website_main, "_current_user_summary", lambda request: {"telegram_user_id": None, "first_name": "x", "telegram_username": None}
    ):
        client.get(f"/auth/handoff?h={token}&next=/terms")
        resp = client.get("/terms?lang=he", headers={"user-agent": INSTAGRAM_IPHONE})
    assert "next=/terms%3Flang%3Dhe" in resp.text
