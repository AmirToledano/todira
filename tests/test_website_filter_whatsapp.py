"""Tests for the website's /filter route resolving a WhatsApp-only account via ?wid= — the
"magic link" fix (2026-09-06) for a real gap the owner hit testing his own WhatsApp-only account:
a WhatsApp-created User has no telegram_user_id, so the existing ?uid= bot-deep-link pattern
(_get_user_by_uid, matches on telegram_user_id) could never resolve it — there was literally no
way to reach /filter for such an account before this. wid mirrors uid's exact low-trust model,
just keyed on whatsapp_phone_number instead.

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

_spec = importlib.util.spec_from_file_location("website_main_filter_whatsapp", _WEBSITE_DIR / "main.py")
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
    def __init__(self, id: int, telegram_user_id: int | None, whatsapp_phone_number: str | None):
        self.id = id
        self.telegram_user_id = telegram_user_id
        self.whatsapp_phone_number = whatsapp_phone_number
        self.first_name = "Amir"
        self.telegram_username = None
        self.filter = _FakeFilter()


class _FakeSession:
    """`scalar()` returns queued results in call order — same convention as
    test_website_auth_google.py's own _FakeSession. `users_by_pk` backs `session.get(User, pk)`,
    which is what a SUBSEQUENT request (already carrying the session cookie a successful wid
    resolution establishes) resolves through instead of ever calling scalar() again."""

    def __init__(self, scalar_results, users_by_pk: dict | None = None):
        self._scalar_results = list(scalar_results)
        self._users_by_pk = users_by_pk or {}
        self.call_count = 0
        self.committed = False

    def scalar(self, stmt):
        self.call_count += 1
        return self._scalar_results.pop(0) if self._scalar_results else None

    def commit(self):
        self.committed = True

    def get(self, model, pk):
        return self._users_by_pk.get(pk)

    def execute(self, stmt):
        # Backs base.html's header lookup (_current_user_summary) once a session is established —
        # same simplified single-user approach as test_website_auth_google.py's own _FakeSession.
        class _Result:
            def __init__(self, row):
                self._row = row

            def first(self):
                return self._row

        return _Result(next(iter(self._users_by_pk.values()), None))


def _client(session):
    @contextmanager
    def _fake_get_session():
        yield session

    with patch.object(website_main, "get_session", _fake_get_session):
        yield TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


@pytest.fixture
def whatsapp_only_user():
    return _FakeUser(id=1, telegram_user_id=None, whatsapp_phone_number="972501234567")


def test_get_filter_resolves_a_whatsapp_only_user_via_wid(whatsapp_only_user):
    session = _FakeSession(scalar_results=[whatsapp_only_user])
    for client in _client(session):
        resp = client.get("/filter?wid=972501234567")

    assert resp.status_code == 200
    assert session.call_count == 1


def test_get_filter_renders_wid_hidden_field_not_uid(whatsapp_only_user):
    session = _FakeSession(scalar_results=[whatsapp_only_user])
    for client in _client(session):
        resp = client.get("/filter?wid=972501234567")

    assert 'name="wid" value="972501234567"' in resp.text
    assert 'name="uid"' not in resp.text


def test_post_filter_update_resolves_via_wid_and_saves(whatsapp_only_user):
    session = _FakeSession(scalar_results=[whatsapp_only_user])
    for client in _client(session):
        resp = client.post(
            "/filter",
            data={"wid": "972501234567", "cities": ["חיפה"], "price_max": "6000"},
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/filter?wid=972501234567"
    assert whatsapp_only_user.filter.cities == ["חיפה"]
    assert whatsapp_only_user.filter.price_max == 6000
    assert session.committed is True


def test_post_filter_update_redirect_carries_wid_even_on_no_filter_bailout():
    user_with_no_filter = _FakeUser(id=2, telegram_user_id=None, whatsapp_phone_number="972509999999")
    user_with_no_filter.filter = None
    session = _FakeSession(scalar_results=[user_with_no_filter])
    for client in _client(session):
        resp = client.post("/filter", data={"wid": "972509999999"})

    assert resp.status_code == 303
    assert resp.headers["location"] == "/filter?wid=972509999999"


def test_uid_takes_priority_over_wid_when_a_linked_account_has_both():
    # A linked account (Telegram + WhatsApp both attached) arriving with both params in flight —
    # _resolve_user must resolve via uid first and never even attempt the wid lookup.
    linked_user = _FakeUser(id=3, telegram_user_id=555, whatsapp_phone_number="972501234567")
    session = _FakeSession(scalar_results=[linked_user])
    for client in _client(session):
        resp = client.get("/filter?uid=555&wid=972501234567")

    assert resp.status_code == 200
    assert session.call_count == 1  # only the uid lookup ran, wid was never reached


def test_no_uid_or_wid_and_no_session_shows_need_uid_page():
    session = _FakeSession(scalar_results=[])
    for client in _client(session):
        resp = client.get("/filter")

    assert resp.status_code == 200
    assert session.call_count == 0  # _resolve_user returns None without ever querying


def test_a_wid_resolution_establishes_a_session_for_every_later_page(whatsapp_only_user):
    """2026-09-06 follow-up, after the owner pointed at how the reference competitor app keeps you
    signed in on EVERY page once you land from its own magic link, not just the one page it
    happened to point at. A wid match now sets request.session["user_id"] — proven here by a
    second request that carries NO identity in its URL at all still resolving the same user,
    purely from the cookie the first request's Set-Cookie response header established."""
    session = _FakeSession(
        scalar_results=[whatsapp_only_user], users_by_pk={whatsapp_only_user.id: whatsapp_only_user}
    )
    for client in _client(session):
        first = client.get("/filter?wid=972501234567")
        assert first.status_code == 200
        assert "set-cookie" in first.headers

        second = client.get("/filter")  # no uid, no wid — only the session cookie now
        assert second.status_code == 200

    assert session.call_count == 1  # the second request never touched scalar() at all
