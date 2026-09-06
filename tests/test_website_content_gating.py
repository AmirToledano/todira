"""Tests for the 2026-09-05 free/paid listing-card content gating on the website: /apartments and
/liked must pass has_access through to _listing_card.html, which then hides the description and
the real listing URL (replacing it with a locked "upgrade" button) for a lite/expired user. See
tests/test_cards.py for the equivalent bot-side (Telegram/WhatsApp caption) gating, and
common/dorin_common/cards.py's format_caption docstring for the underlying decision.

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
    def __init__(self, id, description="תיאור סודי מאוד", url="https://yad2.co.il/item/secret999"):
        self.id = id
        self.image_urls = []
        self.is_broker_listing = False
        self.source = "יד2"
        self.price = 5000
        self.city = "תל אביב"
        self.neighborhood = None
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


def test_apartments_hides_description_and_url_for_an_expired_user(client):
    user = _FakeUser(id=2, telegram_user_id=222, filter=SimpleNamespaceFilter())
    listing = _FakeListing(id=1)
    fake_session = _FakeSession(user, listings=[listing])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: SimpleNamespaceMatch(True)),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    assert "תיאור סודי" not in resp.text
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


def test_apartments_edit_filter_link_omits_uid_for_a_session_only_standalone_user():
    """Real bug found live (2026-09-05): a Google-only standalone account (dorin_common.models.
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


def test_liked_hides_description_and_url_for_an_expired_user(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    listing = _FakeListing(id=1)
    fake_session = _FakeSession(user, listings=[listing])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/liked", params={"uid": 222})

    assert resp.status_code == 200
    assert "תיאור סודי" not in resp.text
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
    """A minimal stand-in for dorin_common.models.Filter — /apartments only reads .cities off it
    in the template's filter-bar, and passes the whole object to evaluate() (mocked in these
    tests, so its own fields never actually matter)."""

    cities: list[str] = []
    rooms_min = None
    rooms_max = None
    price_min = None
    price_max = None


class SimpleNamespaceMatch:
    def __init__(self, matched):
        self.matched = matched
