"""Tests for website/main.py's /about — 2026-09-25 conversion into the second React island
(website/landing-react/, see its README's "How it's wired into the site" section), the same
pattern established for / (home) in test_website_home.py.

Same importlib-loading approach as the other website test files (see test_website_paid_access.py's
own comment).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_about", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_about_renders_react_island(client):
    """Mirrors test_home_shows_whatsapp_cta_when_configured's own reasoning: checks what the
    server actually still controls (config injection, the correct per-entry bundle reference)
    rather than full DOM content, which is a frontend concern verified separately."""
    resp = client.get("/about")

    assert resp.status_code == 200
    assert 'id="root"' in resp.text
    assert "/static/landing/assets/" in resp.text
    assert "/static/landing/assets/about-" in resp.text  # about's OWN entry, not home's index-*


def test_about_config_matches_requested_language(client):
    resp = client.get("/about?lang=en")

    assert resp.status_code == 200
    assert 'lang: "en"' in resp.text
    assert 'dir: "ltr"' in resp.text


def test_about_page_title(client):
    resp = client.get("/about?lang=en")

    assert resp.status_code == 200
    assert "<title>" in resp.text
