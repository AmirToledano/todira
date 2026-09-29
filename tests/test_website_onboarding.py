"""Tests for the dorin.app-style first-time onboarding flow (2026-09-26, real owner request from
a 33-page PDF walkthrough of dorin.app's own onboarding): filter setup (website/main.py's existing
/filter, extended) -> optional Telegram notifications connect (/onboarding/notifications) ->
automatic trial-activation confirmation (/onboarding/trial).

Same importlib-loading + fake-session approach as test_website_filter_cities.py.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_onboarding", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402

_NOW = dt.datetime.now(dt.timezone.utc)


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
    def __init__(self, uid: int | None, trial_ends_at=None):
        self.id = 1
        self.telegram_user_id = uid
        self.filter = _FakeFilter()
        self.trial_ends_at = trial_ends_at or (_NOW + dt.timedelta(days=3))
        self.channel_link_code = None
        self.channel_link_code_expires_at = None
        self.first_name = None
        self.telegram_username = None


class _FakeSession:
    def __init__(self, user: _FakeUser):
        self._user = user
        self.committed = False

    def scalar(self, stmt):
        return self._user

    def commit(self):
        self.committed = True

    def execute(self, stmt):
        # Backs base.html's header lookup (_current_user_summary) — only actually queried when a
        # prior request already stamped a real session cookie (e.g. a successful wid resolution
        # auto-logs a visitor in); harmless to always answer with this same user regardless.
        class _Result:
            def __init__(self, row):
                self._row = row

            def first(self_inner):
                return self_inner._row

        return _Result(self._user)


def _client_for(user: _FakeUser):
    fake_session = _FakeSession(user)

    @contextmanager
    def _fake_get_session():
        yield fake_session

    return patch.object(website_main, "get_session", _fake_get_session)


def _base_form(uid: int, **overrides) -> dict:
    form = {"uid": str(uid)}
    form.update(overrides)
    return form


# --- required-city validation, welcome flow only ---


def test_welcome_flow_with_no_cities_is_blocked_and_nothing_is_saved():
    user = _FakeUser(uid=555)
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.post(
            "/filter", data=_base_form(555, welcome="1", no_brokers="on"),
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/filter?uid=555&welcome=1&error=cities"
    # nothing at all was written — not even the other field in the same submission
    assert user.filter.cities == []
    assert user.filter.no_brokers is False


def test_welcome_flow_with_a_real_city_saves_and_advances_to_step_2():
    user = _FakeUser(uid=555)
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.post(
            "/filter", data=_base_form(555, welcome="1", cities=["רמת גן"]),
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/onboarding/notifications?uid=555"
    assert user.filter.cities == ["רמת גן"]


def test_non_welcome_save_with_no_cities_is_never_blocked():
    """Outside onboarding, an empty cities list still means "all cities" (todira_common.matching
    skips the city check entirely) — this validation is deliberately scoped to the welcome flow
    only, never the general /filter save or the apartments-sidebar panel (same POST /filter
    route)."""
    user = _FakeUser(uid=555)
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.post("/filter", data=_base_form(555))
    assert resp.status_code == 303
    assert resp.headers["location"] == "/apartments?uid=555"
    assert user.filter.cities == []


def test_welcome_flow_error_redirect_is_shown_on_the_filter_page():
    user = _FakeUser(uid=555)
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.get("/filter", params={"uid": 555, "welcome": "1", "error": "cities"})
    assert resp.status_code == 200
    assert "cities-error-banner" in resp.text


# --- 2026-09-27: real bug, live-reported (diagnose-city-filter-coverage-gap.yaml confirmed 3,727
# of 12,893 active listings, ~29%, have a real city outside CITIES' curated ~42-city whitelist) —
# checking every individual city box is NOT the same as "no city filter": the matching-logic city
# check is skipped entirely only when filter.cities is empty, but requires an exact whitelist
# match when non-empty. The mandatory-city welcome block made that real unfiltered state
# unreachable for a new user (leaving the grid empty was the only way there, and welcome blocks
# submitting zero cities). all_cities is a first-class toggle that reaches cities=[] for real and
# also satisfies the welcome validation on its own.


def test_all_cities_toggle_satisfies_welcome_validation_and_saves_an_empty_city_filter():
    user = _FakeUser(uid=555)
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.post(
            "/filter", data=_base_form(555, welcome="1", all_cities="on"),
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/onboarding/notifications?uid=555"
    assert user.filter.cities == []


def test_all_cities_toggle_wins_even_if_individual_cities_were_also_submitted():
    """The front end keeps the toggle and the grid mutually exclusive via JS, but the server
    doesn't trust that alone — all_cities always overrides whatever else came in `cities`."""
    user = _FakeUser(uid=555)
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.post(
            "/filter", data=_base_form(555, all_cities="on", cities=["רמת גן"]),
        )
    assert resp.status_code == 303
    assert user.filter.cities == []


# --- 2026-09-27: real bug, live-reported — _filter_form_fields.html's <script> defining
# filterCityChips/onAllCitiesToggle used to sit AFTER {% endmacro %}, so a `{% from ... import
# filter_form_fields %}` (both filter.html and apartments.html) never rendered it — the city
# search box's typing filter and the "all cities" toggle silently did nothing anywhere. Now
# inlined inside the macro body; asserts the actual function definitions ship on the page, not
# just that the input/button elements exist (which passed even while broken). The apartments.html
# equivalent lives in test_website_content_gating.py, whose fixtures already build the heavier
# fake session /apartments needs.


def test_filter_page_ships_the_city_search_js_functions():
    user = _FakeUser(uid=555)
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.get("/filter", params={"uid": 555})
    assert resp.status_code == 200
    assert "function filterCityChips(query)" in resp.text
    assert "function onAllCitiesToggle(checked)" in resp.text
    assert "function onCityChipChecked()" in resp.text


def test_all_cities_toggle_is_checked_when_the_filter_has_no_cities():
    user = _FakeUser(uid=555)
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.get("/filter", params={"uid": 555})
    assert resp.status_code == 200
    assert 'id="f-all-cities" name="all_cities" checked' in resp.text


def test_all_cities_toggle_is_unchecked_when_specific_cities_are_selected():
    user = _FakeUser(uid=555)
    user.filter.cities = ["רמת גן"]
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.get("/filter", params={"uid": 555})
    assert resp.status_code == 200
    assert 'id="f-all-cities" name="all_cities"  onchange' in resp.text


# --- 2026-09-28: real bug found via a fresh code-review sweep — a brand-new user's Filter row
# always starts with cities==[], so the "all cities" checkbox above rendered checked by default
# during the welcome flow too. filter_update's own mandatory-city block (task #80) only checks
# `all_cities is None`, so a first-time user who tapped "continue" without touching the city grid
# submitted all_cities=on for free and sailed straight past the hard block with zero interaction,
# silently saving an unfiltered filter. The checkbox must render UNCHECKED during welcome
# specifically (welcome always starts with empty cities anyway, so this changes nothing else).


def test_all_cities_toggle_is_unchecked_during_welcome_even_with_no_cities():
    user = _FakeUser(uid=555)
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.get("/filter", params={"uid": 555, "welcome": "1"})
    assert resp.status_code == 200
    assert 'id="f-all-cities" name="all_cities"  onchange' in resp.text


def test_welcome_flow_still_blocked_even_though_all_cities_renders_unchecked():
    """Confirms the checkbox-render fix above and the backend validation agree: doing nothing
    during welcome (no cities, no all_cities toggle) is blocked end to end, not just visually."""
    user = _FakeUser(uid=555)
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.post("/filter", data=_base_form(555, welcome="1"))
    assert resp.status_code == 303
    assert resp.headers["location"] == "/filter?uid=555&welcome=1&error=cities"
    assert user.filter.cities == []


# --- /onboarding/notifications (step 2) ---


def test_notifications_step_shows_a_real_telegram_connect_link_for_a_non_telegram_user():
    user = _FakeUser(uid=None)
    token = website_main.generate_wid_token("972501234567")
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.get("/onboarding/notifications", params={"wid": token})
    assert resp.status_code == 200
    assert "https://t.me/AmirDirotBot?start=" in resp.text
    assert user.channel_link_code  # a real code was actually generated


def test_notifications_step_reuses_an_existing_still_valid_code_instead_of_regenerating():
    """2026-09-27: same real bug as /account's own identical fix — reloading this page (a natural
    thing to do while checking if the Telegram connect worked) used to silently replace an
    already-sent code with a new one via generate_link_code's default replace-on-every-call
    behavior, orphaning it with no error shown anywhere."""
    user = _FakeUser(uid=None)
    user.channel_link_code = "ref_existing"
    user.channel_link_code_expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)
    token = website_main.generate_wid_token("972501234567")
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.get("/onboarding/notifications", params={"wid": token})
    assert resp.status_code == 200
    assert "https://t.me/AmirDirotBot?start=ref_existing" in resp.text
    assert user.channel_link_code == "ref_existing"


def test_notifications_step_skips_straight_to_skip_link_for_an_already_telegram_user():
    user = _FakeUser(uid=555)
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.get("/onboarding/notifications", params={"uid": 555})
    assert resp.status_code == 200
    # already connected via Telegram — no reason to (re)generate a link code for this visitor
    assert user.channel_link_code is None
    assert "/onboarding/trial" in resp.text


def test_notifications_step_skip_link_carries_identity_forward():
    user = _FakeUser(uid=555)
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.get("/onboarding/notifications", params={"uid": 555})
    assert "/onboarding/trial?uid=555" in resp.text


# --- /onboarding/trial (step 3) ---


def test_trial_step_shows_the_real_trial_end_date():
    user = _FakeUser(uid=555, trial_ends_at=dt.datetime(2026, 10, 3, tzinfo=dt.timezone.utc))
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.get("/onboarding/trial", params={"uid": 555})
    assert resp.status_code == 200
    assert "03.10.2026" in resp.text


def test_trial_step_continue_button_goes_to_apartments_with_identity():
    user = _FakeUser(uid=555)
    with _client_for(user):
        client = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = client.get("/onboarding/trial", params={"uid": 555})
    assert 'href="/apartments?uid=555"' in resp.text
