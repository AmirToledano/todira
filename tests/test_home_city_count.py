"""2026-11-04 (owner): the home page's "how many new flats came in in your city today" question also takes an optional
max budget and rooms, and answers with the matching flats of the last 24 hours and of the last 7 days
(website/main.py /api/city-count, static/home.js cityCheck)."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_ROOT = Path(__file__).resolve().parent.parent
_WEBSITE_DIR = _ROOT / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_city_count", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

import i18n as website_i18n  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_NEW_KEYS = ("landing.city_price_label", "landing.city_rooms_label", "landing.city_optional", "landing.city_week_n",
             "landing.city_week_1", "landing.city_match", "landing.city_match_0")


class _Session:
    def __init__(self, row):
        self.row = row
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        row = self.row
        return type("R", (), {"one": lambda self: row})()


@pytest.fixture
def fake_db(monkeypatch):
    session = _Session((42, 310))

    @contextmanager
    def _get_session():
        yield session

    monkeypatch.setattr(website_main, "get_session", _get_session)
    website_main._city_count_cache.clear()
    yield session
    website_main._city_count_cache.clear()


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_one_counted_query_gives_today_and_the_week(client, fake_db):
    resp = client.get("/api/city-count", params={"city": "חיפה", "price_max": "6,000", "rooms_min": "3"})
    assert resp.status_code == 200
    assert resp.json() == {"city": "חיפה", "today": 42, "week": 310}
    assert "max-age=300" in resp.headers["cache-control"]
    assert len(fake_db.statements) == 1
    sql = _sql(fake_db.statements[0])
    assert "listings.city = 'חיפה'" in sql
    assert "listings.price <= 6000" in sql and "listings.rooms >= 3.0" in sql
    assert "listings.deal_type != 'sale'" in sql  # a monthly budget is a rent
    assert "secs=>604800" in sql and "FILTER (WHERE" in sql  # 7 days, and the 24 hours counted inside it


def test_a_purchase_budget_counts_sales_and_no_budget_counts_everything(client, fake_db):
    client.get("/api/city-count", params={"city": "חיפה", "price_max": "2000000"})
    assert "listings.deal_type = 'sale'" in _sql(fake_db.statements[-1])
    client.get("/api/city-count", params={"city": "חיפה"})
    sql = _sql(fake_db.statements[-1])
    assert "deal_type" not in sql and "listings.price" not in sql and "listings.rooms" not in sql


def test_the_same_question_is_answered_from_the_cache(client, fake_db):
    for _ in range(3):
        client.get("/api/city-count", params={"city": "חיפה", "rooms_min": "2"})
    assert len(fake_db.statements) == 1


def test_bad_input_is_refused_or_ignored(client, fake_db):
    assert client.get("/api/city-count").status_code == 400
    assert client.get("/api/city-count", params={"city": "x" * 61}).status_code == 400
    assert client.get("/api/city-count", params={"city": "חיפה", "rooms_min": "abc"}).status_code == 400
    resp = client.get("/api/city-count", params={"city": "חיפה", "rooms_min": "99"})
    assert resp.status_code == 200 and "listings.rooms" not in _sql(fake_db.statements[-1])


def test_unavailable_when_the_database_fails(client, monkeypatch):
    @contextmanager
    def _broken():
        raise RuntimeError("db down")
        yield  # pragma: no cover

    website_main._city_count_cache.clear()
    monkeypatch.setattr(website_main, "get_session", _broken)
    assert client.get("/api/city-count", params={"city": "חיפה"}).status_code == 503


def test_the_home_page_has_the_two_optional_fields_and_the_texts(client):
    html = client.get("/?lang=he").text
    assert 'id="lp-city-price"' in html and 'id="lp-city-rooms"' in html
    strings = website_main._landing_js("he")["strings"]
    assert "{today}" in strings["city_match"] and "{week}" in strings["city_match"]


def test_the_new_texts_exist_in_every_language_without_dashes():
    T = website_i18n.TRANSLATIONS
    for key in _NEW_KEYS:
        assert set(T[key]) >= {"he", "en", "ru", "fr", "ar"}, key
    for code in ("es", "pt", "hi", "fil", "th", "zh"):
        data = json.loads((_WEBSITE_DIR / "i18n_langs" / f"{code}.json").read_text())
        for key in _NEW_KEYS:
            assert data.get(key), (code, key)
    texts = [v for key in _NEW_KEYS for v in T[key].values()]
    assert not any(ch in t for t in texts for ch in "—–·")
