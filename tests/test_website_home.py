"""Tests for website/main.py's / (home) — 2026-09-06 addition of a WhatsApp CTA alongside the
original Telegram-only one, in both the hero and the bottom footer-cta section. Found live: the
homepage's hero/footer CTAs only ever offered Telegram, even though the product has since grown a
WhatsApp bot and direct website browsing — a Telegram-only funnel no longer reflected the real
entry points.

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

_spec = importlib.util.spec_from_file_location("website_main_home", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_home_shows_whatsapp_cta_when_configured(client):
    with patch.object(website_main, "WHATSAPP_PUBLIC_NUMBER", "972500000000"):
        resp = client.get("/")

    assert resp.status_code == 200
    assert resp.text.count("wa.me/972500000000") == 2  # hero + footer-cta sections
    assert "https://t.me/AmirDirotBot" in resp.text  # Telegram CTA stays alongside it


def test_home_hides_whatsapp_cta_when_not_configured(client):
    with patch.object(website_main, "WHATSAPP_PUBLIC_NUMBER", ""):
        resp = client.get("/")

    assert resp.status_code == 200
    assert "wa.me" not in resp.text
    assert "https://t.me/AmirDirotBot" in resp.text
