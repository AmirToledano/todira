"""Tests for _backfill_missing_homeless_descriptions (scraper/main.py, 2026-09-26) — the real,
unconditional catch-up for Homeless listings whose description was never filled in, mirroring
_backfill_missing_yad2_descriptions's own pattern (see that function's docstring and
test_scraper_bright_data_enrichment.py for the original Yad2 story this was modeled on).

Confirmed live via diagnose-description-coverage-per-source.yaml: only 28.6% description coverage
among recent active Homeless listings, despite _scrape_homeless's own new-listing fetch existing —
that fetch only ever gets one shot per listing (the run it's first discovered), and unlike Yad2,
Homeless had NO safety-net fallback at all before this.

Same importlib-loading + fake-session approach as test_scraper_bright_data_enrichment.py.
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
    "scraper_main_homeless_backfill", _SCRAPER_DIR / "main.py"
)
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)

_backfill = scraper_main._backfill_missing_homeless_descriptions


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _QueueSession:
    """Same one-execute-call-per-queued-response pattern as test_scraper_bright_data_enrichment.py's
    own fake — no `scalars()` method, same staleness-bug regression guard (Core table.update(), not
    ORM objects)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.executed_stmts = []
        self.committed = False

    def execute(self, stmt):
        self.executed_stmts.append(stmt)
        return self._responses.pop(0)

    def commit(self):
        self.committed = True


def test_no_missing_listings_is_a_pure_noop():
    session = _QueueSession([_Result([])])  # SELECT finds nothing missing
    result = asyncio.run(_backfill(session))
    assert result == 0
    assert session.committed is False


def test_backfills_an_existing_listing_missing_a_description():
    session = _QueueSession(
        [
            _Result([(101, "https://www.homeless.co.il/rent/viewad,101.aspx")]),  # SELECT id, url
            None,  # UPDATE (result never read)
        ]
    )

    with patch.object(
        scraper_main, "fetch_homeless_description", lambda url: "דירה משופצת ומוארת"
    ):
        result = asyncio.run(_backfill(session))

    assert result == 1
    assert session.committed is True
    update_stmt = session.executed_stmts[1]
    compiled_params = update_stmt.compile().params
    assert compiled_params["description"] == "דירה משופצת ומוארת"


def test_a_fetch_returning_none_is_not_counted_and_issues_no_update():
    session = _QueueSession(
        [
            _Result([(101, "https://www.homeless.co.il/rent/viewad,101.aspx")]),
            # no second entry — an UPDATE here would raise IndexError, proving none was issued
        ]
    )

    with patch.object(scraper_main, "fetch_homeless_description", lambda url: None):
        result = asyncio.run(_backfill(session))

    assert result == 0
    assert len(session.executed_stmts) == 1  # only the SELECT


def test_one_listing_raising_does_not_abort_the_batch():
    session = _QueueSession(
        [
            _Result(
                [
                    (101, "https://www.homeless.co.il/rent/viewad,101.aspx"),
                    (102, "https://www.homeless.co.il/rent/viewad,102.aspx"),
                ]
            ),
            None,  # UPDATE for whichever one succeeds
        ]
    )

    def _flaky_fetch(url):
        if url.endswith("101.aspx"):
            raise ConnectionError("boom")
        return "דירה יפה"

    with patch.object(scraper_main, "fetch_homeless_description", _flaky_fetch):
        result = asyncio.run(_backfill(session))

    assert result == 1
    assert session.committed is True


def test_backfill_respects_its_own_per_run_cap():
    session = _QueueSession(
        [
            _Result(
                [
                    (101, "https://www.homeless.co.il/rent/viewad,101.aspx"),
                    (102, "https://www.homeless.co.il/rent/viewad,102.aspx"),
                ]
            ),
            None,
            None,
        ]
    )

    with (
        patch.object(scraper_main, "fetch_homeless_description", lambda url: "תיאור"),
        patch.object(scraper_main, "_homeless_backfill_max_per_run", lambda: 2),
    ):
        result = asyncio.run(_backfill(session))

    assert result == 2
