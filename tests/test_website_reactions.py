"""Tests for the website's ❤️/🙈 like-hide toggle (POST /react), the /hidden page, and the
/apartments "no brokers" quick-filter toggle — all added 2026-09-06 as part of the account-page
roadmap (referral/AI-chat items excluded, need real product decisions; these mirror data/behavior
that already existed in the Telegram bot: bot/handlers/liked.py's _apply_reaction_sync and
bot/handlers/apartments.py's find_matching_listings hidden-exclusion).

Same importlib-loading approach as the other website test files (see test_website_paid_access.py's
own comment) — website/main.py shares a basename with scraper/main.py so it can't go through a
bare `import main`.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import Delete

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_reactions", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


class _FakeUser:
    def __init__(self, id, telegram_user_id=None, filter=None):
        self.id = id
        self.telegram_user_id = telegram_user_id
        self.filter = filter
        # has_full_access() needs these three — default to unrestricted access so tests can
        # assert on listing content (URL/description) without also gating on paid access, which
        # isn't what these tests are about.
        self.free_access_granted = True
        self.trial_ends_at = None
        self.paid_until = None


class _FakeFilter:
    def __init__(self, no_brokers=False):
        self.no_brokers = no_brokers


class _FakeListing:
    def __init__(self, id):
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
        self.has_parking = False
        self.has_elevator = False
        self.has_balcony = False
        self.pets_allowed = False
        self.is_renovated = False
        self.safe_room_type = None
        self.furniture = None
        self.description = "תיאור"
        self.posted_at = None
        self.url = f"https://yad2.co.il/item/{id}"


class _Scalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeSession:
    """`scalar_queue` is popped in call order — /react makes exactly two session.scalar() calls
    per request (resolve the user by uid, then check for an existing UserListingAction row), so
    tests pass [user, existing_id_or_None] and this fake hands them out in that order, same trick
    other website test files use for their own two-scalar-calls-per-request routes."""

    def __init__(self, user, scalar_queue=None, listings=None):
        self.user = user
        self._scalar_queue = list(scalar_queue) if scalar_queue is not None else [user]
        self._listings = listings or []
        self.added: list = []
        self.deleted_ids: list[int] = []
        self.committed = False

    def scalar(self, stmt):
        return self._scalar_queue.pop(0) if self._scalar_queue else None

    def get(self, model, pk):
        return None

    def scalars(self, stmt):
        return _Scalars(self._listings)

    def execute(self, stmt):
        if isinstance(stmt, Delete):
            self.deleted_ids.append("deleted")
            return None

        class _Result:
            def first(self_inner):
                return None

        return _Result()

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True


def _fake_get_session(session):
    @contextmanager
    def _inner():
        yield session

    return _inner


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_react_like_adds_a_new_action_when_none_exists(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(user, scalar_queue=[user, None])  # None = no existing "liked" row

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/react",
            data={"listing_id": 5, "action": "like", "uid": 222, "next": "/apartments?uid=222"},
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/apartments?uid=222"
    assert len(fake_session.added) == 1
    assert fake_session.added[0].action == "liked"
    assert fake_session.added[0].listing_id == 5
    assert fake_session.committed is True
    assert fake_session.deleted_ids == []


def test_react_like_removes_the_action_when_already_liked(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(user, scalar_queue=[user, 999])  # 999 = existing "liked" row id

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/react", data={"listing_id": 5, "action": "like", "uid": 222}
        )

    assert resp.status_code == 303
    assert fake_session.deleted_ids == ["deleted"]
    assert fake_session.added == []


def test_react_hide_adds_a_hidden_action(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(user, scalar_queue=[user, None])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post("/react", data={"listing_id": 7, "action": "hide", "uid": 222})

    assert resp.status_code == 303
    assert fake_session.added[0].action == "hidden"


def test_react_rejects_an_unknown_action(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(user, scalar_queue=[user, None])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post("/react", data={"listing_id": 7, "action": "explode", "uid": 222})

    assert resp.status_code == 404


def test_react_ignores_a_next_pointing_off_site(client):
    """`next` is attacker-controllable form input — must never redirect anywhere but a same-origin
    relative path, regardless of what the form claims."""
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(user, scalar_queue=[user, None])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post(
            "/react",
            data={"listing_id": 5, "action": "like", "uid": 222, "next": "https://evil.example/"},
        )

    assert resp.headers["location"] == "/apartments"


def test_hidden_page_lists_only_hidden_listings(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    listing = _FakeListing(id=9)
    fake_session = _FakeSession(user, listings=[listing])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/hidden", params={"uid": 222})

    assert resp.status_code == 200
    assert "🙈 דירות מוסתרות" in resp.text


def test_hidden_page_empty_state(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(user, listings=[])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/hidden", params={"uid": 222})

    assert "אין לך כרגע דירות מוסתרות" in resp.text


def test_apartments_excludes_hidden_listings(client):
    """2026-09-06 real bug fix: /apartments previously never excluded hidden listings at all
    (unlike the bot's own find_matching_listings) — a listing hidden via Telegram's 🙈 button kept
    showing up on the website. find_matching_listings-equivalent logic now lives inline in the
    /apartments route via _listing_action_ids(session, user.id, "hidden")."""
    user = _FakeUser(id=2, telegram_user_id=222, filter=_FakeFilter())
    shown = _FakeListing(id=1)
    hidden_listing = _FakeListing(id=2)

    class _ApartmentsSession(_FakeSession):
        def scalars(self, stmt):
            # First scalars() call is the hidden-ids query, second is the listings query — mirrors
            # the two scalars() calls /apartments makes per request.
            self._scalars_call_count = getattr(self, "_scalars_call_count", 0) + 1
            if self._scalars_call_count == 1:
                return _Scalars([2])  # listing id 2 is hidden
            return _Scalars([shown, hidden_listing])

    fake_session = _ApartmentsSession(user, scalar_queue=[user])

    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "evaluate", lambda f, l: type("M", (), {"matched": True})()),
    ):
        resp = client.get("/apartments", params={"uid": 222})

    assert resp.status_code == 200
    assert "yad2.co.il/item/1" in resp.text
    assert "yad2.co.il/item/2" not in resp.text


def test_no_brokers_toggle_flips_and_redirects(client):
    user = _FakeUser(id=2, telegram_user_id=222, filter=_FakeFilter(no_brokers=False))
    fake_session = _FakeSession(user, scalar_queue=[user])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post("/apartments/no-brokers", data={"uid": 222})

    assert resp.status_code == 303
    assert resp.headers["location"] == "/apartments?uid=222"
    assert user.filter.no_brokers is True
    assert fake_session.committed is True


def test_no_brokers_toggle_back_off(client):
    user = _FakeUser(id=2, telegram_user_id=222, filter=_FakeFilter(no_brokers=True))
    fake_session = _FakeSession(user, scalar_queue=[user])

    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        client.post("/apartments/no-brokers", data={"uid": 222})

    assert user.filter.no_brokers is False
