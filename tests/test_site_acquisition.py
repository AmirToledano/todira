"""2026-11-02 (growth): the public channel link, links between city pages and a meta description per content page."""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_acquisition", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402
from i18n import SUPPORTED_LANGS, TRANSLATIONS  # noqa: E402

from todira_common import share  # noqa: E402

CHANNEL = "https://t.me/todira_dirot"
PAGE = {"city": "חיפה", "total": 155, "week": 28, "gone_days": None, "by_rooms": [], "neighborhoods": [], "newest": []}
CITIES = [{"city": f"עיר{i}", "count": 100 - i, "median3": None} for i in range(14)]
CITIES.insert(3, {"city": "חיפה", "count": 155, "median3": 4060})


class _NoDatabase:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(website_main, "get_session", _NoDatabase)
    monkeypatch.setattr(website_main.city_pages, "city_page", lambda session, city: PAGE)
    monkeypatch.setattr(website_main.city_pages, "city_index", lambda session: CITIES)
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def _channel_links(html: str) -> int:
    return html.count(f'href="{CHANNEL}"')


def test_the_channel_is_in_the_footer_and_at_the_end_of_the_rent_pages(client):
    assert _channel_links(client.get("/calculator?lang=he").text) == 1  # the footer only
    for path in ("/rent?lang=he", "/rent/חיפה?lang=he"):
        html = client.get(path).text
        assert _channel_links(html) == 2  # footer plus the line at the end of the page
        assert "הדירות הכי משתלמות של כל בוקר, בערוץ הטלגרם שלנו" in html


def test_the_shared_listing_page_links_the_channel(monkeypatch):
    listing = SimpleNamespace(
        id=7, price=4200, rooms=3, floor=None, floor_total=None, size_sqm=None, city="חיפה", neighborhood=None,
        street=None, has_parking=None, has_elevator=None, has_balcony=None, safe_room_type=None, description=None,
        image_urls=[], is_delisted=False,
    )

    @contextmanager
    def _session():
        yield SimpleNamespace(get=lambda model, pk: listing if pk == 7 else None, expunge=lambda obj: None)

    with patch.object(website_main, "get_session", _session), patch.object(website_main.activity, "record", lambda *a, **k: None):
        html = TestClient(website_main.app).get(share.share_path(7) + "?lang=he").text
    assert _channel_links(html) == 2
    assert 'data-track="channel_share"' in html


def test_a_city_page_links_up_to_twelve_other_cities_but_not_itself(client):
    html = client.get("/rent/חיפה?lang=he").text
    row = html.split('class="rent-more-links"', 1)[1].split("</p>", 1)[0]
    linked = re.findall(r'href="/rent/[^"]+">([^<]+)</a>', row)
    assert "ערים נוספות" in html
    assert "חיפה" not in linked
    assert linked == [c["city"] for c in CITIES if c["city"] != "חיפה"][:12]


def test_the_channel_clicks_are_counted():
    assert {"channel_footer", "channel_rent", "channel_rent_city", "channel_share"} <= website_main._CLICK_TARGETS


def _meta_description(html: str) -> str:
    return re.search(r'<meta name="description" content="([^"]*)"', html).group(1)


def test_each_content_page_has_its_own_meta_description(client):
    pages = ["/", "/moving-checklist", "/rental-contract-check", "/post", "/calculator", "/rent", "/rent/חיפה"]
    for lang in SUPPORTED_LANGS:
        descriptions = [_meta_description(client.get(f"{path}?lang={lang}").text) for path in pages]
        assert len(set(descriptions)) == len(pages), (lang, descriptions)
        assert all(0 < len(d) <= 160 for d in descriptions[1:]), (lang, descriptions)


def test_the_new_texts_exist_in_every_language_without_long_dashes():
    keys = ["channel.footer_link", "channel.page_link", "city.more_cities", "meta.desc_calculator", "meta.desc_moving",
            "meta.desc_contract", "meta.desc_post"]
    for key in keys:
        assert set(TRANSLATIONS[key]) == set(SUPPORTED_LANGS), key
        for text in TRANSLATIONS[key].values():
            assert "—" not in text and "–" not in text, key
            assert len(text) <= 160, key
