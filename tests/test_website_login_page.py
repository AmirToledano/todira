"""Tests for website/main.py's /login — a dedicated screen (2026-09-05 request) with Google/
Telegram/WhatsApp shown as three separate, equally prominent options, replacing the header's own
small Google-only button as the primary way an anonymous visitor identifies themselves.

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


def test_login_page_shows_all_three_options_when_whatsapp_configured(client):
    with patch.object(website_main, "WHATSAPP_PUBLIC_NUMBER", "972500000000"):
        resp = client.get("/login")

    assert resp.status_code == 200
    assert "/auth/google/start" in resp.text
    assert "https://t.me/AmirDirotBot" in resp.text
    assert "wa.me/972500000000" in resp.text


def test_login_page_hides_whatsapp_option_when_not_configured(client):
    with patch.object(website_main, "WHATSAPP_PUBLIC_NUMBER", ""):
        resp = client.get("/login")

    assert resp.status_code == 200
    assert "wa.me" not in resp.text
    # the other two options are unaffected
    assert "/auth/google/start" in resp.text
    assert "https://t.me/AmirDirotBot" in resp.text


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
    assert 'href="/auth/google/start?next=/apartments"' in resp.text
