"""2026-10-31 (owner-approved drafts): the moving checklist and the rental-contract page (website/guides.py)."""
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

_spec = importlib.util.spec_from_file_location("website_main_guides", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

import guides  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_the_moving_checklist_has_every_line_as_a_checkbox(client):
    resp = client.get("/moving-checklist?lang=he")
    assert resp.status_code == 200
    assert "רשימה למעבר דירה" in resp.text
    lines = sum(len(section["items"]) for section in guides.GUIDES["moving"]["sections"])
    assert resp.text.count('type="checkbox"') == lines


def test_the_contract_page_states_the_checked_numbers_and_links_its_sources(client):
    resp = client.get("/rental-contract-check?lang=he")
    assert resp.status_code == 200
    for fact in ("שליש", "60 יום", "30 יום", "3 ימים", "20,000 ₪"):
        assert fact in resp.text
    assert resp.text.count("kolzchut.org.il") == 2
    assert 'type="checkbox"' not in resp.text


def test_every_text_exists_in_every_language_and_has_no_long_dash():
    def texts(entry):
        if isinstance(entry, dict) and "he" in entry:
            yield entry
        elif isinstance(entry, dict):
            for value in entry.values():
                yield from texts(value)
        elif isinstance(entry, (list, tuple)):
            for value in entry:
                yield from texts(value)

    for entry in [*texts(guides.GUIDES), guides.CTA, guides.SOURCES_TITLE]:
        assert set(entry) == {"he", "en", "ru", "fr", "ar"}
        assert not any("—" in value for value in entry.values())


def test_the_pages_are_in_the_footer_and_the_sitemap(client):
    home = client.get("/calculator?lang=he").text
    assert 'href="/moving-checklist"' in home and 'href="/rental-contract-check"' in home
    sitemap = client.get("/sitemap.xml").text
    assert "/moving-checklist" in sitemap and "/rental-contract-check" in sitemap
