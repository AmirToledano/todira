"""Tests for find_new_matches_to_show (bot/handlers/apartments.py) - the dedup added 2026-09-02
after a real report: saving/re-saving a filter used to resend every single current match in full,
every time, so a user tweaking their filter a few times in a row got the same cards over and
over, flooding their chat.

find_matching_listings itself (the underlying query+evaluate() pipeline) is mocked out here - it's
already exercised elsewhere via matching.py's own extensive test suite; these tests isolate the
NEW logic (which matches are "already shown" and get skipped, and that showing one records it).
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.apartments as apartments_module

find_new_matches_to_show = apartments_module.find_new_matches_to_show


class _FakeSession:
    """already_shown_ids stands in for the SentNotification.listing_id query result - the only
    real session.scalars() call left once find_matching_listings itself is mocked out."""

    def __init__(self, already_shown_ids):
        self._already_shown_ids = list(already_shown_ids)
        self.added = []

    def scalars(self, stmt):
        return self._already_shown_ids

    def add(self, obj):
        self.added.append(obj)


def _listing(listing_id):
    return SimpleNamespace(id=listing_id)


def test_all_matches_new_when_none_previously_shown():
    session = _FakeSession(already_shown_ids=set())
    matches = [_listing(1), _listing(2), _listing(3)]
    with patch.object(apartments_module, "find_matching_listings", return_value=matches):
        total, new_to_show = find_new_matches_to_show(session, 42, object(), 10)
    assert total == 3
    assert [listing.id for listing in new_to_show] == [1, 2, 3]
    assert len(session.added) == 3


def test_already_shown_matches_are_excluded():
    session = _FakeSession(already_shown_ids={1, 2})
    matches = [_listing(1), _listing(2), _listing(3)]
    with patch.object(apartments_module, "find_matching_listings", return_value=matches):
        total, new_to_show = find_new_matches_to_show(session, 42, object(), 10)
    assert total == 3
    assert [listing.id for listing in new_to_show] == [3]
    assert len(session.added) == 1


def test_all_matches_already_shown_returns_empty_new_list_but_correct_total():
    # The exact real-world complaint: re-saving/tweaking an already-saved filter where nothing
    # new appeared since last time must not resend anything, while still reporting the real count.
    session = _FakeSession(already_shown_ids={1, 2, 3})
    matches = [_listing(1), _listing(2), _listing(3)]
    with patch.object(apartments_module, "find_matching_listings", return_value=matches):
        total, new_to_show = find_new_matches_to_show(session, 42, object(), 10)
    assert total == 3
    assert new_to_show == []
    assert session.added == []


def test_no_current_matches_at_all():
    session = _FakeSession(already_shown_ids=set())
    with patch.object(apartments_module, "find_matching_listings", return_value=[]):
        total, new_to_show = find_new_matches_to_show(session, 42, object(), 10)
    assert total == 0
    assert new_to_show == []
    assert session.added == []


def test_records_a_sent_notification_for_each_newly_shown_listing():
    session = _FakeSession(already_shown_ids=set())
    matches = [_listing(5)]
    with patch.object(apartments_module, "find_matching_listings", return_value=matches):
        find_new_matches_to_show(session, 99, object(), 10)
    assert len(session.added) == 1
    recorded = session.added[0]
    assert recorded.user_id == 99
    assert recorded.listing_id == 5
    assert recorded.reason == apartments_module.NotificationReason.NEW
