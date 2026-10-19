"""2026-10-19 home page redesign (templates/home.html, static/home.js): the new page, its live map data, and the switch
back to the previous page (owner: "keep the old site so I can bring it back")."""
from __future__ import annotations

import importlib.util
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_home_redesign", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

import i18n as website_i18n  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

T = website_i18n.TRANSLATIONS


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


@pytest.fixture(autouse=True)
def _fresh_map_cache(monkeypatch):
    monkeypatch.delenv("HOME_DESIGN", raising=False)
    website_main._home_map_cache.update(at=0.0, value=None)
    yield
    website_main._home_map_cache.update(at=0.0, value=None)


def test_the_new_home_page_is_the_default(client):
    resp = client.get("/?lang=he")
    assert resp.status_code == 200
    assert T["landing.h1"]["he"] in resp.text
    assert "/static/home.js" in resp.text and "/static/home.css" in resp.text
    assert 'id="root"' not in resp.text  # not the React page
    assert resp.text.count("<h1>") == 1


def test_every_language_renders_its_own_text(client):
    for lang in website_i18n.SUPPORTED_LANGS:
        resp = client.get(f"/?lang={lang}")
        assert resp.status_code == 200
        assert T["landing.h1"][lang] in resp.text
        assert T["landing.demo1_ask"][lang].replace("'", "&#39;") in resp.text


def test_the_page_shows_the_real_pass_prices(client):
    resp = client.get("/?lang=he")
    for price in ("19.90", "29.90", "49.90"):
        assert f"{price} ₪" in resp.text
    assert "1.66 ₪ ליום" in resp.text  # 49.90 / 30


def test_the_previous_page_comes_back_with_one_switch(client, monkeypatch):
    assert 'id="root"' in client.get("/?design=classic").text
    monkeypatch.setenv("HOME_DESIGN", "classic")
    resp = client.get("/")
    assert 'id="root"' in resp.text and "/static/home.js" not in resp.text


def test_the_page_carries_five_example_chats_for_the_demo(client):
    data = website_main._landing_js("en")
    assert len(data["demos"]) == 5
    assert data["demos"][0]["chips"] == T["landing.demo1_chips"]["en"].split("|")
    assert [c["name"] for c in data["cities"]][0] == "Haifa"


def test_no_text_on_the_page_uses_the_tells_the_owner_ruled_out():
    for key, entry in T.items():
        if not key.startswith("landing."):
            continue
        for text in entry.values():
            assert "·" not in text and "—" not in text and "←" not in text and "→" not in text, key


def test_map_api_is_unavailable_when_the_database_fails(client):
    @contextmanager
    def _broken():
        raise RuntimeError("db down")
        yield  # pragma: no cover

    with patch.object(website_main, "get_session", _broken):
        resp = client.get("/api/home-map")
    assert resp.status_code == 503


def test_map_api_returns_the_cached_data(client):
    data = {"grid": [[32.075, 34.8, 12, 3]], "new_24h": 3, "cities_24h": 1,
            "recent": [{"city": "רמת גן", "rooms": 3.0, "price": 7000, "lat": 32.08, "lng": 34.81}]}
    with patch.object(website_main, "_home_map_data", lambda: data):
        resp = client.get("/api/home-map")
    assert resp.status_code == 200 and resp.json() == data
    assert "max-age=300" in resp.headers["cache-control"]
