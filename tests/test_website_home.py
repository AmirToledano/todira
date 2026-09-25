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

import i18n as website_i18n  # noqa: E402 — TRANSLATIONS isn't re-exported by main.py itself

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_home_shows_whatsapp_cta_when_configured(client):
    """2026-09-25: the home page's hero/footer-cta WhatsApp+Telegram buttons moved from
    server-rendered HTML into the React island (website/landing-react/) — see main.py's
    _landing_react_assets()/home() and templates/home.html's own comment on the swap. This test
    now checks what the server actually still controls: the config the React app reads
    (window.__TODIRA_PAGE__.whatsappPublicNumber) is the right value, and the React bundle itself
    is referenced. Whether the React app then renders the right wa.me link from that config is a
    frontend concern, verified separately (manual/Playwright checks during development, not this
    Python suite — this repo's test suite has no browser-rendering dependency anywhere else
    either)."""
    with patch.object(website_main, "WHATSAPP_PUBLIC_NUMBER", "972500000000"):
        resp = client.get("/")

    assert resp.status_code == 200
    assert 'whatsappPublicNumber: "972500000000"' in resp.text
    assert 'id="root"' in resp.text
    assert "/static/landing/assets/" in resp.text  # the built React bundle is actually referenced


def test_home_hides_whatsapp_cta_when_not_configured(client):
    with patch.object(website_main, "WHATSAPP_PUBLIC_NUMBER", ""):
        resp = client.get("/")

    assert resp.status_code == 200
    assert 'whatsappPublicNumber: ""' in resp.text


def test_react_landing_content_json_matches_i18n_py(client):
    """2026-09-10's static before/after visual under feature1 (typed query -> parsed chips), and
    the rest of the home page's marketing copy, is now rendered by the React island
    (website/landing-react/) reading a build-time export, landing-react/src/content.json — not
    server-side HTML — see test_home_shows_whatsapp_cta_when_configured's own comment on why this
    suite checks the server's contract instead of full-page DOM content.

    What this test guards against: content.json is a generated file (a one-off export from
    TRANSLATIONS at the time landing-react was built), not auto-synced on every i18n.py edit — a
    later change to a home.*/footer.*/cookies.*/whatsapp.* string in i18n.py with nobody
    re-running that export would leave the live site showing stale copy with no test failure to
    catch it. Comparing every exported key's every language against the live TRANSLATIONS dict
    (the actual source of truth _render()'s t() reads from) directly catches that drift, unlike
    checking a few hardcoded expected strings against content.json alone would."""
    import json

    content = json.loads((_WEBSITE_DIR / "landing-react" / "src" / "content.json").read_text(encoding="utf-8"))
    assert content, "content.json is empty — was it ever generated?"

    for key, translations in content.items():
        assert key in website_i18n.TRANSLATIONS, f"{key} in content.json no longer exists in i18n.py's TRANSLATIONS"
        for lang, text in translations.items():
            assert website_i18n.TRANSLATIONS[key].get(lang) == text, (
                f"content.json[{key!r}][{lang!r}] is stale — doesn't match the live i18n.py value; "
                "re-run the content.json export (see website/landing-react/README or main.py's own "
                "landing-react comment)"
            )


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
