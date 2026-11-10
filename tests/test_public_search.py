"""2026-11-04 (owner): /search, results before signing in (website/main.py's public_search).

A visitor with no account picks a city, a top price and rooms, and sees the real count of matching live flats from the
last 7 days plus up to 6 of the newest as locked cards (no link to the original ad), then the bot and Google sign-in.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_public_search", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402

from todira_common import listing_matches  # noqa: E402

CITY = "תל אביב יפו"
NOW = dt.datetime.now(dt.timezone.utc)


def _listing(i: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=i, url=f"https://ads.example.invalid/item/{i}", source="yad2", city=CITY, neighborhood="פלורנטין",
        street="הרצל", price=5000 + i, previous_price=None, rooms=3, floor=2, floor_total=None, size_sqm=70,
        property_type="apartment", description="דירה מוארת", image_urls=[], latitude=None, longitude=None,
        posted_at=NOW, first_seen_at=NOW, is_broker_listing=False, reposted_from_at=None, move_in_date=None,
        move_in_note=None, has_parking=False, has_elevator=False, has_balcony=False, pets_allowed=False,
        is_renovated=False, safe_room_type=None, furniture=None, is_delisted=False, also_on=None,
    )


class _NoDatabase:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def scan(monkeypatch):
    """Fakes the match scan with `n` matching rows; records what the preview asked it for."""
    calls = []
    state = {"n": 9}

    def fake_rows(session, draft, hidden_ids=None, *, since=None, scan_limit=None):
        calls.append({"draft": draft, "since": since, "scan_limit": scan_limit})
        return [SimpleNamespace(id=i) for i in range(1, state["n"] + 1)]

    monkeypatch.setattr(website_main, "get_session", _NoDatabase)
    monkeypatch.setattr(website_main, "matching_listing_rows", fake_rows)
    monkeypatch.setattr(website_main, "load_listings", lambda session, ids: [_listing(i) for i in ids])
    website_main._public_search_cache.clear()
    return calls, state


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_the_count_is_every_match_and_at_most_six_cards_show(client, scan):
    calls, _state = scan
    resp = client.get("/search", params={"cities": CITY, "price_max": "6,500", "rooms_min": "2", "rooms_max": "3.5", "lang": "he"})
    assert resp.status_code == 200
    text = resp.text
    assert f"9 דירות ב{CITY} שמתאימות לזה עלו ב־7 הימים האחרונים." in text
    assert text.count('class="listing-card') == 6
    assert "ועוד 3 מחכות לך אחרי ההרשמה." in text
    # the /filter form's parsing, one city, a 7-day window and a capped scan
    (call,) = calls
    draft = call["draft"]
    assert draft.cities == [CITY] and draft.price_max == 6500 and draft.rooms_min == 2.0 and draft.rooms_max == 3.5
    assert draft.deal_type == "rent" and draft.keywords == [] and draft.flexible_match is False
    assert call["scan_limit"] == website_main._PUBLIC_SEARCH_SCAN_CAP
    assert dt.timedelta(days=6, hours=23) < NOW - call["since"] < dt.timedelta(days=7, minutes=5)


def test_one_and_zero_matches_read_naturally(client, scan):
    _calls, state = scan
    state["n"] = 1
    assert f"דירה אחת ב{CITY} שמתאימה לזה" in client.get("/search", params={"cities": CITY}).text
    state["n"] = 0
    website_main._public_search_cache.clear()
    text = client.get("/search", params={"cities": CITY, "price_max": "1000"}).text
    assert f"לא עלתה ב{CITY} דירה" in text and 'class="listing-card' not in text


def test_a_full_scan_says_plus_rather_than_an_exact_number(client, scan, monkeypatch):
    _calls, state = scan
    monkeypatch.setattr(website_main, "_PUBLIC_SEARCH_SCAN_CAP", 20)
    state["n"] = 20
    assert "20+ דירות" in client.get("/search", params={"cities": CITY, "lang": "he"}).text


def test_no_link_to_the_original_ad_and_no_source_name(client, scan):
    text = client.get("/search", params={"cities": CITY}).text
    assert "ads.example.invalid" not in text
    assert "source-badge" not in text and "yad2" not in text.lower()
    assert "/go/" not in text and 'action="/react"' not in text
    # the locked button leads to signing in, not to a payment page this visitor can't use yet
    assert 'class="view-btn locked" href="/login?next=/filter"' in text


def test_the_two_ways_in_and_noindex(client, scan):
    resp = client.get("/search", params={"cities": CITY})
    assert 'href="https://t.me/AmirDirotBot?start=site_preview"' in resp.text
    assert 'href="/login?next=/filter"' in resp.text
    assert resp.headers["X-Robots-Tag"] == "noindex"
    assert '<meta name="robots" content="noindex">' in resp.text
    assert "@AmirDirotBot" not in resp.text  # the bot is linked on words, its @name never written out
    assert "Disallow: /search" in client.get("/robots.txt").text


def test_no_city_shows_only_the_form_and_never_scans(client, scan):
    calls, _state = scan
    for params in ({}, {"cities": "not a place"}):
        resp = client.get("/search", params=params)
        assert resp.status_code == 200 and 'name="cities"' in resp.text and 'name="price_max"' in resp.text
        assert 'class="listing-card' not in resp.text
    assert calls == []


def test_the_same_question_twice_is_answered_from_memory(client, scan):
    calls, _state = scan
    client.get("/search", params={"cities": CITY, "price_max": "7000"})
    client.get("/search", params={"cities": CITY, "price_max": "7000"})
    assert len(calls) == 1


def test_a_visitor_on_apartments_is_sent_to_the_preview(client, monkeypatch):
    monkeypatch.setattr(website_main, "get_session", _NoDatabase)
    monkeypatch.setattr(website_main, "_resolve_user", lambda request, session, uid: None)
    resp = client.get("/apartments")
    assert resp.status_code == 303 and resp.headers["location"] == "/search"
    resp = client.get("/apartments", params={"city": "חיפה", "lang": "en"})
    assert resp.headers["location"] == "/search?cities=%D7%97%D7%99%D7%A4%D7%94&lang=en"
    # a deep link to one listing still asks to sign in, as before
    resp = client.get("/apartments", params={"listing": 5})
    assert resp.status_code == 200 and 'class="btn gold" href="/login"' in resp.text


def test_the_home_page_links_to_the_preview(client):
    text = client.get("/?lang=he").text
    assert 'href="/search"' in text and "לראות דירות עכשיו" in text


def test_the_scan_window_and_cap_reach_the_sql():
    captured = {}

    class _Session:
        def execute(self, query):
            captured["sql"] = str(query.compile(dialect=postgresql.dialect()))
            return []

    draft = website_main._blank_filter()
    draft.cities = [CITY]
    listing_matches.matching_listing_rows(_Session(), draft, since=NOW, scan_limit=3000)
    assert "listings.first_seen_at >=" in captured["sql"] and "LIMIT" in captured["sql"]
    listing_matches.matching_listing_rows(_Session(), draft)
    assert "LIMIT" not in captured["sql"] and "first_seen_at >=" not in captured["sql"]


def test_a_broad_scan_is_read_in_batches_and_keeps_no_descriptions():
    """2026-11-09 (owner: "save and search" with everything set to "all" got stuck): every live listing, descriptions
    included, was read into the bot's memory at once."""
    captured = {}
    keys = [c.key for c in listing_matches.MATCH_COLUMNS]
    values = dict.fromkeys(keys)
    values.update(id=7, deal_type="rent", city=CITY, price=4000, description="מרפסת גדולה", first_seen_at=NOW)
    row = SimpleNamespace(_mapping=values, **values)  # a database row: attributes plus _mapping

    class _Session:
        def execute(self, query):
            captured["yield_per"] = query.get_execution_options().get("yield_per")
            return [row]

    draft = website_main._blank_filter()
    draft.cities = [CITY]
    rows = listing_matches.matching_listing_rows(_Session(), draft)
    assert captured["yield_per"] == 2000
    assert [r.id for r in rows] == [7] and rows[0].price == 4000 and rows[0].description is None


def test_descriptions_are_fetched_only_for_a_search_with_keywords():
    """2026-11-09 (owner: /apartments stayed blank with a search set to "all"): every candidate's description was
    fetched and sorted in the database although only keywords read it."""
    captured = {}

    class _Session:
        def execute(self, query):
            captured["sql"] = str(query.compile(dialect=postgresql.dialect()))
            return []

    draft = website_main._blank_filter()
    draft.keywords = []
    listing_matches.matching_listing_rows(_Session(), draft)
    assert "left(listings.description" in captured["sql"]  # only the opening the parking/storage check reads
    draft.keywords = ["מרפסת"]
    listing_matches.matching_listing_rows(_Session(), draft)
    assert "listings.description" in captured["sql"] and "left(listings.description" not in captured["sql"]
