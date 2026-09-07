"""Tests for the 2026-09-07 SEO additions: /robots.txt, /sitemap.xml, and base.html's canonical/
hreflang tags + the landscape og-image. Found live during a full audit that none of this existed
at all — no robots.txt (crawlers had no signal to stay off personalized/behind-auth pages, and no
pointer to a sitemap), no canonical/hreflang (nothing told search engines that /apartments?lang=en
and the Hebrew default are the same page in different languages), and og:image pointed straight at
the tall-portrait brand photo instead of a proper 1200x630 landscape crop.

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

_spec = importlib.util.spec_from_file_location("website_main_seo", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_robots_txt_disallows_personalized_pages_and_points_at_sitemap(client):
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "Disallow: /apartments" in resp.text
    assert "Disallow: /account" in resp.text
    assert "Disallow: /admin" in resp.text
    assert "Sitemap: http://testserver/sitemap.xml" in resp.text


def test_sitemap_xml_lists_only_public_pages(client):
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert "xml" in resp.headers["content-type"]
    for path in ("<loc>http://testserver/</loc>", "/login", "/contact", "/terms", "/privacy"):
        assert path in resp.text
    assert "/apartments" not in resp.text
    assert "/admin" not in resp.text


def test_home_page_has_canonical_and_hreflang_for_every_language(client):
    resp = client.get("/")
    assert '<link rel="canonical" href="http://testserver/">' in resp.text
    for lang in ("he", "en", "ru", "fr", "ar"):
        assert f'hreflang="{lang}"' in resp.text
    assert 'hreflang="x-default"' in resp.text


def test_non_default_language_canonical_and_hreflang_carry_the_lang_param(client):
    resp = client.get("/", params={"lang": "en"})
    assert '<link rel="canonical" href="http://testserver/?lang=en">' in resp.text
    assert 'hreflang="en" href="http://testserver/?lang=en"' in resp.text
    # the Hebrew default variant must still point at the bare (no ?lang=) URL
    assert 'hreflang="he" href="http://testserver/">' in resp.text


def test_og_image_points_at_the_landscape_crop_not_the_portrait_brand_photo(client):
    resp = client.get("/")
    assert 'property="og:image" content="http://testserver/static/og-image.jpg' in resp.text
    assert 'property="og:image" content="http://testserver/static/todira-brand.webp' not in resp.text
    assert '<meta property="og:image:width" content="1200">' in resp.text
    assert '<meta property="og:image:height" content="630">' in resp.text
