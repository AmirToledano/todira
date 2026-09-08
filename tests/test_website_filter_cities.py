"""Tests for the website's /filter POST route (website/main.py) — specifically the cities field,
which changed 2026-09-02 from a free-typed comma-separated text input to a checkbox grid (mirrors
how property_types already worked on the same page) after a real user asked for it: typing exact
city names by hand was the actual complaint, matching what the Telegram bot's /filter conversation
had already been changed to do (see keyboards.py's city_picker_keyboard, same session).

website/main.py is loaded via importlib under an explicit name — see test_website_contact.py's
module docstring for why (scraper/main.py shares a basename).
"""
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

_spec = importlib.util.spec_from_file_location("website_main_filter_cities", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


class _FakeFilter:
    def __init__(self):
        self.cities: list[str] = []
        self.price_min = self.price_max = None
        self.rooms_min = self.rooms_max = None
        self.property_types: list[str] = []
        self.floor_min = self.floor_max = None
        self.ground_floor_only = False
        self.require_parking = self.require_elevator = self.require_balcony = False
        self.require_pets_allowed = self.require_renovated = False
        self.require_roommate_friendly = self.require_has_photos = False
        self.no_brokers = False
        self.safe_room_pref = "any"
        self.furniture_pref = "any"
        self.min_area_sqm = None
        self.keywords: list[str] = []
        self.flexible_match = False


class _FakeUser:
    def __init__(self, uid: int):
        self.id = 1
        self.telegram_user_id = uid
        self.filter = _FakeFilter()


class _FakeSession:
    def __init__(self, user: _FakeUser):
        self._user = user
        self.committed = False

    def scalar(self, stmt):
        return self._user

    def commit(self):
        self.committed = True


@pytest.fixture
def fake_user():
    return _FakeUser(uid=555)


@pytest.fixture
def client(fake_user):
    fake_session = _FakeSession(fake_user)

    @contextmanager
    def _fake_get_session():
        yield fake_session

    with patch.object(website_main, "get_session", _fake_get_session):
        yield TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def _base_form(uid: int, **overrides) -> dict:
    form = {"uid": str(uid)}
    form.update(overrides)
    return form


def test_checked_cities_are_saved(client, fake_user):
    resp = client.post(
        "/filter",
        data=_base_form(fake_user.telegram_user_id, cities=["רמת גן", "חיפה"]),
    )
    assert resp.status_code == 303
    assert fake_user.filter.cities == ["רמת גן", "חיפה"]


def test_unknown_city_value_is_dropped_not_trusted_blindly():
    # mirrors property_types' own validation - a POST isn't necessarily from the real form
    user = _FakeUser(uid=555)
    session = _FakeSession(user)

    @contextmanager
    def _fake_get_session():
        yield session

    with patch.object(website_main, "get_session", _fake_get_session):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        client.post(
            "/filter",
            data=_base_form(user.telegram_user_id, cities=["רמת גן", "עיר שלא קיימת"]),
        )

    assert user.filter.cities == ["רמת גן"]


def test_no_cities_checked_means_empty_list_not_error(client, fake_user):
    resp = client.post("/filter", data=_base_form(fake_user.telegram_user_id))
    assert resp.status_code == 303
    assert fake_user.filter.cities == []


def test_successful_save_redirects_to_apartments_not_back_to_filter(client, fake_user):
    """2026-09-08 UX fix (owner's own report): saving used to redirect back to /filter itself,
    leaving the visitor on the same form with no visible sign anything happened. A successful
    save now lands on /apartments — showing the results of the change just made."""
    resp = client.post("/filter", data=_base_form(fake_user.telegram_user_id))
    assert resp.status_code == 303
    assert resp.headers["location"] == "/apartments?uid=555"


def test_filter_page_renders_every_bundled_city_as_a_checkbox(client, fake_user):
    from dorin_common.cities import CITIES

    resp = client.get(f"/filter?uid={fake_user.telegram_user_id}")
    assert resp.status_code == 200
    for city in CITIES:
        assert f'value="{city}"' in resp.text


def test_filter_page_renders_cities_in_alphabetical_order(client, fake_user):
    # Real user feedback (2026-09-02): the raw CITIES list isn't alphabetized, making the
    # checkbox grid hard to scan - display order should be sorted even though CITIES itself
    # (used by matching/the bot's own picker) stays in its original order.
    from dorin_common.cities import CITIES

    resp = client.get(f"/filter?uid={fake_user.telegram_user_id}")
    positions = [resp.text.index(f'value="{city}"') for city in sorted(CITIES)]
    assert positions == sorted(positions)


def test_filter_page_city_search_box_does_not_submit_the_form_on_enter(client, fake_user):
    # Real bug (2026-09-02): pressing Enter/search in the city-search text box submitted the
    # whole filter form (a full page reload) instead of just filtering the checkbox list.
    resp = client.get(f"/filter?uid={fake_user.telegram_user_id}")
    assert "onkeydown" in resp.text
    assert "f-cities-search" in resp.text
