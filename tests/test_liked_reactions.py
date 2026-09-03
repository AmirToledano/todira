"""Tests for _apply_reaction_sync's toggle behavior (bot/handlers/liked.py) — 2026-09-03, real
user report: pressing ❤️ on an already-liked listing (e.g. from inside /liked itself, which
re-sends the same buttons on every card) used to be a silent no-op, with no way to remove a
listing from /liked or bring one back from /hidden. Mocks get_session with a fake session object
(same idiom as tests/test_admin_messages.py's _FakeSession) rather than a real database, matching
this suite's existing DB-touching-logic convention.
"""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from unittest.mock import patch

import handlers.liked as liked_module

USER_ID = 42
LISTING_ID = 7


class _FakeUser:
    id = 1
    telegram_user_id = USER_ID
    telegram_username = "amir"
    first_name = "Amir"
    is_active = True


class _FakeSession:
    """`scalar` is called twice per like/hide reaction, in a fixed order: first by
    get_or_create_user (the User lookup — always returns the existing fake user here, so it never
    falls into the add/commit "new user" branch), then by _apply_reaction_sync's own
    already-liked/hidden check (`existing_action_id`, the thing each test actually varies)."""

    def __init__(self, existing_action_id=None):
        self._existing_action_id = existing_action_id
        self._scalar_calls = 0
        self.added = []
        self.deleted_stmts = []
        self.commits = 0

    def scalar(self, stmt):
        self._scalar_calls += 1
        if self._scalar_calls == 1:
            return _FakeUser()
        return self._existing_action_id

    def add(self, obj):
        self.added.append(obj)

    def execute(self, stmt):
        self.deleted_stmts.append(stmt)
        return SimpleNamespace()

    def commit(self):
        self.commits += 1


@contextmanager
def _wrap(fake_session):
    yield fake_session


def _apply(fake_session, action):
    with patch.object(liked_module, "get_session", lambda: _wrap(fake_session)):
        return liked_module._apply_reaction_sync(
            SimpleNamespace(id=USER_ID, username="amir", first_name="Amir"), action, LISTING_ID
        )


def test_like_first_press_inserts_and_confirms():
    session = _FakeSession(existing_action_id=None)
    toast = _apply(session, "like")

    assert toast == "נשמר ❤️"
    assert len(session.added) == 1
    assert session.added[0].action == "liked"
    assert not session.deleted_stmts  # nothing to remove yet


def test_like_second_press_removes_it_instead_of_doing_nothing():
    session = _FakeSession(existing_action_id=99)
    toast = _apply(session, "like")

    assert toast == "הוסר מהשמורים 💔"
    assert not session.added  # not re-inserted
    assert len(session.deleted_stmts) == 1


def test_hide_first_press_inserts_and_confirms():
    session = _FakeSession(existing_action_id=None)
    toast = _apply(session, "hide")

    assert toast == "הוסתר 🙈"
    assert len(session.added) == 1
    assert session.added[0].action == "hidden"


def test_hide_second_press_un_hides_it():
    session = _FakeSession(existing_action_id=123)
    toast = _apply(session, "hide")

    assert toast == "הוחזר לרשימה 👀"
    assert not session.added
    assert len(session.deleted_stmts) == 1


def test_found_still_deactivates_the_user_unaffected_by_toggle_logic():
    session = _FakeSession()
    toast = _apply(session, "found")

    assert "מזל טוב" in toast
    assert session.commits == 1
    assert not session.added
    assert not session.deleted_stmts
