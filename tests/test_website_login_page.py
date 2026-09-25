"""Tests for website/main.py's /login — a dedicated screen (2026-09-05 request) with Google/
Telegram/WhatsApp shown as three separate, equally prominent options, replacing the header's own
small Google-only button as the primary way an anonymous visitor identifies themselves.

2026-09-25: /login became the site's seventh React island (website/landing-react/login.html) —
same pattern as about/accessibility/privacy/terms/contact. GET tests now check what the server
actually still controls (config injection into window.__TODIRA_PAGE__, the correct bundle
reference) rather than server-rendered `<a href>` markup, which is a frontend concern verified
separately (Playwright, during development) — same reasoning as the other converted pages' own
test files.

Same importlib-loading approach as the other website test files (see test_website_paid_access.py's
own comment).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_login_page", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_login_page_renders_react_island(client):
    resp = client.get("/login")

    assert resp.status_code == 200
    assert 'id="root"' in resp.text
    assert "/static/landing/assets/" in resp.text
    assert "/static/landing/assets/login-" in resp.text  # its OWN entry, not another page's


def test_login_page_injects_whatsapp_number_when_configured(client):
    with patch.object(website_main, "WHATSAPP_PUBLIC_NUMBER", "972500000000"):
        resp = client.get("/login")

    assert resp.status_code == 200
    assert 'whatsappPublicNumber: "972500000000"' in resp.text


def test_login_page_redirects_already_logged_in_visitor():
    from starlette.requests import Request as StarletteRequest

    request = StarletteRequest({"type": "http", "session": {"user_id": 7}})
    resp = website_main.login(request, next="/liked")

    assert resp.status_code == 303
    assert resp.headers["location"] == "/liked"


def test_login_page_next_param_is_sanitized_by_safe_next(client):
    resp = client.get("/login", params={"next": "https://evil.example/phish"})
    assert resp.status_code == 200
    # _safe_next falls back to /apartments for any non-relative target
    assert "next: \"/apartments\"" in resp.text


def test_login_page_injects_uid_for_the_react_form(client):
    resp = client.get("/login", params={"uid": 123456})
    assert resp.status_code == 200
    assert "uid: 123456" in resp.text


def test_login_page_injects_null_uid_when_none_given(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "uid: null" in resp.text


def test_login_page_next_is_json_encoded_not_a_raw_hand_written_string(client):
    """2026-09-25: `next` is the first value injected into window.__TODIRA_PAGE__ across any
    converted page that's genuinely attacker-influenceable text, not a fixed-whitelist string
    (lang/dir), an int (uid), or a trusted env var (whatsappPublicNumber) — _safe_next() only
    requires it start with a single "/", it doesn't restrict the character set otherwise. A
    hand-written `next: "{{ next }}"` would rely on Jinja's HTML-entity autoescaping alone, which
    is NOT JS-string-safe in general; `| tojson` (see login.html's own comment) is what actually
    makes this safe — proper JSON/JS-string escaping, including `<`/`>` so a `next` value can never
    break out of the inline <script> block via a literal quote or a `</script>` sequence."""
    resp = client.get("/login", params={"next": '/foo"};alert(1);//'})
    assert resp.status_code == 200
    assert 'next: "/foo\\"};alert(1);//"' in resp.text
    assert "};alert(1);//\";" not in resp.text  # would indicate a real string-literal breakout


def test_login_page_renders_in_english_when_lang_param_is_set(client):
    """2026-09-08 fix: this whole page was hardcoded Hebrew-only, unlike every other
    customer-facing page — confirms the fix actually renders translated content."""
    resp = client.get("/login", params={"lang": "en"})

    assert resp.status_code == 200
    assert 'lang: "en"' in resp.text
    assert 'dir: "ltr"' in resp.text
