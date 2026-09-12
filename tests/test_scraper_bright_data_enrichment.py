"""Tests for _enrich_new_listings_via_bright_data (scraper/main.py, 2026-09-12) — fetches each
genuinely-new listing's full detail record from Bright Data and applies
normalize._compute_detail_updates onto that DB row.

Same importlib-loading + fake-session approach as test_scraper_upsert.py, with one deliberate
extra check: the fake session here has NO `scalars()` method at all, only `execute()`. This is a
regression guard for a real bug caught before it ever ran (see PROJECT_STATE.md, 2026-09-12): this
project's session factory is `expire_on_commit=False` (dorin_common/db.py), so loading ORM
`Listing` objects here, updating the DB via Core `table.update()`, then having run_once() later
re-query those same ids would silently hand back the STALE pre-enrichment ORM objects from the
identity map. The fix was to fetch plain (id, url) tuples via Core `select(...)` instead of ORM
objects — if a future edit reverts to `session.scalars(select(Listing)...)`, these tests fail
loudly (AttributeError: no `scalars`) instead of silently reintroducing the staleness bug.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"

_spec = importlib.util.spec_from_file_location(
    "scraper_main_bright_data_enrichment", _SCRAPER_DIR / "main.py"
)
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)

_enrich = scraper_main._enrich_new_listings_via_bright_data
_bright_data_client = scraper_main.bright_data_client


class _Result:
    """Stands in for a SQLAlchemy CursorResult: supports exactly the two access patterns this
    function actually uses — `.all()` on the id/url SELECT."""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _QueueSession:
    """Same one-execute-call-per-queued-response pattern as test_scraper_upsert.py's fake — but
    NO `scalars()` method, deliberately (see module docstring)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.executed_stmts = []
        self.committed = False

    def execute(self, stmt):
        self.executed_stmts.append(stmt)
        return self._responses.pop(0)

    def commit(self):
        self.committed = True


_REAL_DETAIL = {
    "additionalDetails": {"buildingTopFloor": 4},
    "metaData": {"description": "דירה יפה ומוארת"},
}


def test_not_configured_is_a_pure_noop():
    session = _QueueSession([])  # would raise IndexError if execute() were ever called
    with patch.object(_bright_data_client, "is_configured", lambda: False):
        result = asyncio.run(_enrich(session, [1, 2, 3]))
    assert result == 0
    assert session.executed_stmts == []


def test_empty_new_ids_is_a_pure_noop():
    session = _QueueSession([])
    with patch.object(_bright_data_client, "is_configured", lambda: True):
        result = asyncio.run(_enrich(session, []))
    assert result == 0
    assert session.executed_stmts == []


def test_enriches_a_new_listing_and_applies_updates():
    session = _QueueSession(
        [
            _Result([(101, "https://yad2.co.il/item/101")]),  # SELECT id, url
            None,  # UPDATE (result never read)
        ]
    )

    with (
        patch.object(_bright_data_client, "is_configured", lambda: True),
        patch.object(
            _bright_data_client, "fetch_listing_detail_via_bright_data", lambda url: _REAL_DETAIL
        ),
    ):
        result = asyncio.run(_enrich(session, [101]))

    assert result == 1
    assert session.committed is True
    update_stmt = session.executed_stmts[1]
    # sanity: the second statement really is an UPDATE carrying our computed fields, not a re-read
    compiled_params = update_stmt.compile().params
    assert compiled_params["description"] == "דירה יפה ומוארת"
    assert compiled_params["floor_total"] == 4


def test_bright_data_returning_none_is_not_counted_and_issues_no_update():
    session = _QueueSession(
        [
            _Result([(101, "https://yad2.co.il/item/101")]),  # SELECT id, url
            # no second entry — an UPDATE here would raise IndexError, proving none was issued
        ]
    )

    with (
        patch.object(_bright_data_client, "is_configured", lambda: True),
        patch.object(_bright_data_client, "fetch_listing_detail_via_bright_data", lambda url: None),
    ):
        result = asyncio.run(_enrich(session, [101]))

    assert result == 0
    assert len(session.executed_stmts) == 1  # only the SELECT


def test_one_listing_raising_does_not_abort_the_batch():
    session = _QueueSession(
        [
            _Result(
                [
                    (101, "https://yad2.co.il/item/101"),
                    (102, "https://yad2.co.il/item/102"),
                ]
            ),  # SELECT id, url — two new listings
            None,  # UPDATE for whichever one succeeds
        ]
    )

    def _flaky_fetch(url):
        if url.endswith("101"):
            raise ConnectionError("boom")
        return _REAL_DETAIL

    with (
        patch.object(_bright_data_client, "is_configured", lambda: True),
        patch.object(_bright_data_client, "fetch_listing_detail_via_bright_data", _flaky_fetch),
    ):
        result = asyncio.run(_enrich(session, [101, 102]))

    # the raising listing is skipped, not fatal; the other one still gets enriched and counted
    assert result == 1
    assert session.committed is True
