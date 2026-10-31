"""2026-10-31: a page per city for people searching Google (website/city_pages.py)."""
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

_spec = importlib.util.spec_from_file_location("website_main_city_pages", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402

PAGE = {
    "city": "חיפה", "total": 155, "week": 28, "gone_days": 9,
    "by_rooms": [{"rooms": 3, "median": 4060, "count": 51}, {"rooms": 5, "median": 5190, "count": 12}],
    "neighborhoods": [{"name": "הדר", "median": 3500, "count": 12}],
    "newest": [{"price": 3900, "rooms": 3, "neighborhood": "הדר", "street": None, "size": 70,
                "photo": "https://example.invalid/p.jpg", "link": "/s/abc", "first_seen_at": None}],
}


class _NoDatabase:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(website_main, "get_session", _NoDatabase)
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_a_city_page_shows_our_numbers_and_the_way_in(client, monkeypatch):
    monkeypatch.setattr(website_main.city_pages, "city_page", lambda session, city: PAGE)
    resp = client.get("/rent/חיפה?lang=he")
    assert resp.status_code == 200
    text = resp.text
    assert "<title>דירות להשכרה בחיפה: מחירים עדכניים ודירות חדשות | טודירה</title>" in text
    assert "לפי 155 דירות שעלו ב־30 הימים האחרונים" in text  # the meta description
    assert "חצי מהדירות כאן ירדו מהאוויר תוך 9 ימים." in text
    assert "₪4,060" in text and "5+" in text and "הדר" in text
    assert 'href="/s/abc"' in text and "t.me/AmirDirotBot?start=rent_city" in text


def test_no_page_for_a_place_that_is_not_a_locality_or_has_too_few_flats(client, monkeypatch):
    monkeypatch.setattr(website_main.city_pages, "city_page", lambda session, city: None)
    assert client.get("/rent/not-a-city").status_code == 404
    assert client.get("/rent/חיפה").status_code == 404


def test_the_index_links_every_city(client, monkeypatch):
    monkeypatch.setattr(website_main.city_pages, "city_index", lambda session: [
        {"city": "תל אביב יפו", "count": 900, "median3": 7200}, {"city": "חיפה", "count": 155, "median3": None},
    ])
    text = client.get("/rent?lang=he").text
    assert "/rent/%D7%AA%D7%9C%20%D7%90%D7%91%D7%99%D7%91%20%D7%99%D7%A4%D7%95" in text and "₪7,200" in text
    sitemap = client.get("/sitemap.xml").text
    assert "/rent/%D7%97%D7%99%D7%A4%D7%94" in sitemap and "/rent<" in sitemap
