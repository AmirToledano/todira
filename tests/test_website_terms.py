"""Tests for website/main.py's /terms — 2026-09-25 conversion into the fifth React island
(website/landing-react/, see its README's "How it's wired into the site" section), the same
pattern established for /about, /accessibility, and /privacy in their own test files.

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

_spec = importlib.util.spec_from_file_location("website_main_terms", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_terms_renders_react_island(client):
    """Mirrors test_privacy_renders_react_island's own reasoning: checks what the server actually
    still controls (config injection, the correct per-entry bundle reference) rather than full
    DOM content, which is a frontend concern verified separately."""
    resp = client.get("/terms")

    assert resp.status_code == 200
    assert 'id="root"' in resp.text
    assert "/static/landing/assets/" in resp.text
    assert "/static/landing/assets/terms-" in resp.text  # its OWN entry, not another page's


def test_terms_config_matches_requested_language(client):
    resp = client.get("/terms?lang=en")

    assert resp.status_code == 200
    assert 'lang: "en"' in resp.text
    assert 'dir: "ltr"' in resp.text


def test_terms_page_title(client):
    resp = client.get("/terms?lang=en")

    assert resp.status_code == 200
    assert "<title>" in resp.text
