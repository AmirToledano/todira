"""Tests for todira_common/users.py's get_or_create_user — a real bug
fix (2026-09-25) for a plain SELECT-then-INSERT race, found via a live code-review pass.

Two genuinely concurrent updates for the same brand-new user can both pass the existing-user SELECT
before either one's INSERT/commit lands, so the second one to commit hits the DB's own unique
constraint (telegram_user_id). That used to bubble up as an unhandled
exception instead of resolving to the row the other, winning request already created — the same
real incident class as website/main.py's auth_google_create_account race, fixed the same way.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from sqlalchemy.exc import IntegrityError

from todira_common.users import get_or_create_user


class _FakeSession:
    def __init__(self, scalar_results, commit_raises=None):
        self._scalar_results = list(scalar_results)
        self.added: list = []
        self.rolled_back = False
        self.committed_count = 0
        self._commit_raises = commit_raises

    def scalar(self, stmt):
        return self._scalar_results.pop(0) if self._scalar_results else None

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed_count += 1
        if self._commit_raises is not None and self.committed_count == 1:
            raise self._commit_raises

    def rollback(self):
        self.rolled_back = True


def test_get_or_create_user_returns_the_existing_row_without_inserting():
    existing = SimpleNamespace(id=1, telegram_user_id=555)
    session = _FakeSession(scalar_results=[existing])
    tg_user = SimpleNamespace(id=555, username="amirt", first_name="Amir")

    result = get_or_create_user(session, tg_user)

    assert result is existing
    assert session.added == []
    assert session.committed_count == 0


def test_get_or_create_user_recovers_from_a_genuine_concurrent_insert_race():
    winner = SimpleNamespace(id=2, telegram_user_id=555)
    session = _FakeSession(
        # 1st scalar(): the existing-user check, before either INSERT — finds nothing (the race).
        # 2nd scalar(): the post-IntegrityError recovery lookup — finds the row the OTHER
        # concurrent request just committed.
        scalar_results=[None, winner],
        commit_raises=IntegrityError("insert", {}, Exception("unique violation")),
    )
    tg_user = SimpleNamespace(id=555, username="amirt", first_name="Amir")

    result = get_or_create_user(session, tg_user)

    assert result is winner
    assert session.rolled_back is True
