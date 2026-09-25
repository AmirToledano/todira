"""Tests for the free/paid listing-card content gating on the website: /apartments and /liked must
pass has_access through to _listing_card.html, which then replaces the real listing URL with a
locked "upgrade" button for a lite/expired user. The description itself is shown to everyone as of
2026-09-12 (reversing the original 2026-09-05 decision to hide it too) — see tests/test_cards.py
for the equivalent bot-side (Telegram/WhatsApp caption) gating, and
common/todira_common/cards.py's format_caption docstring for that history.

Same importlib-loading approach as the other website test files (see test_website_paid_access.py's
own comment) — website/main.py shares a basename with scraper/main.py so it can't go through a
bare `import main`.
"""
from __future__ import annotations

import datetime as dt
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

_spec = importlib.util.spec_from_file_location(
    "website_main_content_gating", _WEBSITE_DIR / "main.py"
)
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402

_NOW = dt.datetime.now(dt.timezone.utc)


class _FakeUser:
    def __init__(self, id, telegram_user_id, **overrides):
        self.id = id
        self.telegram_user_id = telegram_user_id
        self.first_name = overrides.get("first_name")
        self.telegram_username = overrides.get("telegram_username")
        self.filter = overrides.get("filter")
        self.free_access_granted = overrides.get("free_access_granted", False)
        self.trial_ends_at = overrides.get("trial_ends_at", _NOW - dt.timedelta(days=1))
        self.paid_until = overrides.get("paid_until")


class _FakeListing:
    def __init__(
        self, id, description="תיאור סודי מאוד", url="https://yad2.co.il/item/secret999",
        latitude=None, longitude=None, street=None, property_type=None,
        previous_price=None, move_in_date=None,
    ):
        self.id = id
        self.latitude = latitude
        self.longitude = longitude
        self.image_urls = []
        self.is_broker_listing = False
        self.source = "יד2"
        self.price = 5000
        self.city = "תל אביב"
        self.neighborhood = None
        self.street = street
        self.property_type = property_type
        self.rooms = 3
        self.floor = 1
        self.floor_total = 3
        self.size_sqm = 70
        self.has_parking = True
        self.has_elevator = False
        self.has_balcony = False
        self.pets_allowed = False
        self.is_renovated = False
        self.safe_room_type = None
        self.furniture = None
        self.description = description
        self.posted_at = None
        self.move_in_date = move_in_date
        self.previous_price = previous_price
        self.url = url


class _FakeSession:
    def __init__(self, user, listings=None, liked_ids=None):
        self._user = user
        self._listings = listings or []
        self._liked_ids = liked_ids or []

    def scalar(self, stmt):
        return self._user

    def get(self, model, pk):
        return self._user

    def execute(self, stmt):
        # Backs base.html's header lookup (_current_user_summary), triggered whenever the
        # request's session already carries a user_id (a real session-only visitor).
        class _Result:
            def __init__(self, row):
                self._row = row

            def first(self_inner):
                return self_inner._row

        return _Result(self._user)

    def scalars(self, stmt):
        class _Scalars:
            def __init__(self, items):
                self._items = items

            def all(self):
                return self._items

        # /apartments's own listing query and /liked's liked_listing_ids query both go through
        # scalars() — this fake session is only ever used with one or the other per test, so
        # returning self._listings unconditionally is enough (liked_ids tests set listings
        # directly instead).
        return _Scalars(self._listings)


def _fake_get_session(session):
    @contextmanager
    def _inner():
        yield session

    return _inner


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_apartments_shows_description_but_hides_url_for_an_expired_user(client):
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter())
    listing = _FakeListing(id=1)
    fake_session = _FakeSession(user, listings=[listing])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    assert "תיאור סודי" in resp.text
    assert "secret999" not in resp.text


def test_apartments_shows_description_and_url_for_a_trial_user(client):
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter(),
                      trial_ends_at=_NOW + dt.timedelta(days=2))
    listing = _FakeListing(id=1)
    fake_session = _FakeSession(user, listings=[listing])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    assert "תיאור סודי" in resp.text
    assert "secret999" in resp.text


def test_apartments_map_workspace_renders_with_pins_for_listings_that_have_coords(client):
    """2026-09-24: the map+filter sidebar workspace (dorin.app-style layout) — a listing with real
    coordinates gets data-lat/data-lng on its card (read by the map's own JS, see apartments.html's
    script), a listing without them gets neither attribute at all (never a blank data-lat="")."""
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter(),
                      trial_ends_at=_NOW + dt.timedelta(days=2))
    with_coords = _FakeListing(id=1, latitude=32.0853, longitude=34.7818)
    without_coords = _FakeListing(id=2)
    fake_session = _FakeSession(user, listings=[with_coords, without_coords])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    assert 'class="apt-workspace' in resp.text
    assert 'id="apt-map"' in resp.text
    assert 'id="apt-filter-pane"' in resp.text
    assert 'data-lat="32.0853" data-lng="34.7818"' in resp.text
    assert 'data-lat=""' not in resp.text
    assert 'data-lng=""' not in resp.text


def test_apartments_workspace_has_map_toggle_settings_and_detail_modal_markup(client):
    """2026-09-24: real owner request batch — map collapse/reopen toggle, a map-settings age
    filter, and the listing-detail modal (clicking a card opens a real floating window on top of
    the page — see apartments.html's own script comment; this replaced an earlier sidebar-swap
    version after the owner explicitly said that wasn't what they meant). This only checks the
    markup these features' JS depends on actually renders; the JS/CSS behavior itself is covered
    by manual Playwright verification (no headless browser in this test suite)."""
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter(),
                      trial_ends_at=_NOW + dt.timedelta(days=2))
    listing = _FakeListing(
        id=1, latitude=32.0853, longitude=34.7818,
        description="תיאור ארוך של הדירה " * 10,
    )
    listing.posted_at = _NOW - dt.timedelta(days=3)
    listing.image_urls = ["https://img.example/1.jpg", "https://img.example/2.jpg"]
    fake_session = _FakeSession(user, listings=[listing])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    # Collapse toggle (in-pane arrow) + the toolbar toggle that replaced the old floating reopen
    # pill (2026-09-24 real owner report: the map took up too much page space by default — the
    # single show/hide control now lives in the always-visible toolbar, and the map starts collapsed).
    assert 'id="apt-map-collapse-btn"' in resp.text
    assert 'id="apt-toolbar-map-toggle"' in resp.text
    # 2026-09-25: no longer carries .reveal — see apartments.html's own comment for the real
    # CSS-opacity-compounding bug this fixed (a fully-clickable but visually invisible results area).
    assert 'class="apt-workspace map-collapsed"' in resp.text
    assert 'class="apt-map-pane collapsed"' in resp.text
    # Map-settings age filter popover
    assert 'id="apt-map-settings"' in resp.text
    assert 'id="apt-map-age-select"' in resp.text
    # Toolbar chip order (2026-09-24 follow-up owner report): the map toggle must sit further along
    # the toolbar than the results count, not before it.
    assert resp.text.index('apt-toolbar-count') < resp.text.index('apt-toolbar-map-toggle')
    # Listing-detail modal — a real floating overlay, hidden by default, closed via its own top bar
    assert 'id="apt-listing-modal" hidden' in resp.text
    assert 'id="apt-listing-modal-backdrop"' in resp.text
    assert 'id="apt-listing-modal-header"' in resp.text
    assert 'id="apt-listing-modal-body"' in resp.text
    # The card carries the data the modal's JS reads: full (untruncated) description, posted date,
    # and the full photo list (2026-09-24) the modal's own gallery is built from.
    assert 'data-description-full="תיאור ארוך' in resp.text
    assert f'data-posted-at="{listing.posted_at.isoformat()}"' in resp.text
    assert "data-image-urls=" in resp.text
    assert "https://img.example/1.jpg" in resp.text
    assert "https://img.example/2.jpg" in resp.text
    # 2026-09-25: real owner request, comparing directly against dorin.app's own bottom-sheet —
    # the modal body carries the translated section-heading/posted-date strings its own JS reads
    # to build a real "תיאור הנכס" heading and an exact posted-date line (see apartments.html's
    # own openListingDetail() comment).
    assert 'data-description-heading="תיאור הנכס"' in resp.text
    assert 'data-posted-on-template="פורסם ב-__DATE__"' in resp.text


def test_apartments_listing_card_omits_posted_at_and_description_full_when_absent(client):
    """Mirrors the existing data-lat/data-lng guard (never a blank attribute for a listing that
    just doesn't have the field) — a listing with no posted_at/description must not render
    data-posted-at="" or data-description-full=""."""
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter(),
                      trial_ends_at=_NOW + dt.timedelta(days=2))
    listing = _FakeListing(id=1, description=None)
    listing.posted_at = None
    fake_session = _FakeSession(user, listings=[listing])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    assert 'data-posted-at=""' not in resp.text
    assert 'data-description-full=""' not in resp.text


def test_apartments_card_shows_street_property_type_and_price_drop_badge(client):
    """2026-09-24 real owner request batch (comparing against dorin.app's own card): the location
    block shows city/neighborhood/street, a property-type badge appears among the feature badges,
    and a real price DROP renders the old price struck through + a green '-X%' badge."""
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter(),
                      trial_ends_at=_NOW + dt.timedelta(days=2))
    listing = _FakeListing(
        id=1, street="הרצל 12", property_type="apartment", previous_price=5000,
    )
    listing.price = 4000  # dropped from previous_price=5000 -> 4000, a real 20% drop
    fake_session = _FakeSession(user, listings=[listing])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    assert "הרצל 12" in resp.text
    assert 'class="loc-city"' in resp.text
    assert "דירה" in resp.text  # card.type_apartment
    assert '5,000 ₪' in resp.text or "5000 ₪" in resp.text
    assert "price-drop" in resp.text
    assert "-20%" in resp.text


def test_apartments_card_shows_price_rise_badge_with_correct_sign(client):
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter(),
                      trial_ends_at=_NOW + dt.timedelta(days=2))
    listing = _FakeListing(id=1, previous_price=4000)
    listing.price = 5000  # rose from previous_price=4000 -> 5000, a real 25% rise
    fake_session = _FakeSession(user, listings=[listing])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    assert "price-rise" in resp.text
    assert "+25%" in resp.text


def test_apartments_card_omits_price_change_badge_when_price_unchanged(client):
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter(),
                      trial_ends_at=_NOW + dt.timedelta(days=2))
    listing = _FakeListing(id=1, previous_price=5000)
    listing.price = 5000  # same price -> no badge, ever
    fake_session = _FakeSession(user, listings=[listing])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    assert "price-change" not in resp.text


def test_apartments_edit_filter_link_omits_uid_for_a_session_only_standalone_user():
    """Real bug found live (2026-09-05): a Google-only standalone account (todira_common.models.
    User, created via /auth/google/create-account) has no telegram_user_id at all, so `uid` in the
    template context is None for a visitor resolved purely via their session cookie. apartments.
    html's "ערוך סינון" link used to string-interpolate it unconditionally (`?uid={{ uid }}`), and
    Jinja renders a raw None as the literal text "None" — every click 422'd with
    `{"detail":[{"type":"int_parsing","loc":["query","uid"],... "input":"None"}]}`."""
    from starlette.requests import Request as StarletteRequest

    user = _FakeUser(id=2, telegram_user_id=None, filter=SimpleNamespaceFilter())
    fake_session = _FakeSession(user, listings=[])

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/apartments",
        "session": {"user_id": 2},
        "query_string": b"",
        "headers": [],
        "app": website_main.app,
    }
    request = StarletteRequest(scope)

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = website_main.apartments(request, uid=None)

    body = resp.body.decode()
    assert "uid=None" not in body
    assert 'href="/filter"' in body


def test_liked_shows_description_but_hides_url_for_an_expired_user(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    listing = _FakeListing(id=1)
    fake_session = _FakeSession(user, listings=[listing])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/liked", params={"uid": 222})

    assert resp.status_code == 200
    assert "תיאור סודי" in resp.text
    assert "secret999" not in resp.text


# ---------------------------------------------------------------------------
# /apartments pagination — 2026-09-06: rendering all (up to 200) matches in one page crashed real
# visitors' browsers, so the route now paginates (APARTMENTS_PAGE_SIZE at a time) with a
# JS-driven "load more" fragment endpoint. See main.py's apartments() route and apartments.html's
# own script for the full mechanism.
# ---------------------------------------------------------------------------


def test_apartments_first_page_shows_only_page_size_and_a_sentinel(client):
    page_size = website_main.APARTMENTS_PAGE_SIZE
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter())
    listings = [_FakeListing(id=i) for i in range(page_size + 5)]
    for i, listing in enumerate(listings):
        listing.city = f"עיר-{i}"
    fake_session = _FakeSession(user, listings=listings)

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    for i in range(page_size):
        assert f"עיר-{i}" in resp.text
    for i in range(page_size, page_size + 5):
        assert f"עיר-{i}" not in resp.text
    assert f'data-next-offset="{page_size}"' in resp.text
    # The results-count badge shows the TOTAL match count, not just this page's size.
    assert f"<b>{page_size + 5}</b>" in resp.text


def test_apartments_no_sentinel_when_everything_fits_on_one_page(client):
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter())
    listings = [_FakeListing(id=1)]
    fake_session = _FakeSession(user, listings=listings)

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    # The script itself mentions the class name (querySelector calls) regardless — check for the
    # actual sentinel *element*, not just the substring anywhere on the page.
    assert 'class="load-more-sentinel"' not in resp.text


def test_apartments_fragment_request_returns_only_the_next_batch_no_page_layout(client):
    page_size = website_main.APARTMENTS_PAGE_SIZE
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter())
    listings = [_FakeListing(id=i) for i in range(page_size + 5)]
    for i, listing in enumerate(listings):
        listing.city = f"עיר-{i}"
    fake_session = _FakeSession(user, listings=listings)

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222, "offset": page_size, "fragment": "1"})

    assert resp.status_code == 200
    # The next batch's listings are here...
    for i in range(page_size, page_size + 5):
        assert f"עיר-{i}" in resp.text
    # ...the first page's are not (this is only the new batch, appended client-side)...
    assert "עיר-0" not in resp.text
    # ...no more after this, so no sentinel...
    assert "load-more-sentinel" not in resp.text
    # ...and critically, no full-page layout (header/nav) — just the card markup to insert.
    assert "<html" not in resp.text
    assert "nav-toggle" not in resp.text


class SimpleNamespaceFilter:
    """A minimal stand-in for todira_common.models.Filter — /apartments only reads .cities off it
    in the template's filter-bar, and passes the whole object to evaluate() (mocked in these
    tests, so its own fields never actually matter for the matching itself)."""

    def __init__(self, deal_type=None, cities=None):
        self.deal_type = deal_type
        self.cities = cities or []

    rooms_min = None
    rooms_max = None
    price_min = None
    price_max = None


def test_apartments_listing_photos_have_real_alt_text(client):
    # Found live 2026-09-07: every cover photo had alt="" regardless of whether it was a real
    # Yad2 photo or the decorative Todi-illustration fallback — a screen-reader user got zero
    # information about what a card's actual photos showed.
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter())
    listing = _FakeListing(id=1)
    listing.image_urls = ["https://img.example/1.jpg"]
    listing.city = "חיפה"
    listing.rooms = 3
    fake_session = _FakeSession(user, listings=[listing])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    assert 'alt=""' not in resp.text
    assert "חיפה" in resp.text
    assert 'alt="' in resp.text


def test_apartments_has_an_aria_live_region_for_infinite_scroll_announcements(client):
    # Found live 2026-09-07: infinite scroll inserted new cards completely silently — a
    # screen-reader user got no indication that more listings had appeared below the ones they'd
    # already heard, since there's no page navigation to trigger a re-announcement.
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter())
    fake_session = _FakeSession(user, listings=[_FakeListing(id=1)])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    assert 'id="apartments-live-region"' in resp.text
    assert 'aria-live="polite"' in resp.text
    assert 'role="status"' in resp.text


def test_apartments_scopes_the_listings_query_by_filter_city_and_deal_type(client):
    # Found live 2026-09-07: /apartments used to look at only the 200 most-recently-scraped
    # listings across EVERY city/deal_type before filtering, so a narrow filter for one specific
    # (less active) city could have its own matching listings permanently pushed out of that
    # window by newer listings scraped for every other city. Applying city/deal_type in the SQL
    # WHERE clause itself (both already hard filters evaluate() enforces regardless) fixes this by
    # construction — asserted here directly against the compiled statement rather than through
    # observed behavior, since the fake session's scalars() doesn't otherwise care what it's given.
    class _RecordingSession(_FakeSession):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.captured_stmts = []

        def scalars(self, stmt):
            self.captured_stmts.append(stmt)
            return super().scalars(stmt)

    user = _FakeUser(
        id=2, telegram_user_id=222, filter=SimpleNamespaceFilter(deal_type="rent", cities=["חיפה"])
    )
    fake_session = _RecordingSession(user, listings=[])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    # /apartments issues several scalars() queries per request (hidden-listing-ids, the listings
    # query itself, liked-listing-ids) — find the one actually selecting from "listings".
    listings_stmt = next(
        stmt for stmt in fake_session.captured_stmts if "FROM listings" in str(stmt)
    )
    compiled_sql = str(listings_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "deal_type" in compiled_sql and "rent" in compiled_sql
    assert "city" in compiled_sql and "חיפה" in compiled_sql


class SimpleNamespaceMatch:
    def __init__(self, matched):
        self.matched = matched
