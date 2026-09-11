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
    # hero + footer-cta sections + the site-wide footer's own WhatsApp link (2026-09-07, base.html)
    assert resp.text.count("wa.me/972500000000") == 3
    assert "https://t.me/AmirDirotBot" in resp.text  # Telegram CTA stays alongside it


def test_home_hides_whatsapp_cta_when_not_configured(client):
    with patch.object(website_main, "WHATSAPP_PUBLIC_NUMBER", ""):
        resp = client.get("/")

    assert resp.status_code == 200
    assert "wa.me" not in resp.text
    assert "https://t.me/AmirDirotBot" in resp.text


def test_home_page_shows_ai_understanding_demo(client):
    """2026-09-10 addition: a static before/after visual under feature1 (typed query -> parsed
    chips). The query text is a fixed Hebrew example (matches feature1_body's own "in Hebrew"
    framing) and stays Hebrew regardless of ?lang=; only the chip labels translate."""
    resp = client.get("/", params={"lang": "en"})

    assert resp.status_code == 200
    assert "2-3 חדרים בתל אביב עד 6000 שקל" in resp.text
    assert "Tel Aviv" in resp.text
    assert "2-3 rooms" in resp.text
    assert "Up to ₪6,000" in resp.text


def test_home_page_has_valid_organization_and_website_json_ld(client):
    # Found live 2026-09-07: nothing on the site told search engines what kind of thing "טודירה"
    # IS (an Organization/WebSite, not just a page title) — no structured basis for a rich result.
    import json
    import re

    resp = client.get("/")
    match = re.search(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>', resp.text, re.DOTALL
    )
    assert match is not None, "no JSON-LD script tag found on the home page"

    data = json.loads(match.group(1))
    types = {node["@type"] for node in data["@graph"]}
    assert types == {"Organization", "WebSite"}
    for node in data["@graph"]:
        assert node["url"] == "http://testserver/"
