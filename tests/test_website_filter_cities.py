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
    from todira_common.cities import CITIES

    resp = client.get(f"/filter?uid={fake_user.telegram_user_id}")
    assert resp.status_code == 200
    for city in CITIES:
        assert f'value="{city}"' in resp.text


def test_filter_page_renders_cities_in_alphabetical_order(client, fake_user):
    # Real user feedback (2026-09-02): the raw CITIES list isn't alphabetized, making the
    # checkbox grid hard to scan - display order should be sorted even though CITIES itself
    # (used by matching/the bot's own picker) stays in its original order.
    from todira_common.cities import CITIES

    resp = client.get(f"/filter?uid={fake_user.telegram_user_id}")
    positions = [resp.text.index(f'value="{city}"') for city in sorted(CITIES)]
    assert positions == sorted(positions)


def test_filter_page_city_search_box_does_not_submit_the_form_on_enter(client, fake_user):
    # Real bug (2026-09-02): pressing Enter/search in the city-search text box submitted the
    # whole filter form (a full page reload) instead of just filtering the checkbox list.
    resp = client.get(f"/filter?uid={fake_user.telegram_user_id}")
    assert "onkeydown" in resp.text
    assert "f-cities-search" in resp.text


# --- non-numeric input on the numeric fields (2026-09-24 real bug fix) ---
# price_min/price_max/rooms_min/rooms_max/floor_min/floor_max/min_area_sqm are deliberately plain
# `str = Form` (not `int = Form`), so an empty string can mean "no limit" without FastAPI 422ing
# the whole form — but that also meant a non-numeric value skipped FastAPI's own type coercion
# entirely and hit a bare int()/float() in filter_update, raising an uncaught ValueError on every
# save (not just that field) instead of just... having no limit, same as an empty field already got.


def test_non_numeric_price_min_is_treated_as_no_limit_not_a_500(client, fake_user):
    resp = client.post(
        "/filter", data=_base_form(fake_user.telegram_user_id, price_min="לא מספר")
    )
    assert resp.status_code == 303
    assert fake_user.filter.price_min is None


def test_non_numeric_rooms_max_is_treated_as_no_limit_not_a_500(client, fake_user):
    resp = client.post(
        "/filter", data=_base_form(fake_user.telegram_user_id, rooms_max="abc")
    )
    assert resp.status_code == 303
    assert fake_user.filter.rooms_max is None


def test_comma_formatted_price_is_treated_as_no_limit_not_a_500(client, fake_user):
    # A real, plausible way to hit this without any malice at all — a user pasting "5,000" from
    # somewhere with thousands separators. int("5,000") raises ValueError just like garbage text.
    resp = client.post(
        "/filter", data=_base_form(fake_user.telegram_user_id, price_max="5,000")
    )
    assert resp.status_code == 303
    assert fake_user.filter.price_max is None


def test_non_numeric_input_does_not_prevent_the_rest_of_the_form_from_saving(client, fake_user):
    # The real regression this whole bug caused: ONE bad numeric field used to 500 the entire
    # save, silently discarding every other real change (cities, amenities, etc.) in the same
    # submission along with it.
    resp = client.post(
        "/filter",
        data=_base_form(
            fake_user.telegram_user_id, floor_min="oops", cities=["רמת גן"], no_brokers="on",
        ),
    )
    assert resp.status_code == 303
    assert fake_user.filter.floor_min is None
    assert fake_user.filter.cities == ["רמת גן"]
    assert fake_user.filter.no_brokers is True
