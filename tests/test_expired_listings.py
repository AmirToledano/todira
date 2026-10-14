"""2026-10-14 (owner): listings are deleted a month after first being seen, so they don't take space — but only once they
are no longer published (delisted for a week, or not seen for a month): deleting a still-published ad would make the
next run announce it to every matching user again as new. Verified end to end on a local Postgres when written; CI has
no database, so these check the statement and the batching."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from sqlalchemy.dialects import postgresql  # noqa: E402

from todira_common.models import Listing  # noqa: E402

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"
_spec = importlib.util.spec_from_file_location("scraper_main_expired", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)


def _sql(clause) -> str:
    return str(clause.compile(dialect=postgresql.dialect()))


def test_only_month_old_listings_that_are_no_longer_published_are_expired():
    sql = _sql(scraper_main._expired_listings_condition(Listing.__table__))
    assert "listings.first_seen_at <" in sql  # a month after first seen
    assert "listings.is_delisted IS true" in sql  # ...and taken down,
    assert "coalesce(listings.delisted_at, listings.scraped_at) <" in sql  # ...for a week,
    assert "listings.scraped_at <" in sql  # ...or not seen at all for a month
    assert scraper_main.LISTING_RETENTION.days == 30 and scraper_main.DELISTED_GRACE.days == 7


class _FakeResult:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _FakeSession:
    def __init__(self, batches):
        self._batches = list(batches)
        self.statements = []
        self.commits = 0

    def execute(self, stmt):
        self.statements.append(stmt)
        return _FakeResult(self._batches.pop(0) if self._batches else 0)

    def commit(self):
        self.commits += 1


def test_deletes_in_small_committed_batches_until_nothing_is_left():
    batch = scraper_main._EXPIRED_DELETE_BATCH
    session = _FakeSession([batch, batch, 17])
    assert scraper_main._delete_expired_listings(session) == 2 * batch + 17
    assert session.commits == 3
    assert all(_sql(stmt).startswith("DELETE FROM listings") for stmt in session.statements)


def test_a_run_stops_after_its_batch_budget():
    batch = scraper_main._EXPIRED_DELETE_BATCH
    session = _FakeSession([batch] * (scraper_main._EXPIRED_DELETE_MAX_BATCHES + 5))
    assert scraper_main._delete_expired_listings(session) == batch * scraper_main._EXPIRED_DELETE_MAX_BATCHES
