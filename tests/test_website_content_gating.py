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


def test_liked_hides_description_and_url_for_an_expired_user(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    listing = _FakeListing(id=1)
    fake_session = _FakeSession(user, listings=[listing])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/liked", params={"uid": 222})

    assert resp.status_code == 200
    assert "תיאור סודי" not in resp.text
    assert "secret999" not in resp.text


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
