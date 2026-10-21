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


def test_the_demo_alert_is_the_bots_real_message():
    """Owner, 2026-10-20: the demo's alert shows the full message the bot sends, with its labels, emoji and buttons."""
    from todira_common.bot_strings import bot_text

    for lang in website_i18n.SUPPORTED_LANGS:
        alerts = [demo["alert"] for demo in website_main._landing_js(lang)["demos"]]
        assert len(alerts) == 5
        first = alerts[0]
        assert first["rows"][0] == ["💰", bot_text("card.price_label", lang), "7,300₪"]
        assert first["features_label"] == bot_text("card.features_label", lang)
        assert first["buttons"] == [bot_text(k, lang) for k in ("card.like_button", "card.hide_button", "card.found_button")]
        assert first["place"] == T["landing.demo1_street"][lang]
        assert alerts[2]["prefix"] == bot_text("card.sublet", lang)  # the sublet example says so, like the bot does
    html = TestClient(website_main.app).get("/?lang=he").text
    assert "🌿מרפסת" in html and 'id="lp-d-buttons"' in html


def test_dark_mode_shows_the_same_portrait_with_its_words(client):
    """Owner, 2026-10-19: the dark page showed a different picture of Todi; both themes use the one portrait with
    the words on it (a cut-out dark version was tried on 2026-10-21 and dropped)."""
    html = client.get("/?lang=he").text
    assert html.count('class="lp-portrait"') == 1 and "todi-hero-light.webp" in html
    assert "todi-hero-dark" not in html


def test_every_map_label_says_which_side_of_its_city_it_sits_on():
    for city in website_main._landing_js("he")["cities"]:
        assert city["side"] in ("w", "e") and city["name"]


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


def test_phone_notification_does_not_inherit_the_desktop_bottom():
    """2026-10-21 (owner screenshot): the desktop placement's `bottom` stayed on phones together with `top: 0`, and the
    card stretched over the whole picture. The phone rule has to clear it."""
    css = (Path(__file__).resolve().parent.parent / "website" / "static" / "home.css").read_text()
    phone_rule = next(line for line in css.splitlines() if ".lp-notif { top: 0;" in line)
    assert "bottom: auto" in phone_rule


def test_dark_theme_does_not_change_the_page_height():
    """2026-10-22 (owner: the whole site moved up or down when switching dark/light): the dark card got its spacing from
    margins, 80px more page. It may only change how it looks (a transform), never take more room."""
    css = (Path(__file__).resolve().parent.parent / "website" / "static" / "home.css").read_text()
    dark_rules = [line for line in css.splitlines() if "dark" in line and ".lp-portrait" in line and "{" in line]
    assert dark_rules and all("margin" not in rule for rule in dark_rules)


def test_apartments_page_does_not_wait_for_the_map():
    """2026-10-22 (owner: the listings page takes seconds): the map's CDN scripts and style sheets must never block the
    listings from showing."""
    html = (Path(__file__).resolve().parent.parent / "website" / "templates" / "apartments.html").read_text()
    for line in html.splitlines():
        if "cdn.jsdelivr.net/npm/leaflet" in line and "<script" in line:
            assert " defer" in line, line
        if "cdn.jsdelivr.net/npm/leaflet" in line and "<link" in line:
            assert 'media="print"' in line, line


def test_compact_json_stays_safe_inside_a_script_tag():
    import json

    out = str(website_main._json_compact({"a": "</script><b>'&", "b": "אבג"}))
    assert "</script>" not in out and "<" not in out and "אבג" in out
    assert json.loads(out) == {"a": "</script><b>'&", "b": "אבג"}


_CITY_KEYS = ("city_label", "city_placeholder", "city_result_n", "city_result_1", "city_result_0", "city_go", "last_now",
              "last_min_1", "last_min_n", "last_hour_1", "last_hour_n")


def test_city_check_texts_exist_in_every_language():
    """2026-10-22 (owner): how many came in in your city and when the last one came in, for every visitor."""
    for key in _CITY_KEYS:
        entry = T[f"landing.{key}"]
        assert set(entry) >= {"he", "en", "ru", "fr", "ar"}, key
        if key not in ("city_label", "city_placeholder"):
            assert all("{city}" in text for text in entry.values()), key


def test_city_check_is_on_the_home_page_and_its_button_goes_through_login(client):
    html = client.get("/?lang=he").text
    assert 'id="lp-mycity"' in html and 'id="lp-city-in"' in html
    assert 'href="/login?next=/apartments"' in html
    assert '"city_names"' in html and '"city_result_n"' in html


def test_city_view_shows_every_flat_of_that_city_and_keeps_the_saved_filter():
    """2026-10-22 (owner): the home page's "see the flats in <city>" opened the user's own filter instead."""
    from types import SimpleNamespace

    saved = SimpleNamespace(id=7, user_id=3, deal_type="sale", cities=["חיפה"], price_max=5000, require_parking=True)
    view = website_main._city_view_filter(saved, "ירושלים")
    assert view.cities == ["ירושלים"] and view.deal_type == "sale" and view.user_id == 3
    assert view.price_max is None and view.require_parking is False and view.keywords == []
    assert view.safe_room_pref == "any" and view.furniture_pref == "any"
    assert saved.cities == ["חיפה"] and saved.price_max == 5000  # the saved search is untouched


def test_home_city_button_goes_to_that_city_through_login():
    js = (Path(__file__).resolve().parent.parent / "website" / "static" / "home.js").read_text()
    assert '"/login?next=" + encodeURIComponent("/apartments?city="' in js
