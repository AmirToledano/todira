"""Tests for _find_unnotified_recent_listings (scraper/main.py) — a real bug fix (2026-09-25).

A listing used to be handed to run_notifications ONLY on the one run that inserted it (or its own
price-change run). If every send for it failed that run, no SentNotification row gets written (see
notifier.py's own sent_on_any_channel gate), but the listing was never reconsidered on any later
run either — a silent, permanent notification loss with no recovery. This widens run_once()'s own
new_listings with recently-active listings that never produced even one successful 'new'
notification to anyone.

No live DB in CI (same constraint as test_scraper_delisting.py) — a fake session that just records
what it's asked to execute stands in for SQLAlchemy; this inspects the compiled SQL of the query
_find_unnotified_recent_listings builds, not real query results.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"

_spec = importlib.util.spec_from_file_location("scraper_main_notif_retry", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)

_find_unnotified_recent_listings = scraper_main._find_unnotified_recent_listings


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _RecordingSession:
    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    def scalars(self, stmt):
        self.executed.append(stmt)
        return _FakeScalarsResult(self._rows)


class _FakeListing:
    def __init__(self, id):
        self.id = id


def test_query_filters_out_delisted_and_requires_never_notified():
    session = _RecordingSession(rows=[])
    _find_unnotified_recent_listings(session, exclude_ids=set())

    assert len(session.executed) == 1
    sql = str(session.executed[0].compile())
    assert "is_delisted" in sql
    assert "NOT (EXISTS" in sql or "NOT EXISTS" in sql
    assert "scraped_at" in sql


def test_excludes_ids_already_handled_as_genuinely_new_this_run():
    session = _RecordingSession(rows=[_FakeListing(1), _FakeListing(2), _FakeListing(3)])
    result = _find_unnotified_recent_listings(session, exclude_ids={2})

    assert [listing.id for listing in result] == [1, 3]
