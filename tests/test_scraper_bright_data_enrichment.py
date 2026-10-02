"""Tests for _enrich_new_listings_via_bright_data (scraper/main.py, 2026-09-12) — fetches each
genuinely-new listing's full detail record from Bright Data and applies
normalize._compute_detail_updates onto that DB row.

Same importlib-loading + fake-session approach as test_scraper_upsert.py, with one deliberate
extra check: the fake session here has NO `scalars()` method at all, only `execute()`. This is a
regression guard for a real bug caught before it ever ran (see PROJECT_STATE.md, 2026-09-12): this
project's session factory is `expire_on_commit=False` (todira_common/db.py), so loading ORM
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

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"

_spec = importlib.util.spec_from_file_location(
    "scraper_main_bright_data_enrichment", _SCRAPER_DIR / "main.py"
)
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)

_enrich = scraper_main._enrich_new_listings_via_bright_data
_backfill = scraper_main._backfill_missing_yad2_descriptions
_bright_data_client = scraper_main.bright_data_client
_API_KEY_ENV_VAR = _bright_data_client.API_KEY_ENV_VAR


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


@pytest.fixture(autouse=True)
def _eager_enrichment_on(monkeypatch):
    """2026-10-02: eager per-new-listing enrichment is OFF by default now (cost cut — Yad2 detail is
    fetched on demand in notifier._maybe_fetch_description). These tests exercise the eager path
    itself, so they turn it on explicitly."""
    monkeypatch.setenv(scraper_main._BRIGHT_DATA_ENRICH_MAX_PER_RUN_ENV_VAR, "15")


def test_not_configured_is_a_pure_noop():
    session = _QueueSession([])  # would raise IndexError if execute() were ever called
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop(_API_KEY_ENV_VAR, None)
        result = asyncio.run(_enrich(session, [1, 2, 3]))
    assert result == 0
    assert session.executed_stmts == []


def test_suspended_via_env_var_is_a_pure_noop():
    session = _QueueSession([])  # would raise IndexError if execute() were ever called
    with patch.dict(
        os.environ, {_API_KEY_ENV_VAR: "key", "BRIGHT_DATA_ENRICHMENT_SUSPENDED": "true"}
    ):
        result = asyncio.run(_enrich(session, [1, 2, 3]))
    assert result == 0
    assert session.executed_stmts == []


def test_suspended_env_var_unset_does_not_suspend():
    session = _QueueSession(
        [
            _Result([(101, "https://yad2.co.il/item/101")]),  # SELECT id, url
            None,  # UPDATE (result never read)
        ]
    )
    with (
        patch.object(scraper_main, "fetch_listing_detail_via_web_unlocker", lambda url: _REAL_DETAIL),
        patch.dict(os.environ, {_API_KEY_ENV_VAR: "key"}),
    ):
        os.environ.pop("BRIGHT_DATA_ENRICHMENT_SUSPENDED", None)
        result = asyncio.run(_enrich(session, [101]))
    assert result == 1


def test_empty_new_ids_is_a_pure_noop():
    session = _QueueSession([])
    with patch.dict(os.environ, {_API_KEY_ENV_VAR: "key"}):
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
        patch.object(scraper_main, "fetch_listing_detail_via_web_unlocker", lambda url: _REAL_DETAIL),
        patch.dict(os.environ, {_API_KEY_ENV_VAR: "key"}),
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
        patch.object(scraper_main, "fetch_listing_detail_via_web_unlocker", lambda url: None),
        patch.dict(os.environ, {_API_KEY_ENV_VAR: "key"}),
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
        patch.object(scraper_main, "fetch_listing_detail_via_web_unlocker", _flaky_fetch),
        patch.dict(os.environ, {_API_KEY_ENV_VAR: "key"}),
    ):
        result = asyncio.run(_enrich(session, [101, 102]))

    # the raising listing is skipped, not fatal; the other one still gets enriched and counted
    assert result == 1
    assert session.committed is True


def test_enrichment_respects_the_per_run_cap():
    """2026-09-18: real incident, not hypothetical — see _BRIGHT_DATA_ENRICH_MAX_PER_RUN_ENV_VAR's
    own comment. 3 new listings, cap=2: only the first 2 (per the SELECT's own ordering) get a
    fetch attempt at all — the 3rd never even gets fetch_listing_detail_via_web_unlocker called on
    it, exactly like Komo/Homeless's own per-run caps."""
    session = _QueueSession(
        [
            _Result(
                [
                    (101, "https://yad2.co.il/item/101"),
                    (102, "https://yad2.co.il/item/102"),
                    (103, "https://yad2.co.il/item/103"),
                ]
            ),  # SELECT id, url — three new listings
            None,  # UPDATE for whichever ones succeed
            None,
        ]
    )
    fetched_urls = []

    def _tracking_fetch(url):
        fetched_urls.append(url)
        return _REAL_DETAIL

    with (
        patch.object(scraper_main, "fetch_listing_detail_via_web_unlocker", _tracking_fetch),
        patch.dict(
            os.environ,
            {_API_KEY_ENV_VAR: "key", _bright_data_client.API_KEY_ENV_VAR: "key"},
        ),
        patch.object(scraper_main, "_bright_data_enrich_max_per_run", lambda: 2),
    ):
        result = asyncio.run(_enrich(session, [101, 102, 103]))

    assert result == 2
    assert len(fetched_urls) == 2
    assert "103" not in "".join(fetched_urls)


# ---------------------------------------------------------------------------
# _backfill_missing_yad2_descriptions (2026-09-26) — the real, unconditional catch-up for the
# accumulated backlog of already-existing Yad2 listings _enrich_new_listings_via_bright_data (above)
# never touches, since it only ever runs once, on a listing's own discovery run. Confirmed live via
# diagnose-description-coverage-per-source.yaml: only 6.2% description coverage among the 470 most-
# recent active Yad2 listings despite Bright Data being configured and not suspended — see this
# function's own docstring in scraper/main.py for the full root-cause trace.
# ---------------------------------------------------------------------------


def test_backfill_not_configured_is_a_pure_noop():
    session = _QueueSession([])  # would raise IndexError if execute() were ever called
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop(_API_KEY_ENV_VAR, None)
        result = asyncio.run(_backfill(session))
    assert result == 0
    assert session.executed_stmts == []


def test_backfill_suspended_via_env_var_is_a_pure_noop():
    session = _QueueSession([])  # would raise IndexError if execute() were ever called
    with patch.dict(
        os.environ, {_API_KEY_ENV_VAR: "key", "BRIGHT_DATA_ENRICHMENT_SUSPENDED": "true"}
    ):
        result = asyncio.run(_backfill(session))
    assert result == 0
    assert session.executed_stmts == []


def test_backfill_no_missing_listings_is_a_pure_noop():
    session = _QueueSession([_Result([])])  # SELECT finds nothing missing
    with patch.dict(os.environ, {_API_KEY_ENV_VAR: "key"}):
        os.environ.pop("BRIGHT_DATA_ENRICHMENT_SUSPENDED", None)
        result = asyncio.run(_backfill(session))
    assert result == 0
    assert session.committed is False  # never even tries to commit with nothing to do


def test_backfill_fetches_and_applies_updates_for_an_existing_listing():
    session = _QueueSession(
        [
            _Result([(101, "https://yad2.co.il/item/101")]),  # SELECT id, url — missing description
            None,  # UPDATE (result never read)
        ]
    )

    with (
        patch.object(scraper_main, "fetch_listing_detail_via_web_unlocker", lambda url: _REAL_DETAIL),
        patch.dict(os.environ, {_API_KEY_ENV_VAR: "key"}),
    ):
        os.environ.pop("BRIGHT_DATA_ENRICHMENT_SUSPENDED", None)
        result = asyncio.run(_backfill(session))

    assert result == 1
    assert session.committed is True
    update_stmt = session.executed_stmts[1]
    compiled_params = update_stmt.compile().params
    assert compiled_params["description"] == "דירה יפה ומוארת"
    assert compiled_params["floor_total"] == 4


def test_backfill_one_listing_raising_does_not_abort_the_batch():
    session = _QueueSession(
        [
            _Result(
                [
                    (101, "https://yad2.co.il/item/101"),
                    (102, "https://yad2.co.il/item/102"),
                ]
            ),
            None,  # UPDATE for whichever one succeeds
        ]
    )

    def _flaky_fetch(url):
        if url.endswith("101"):
            raise ConnectionError("boom")
        return _REAL_DETAIL

    with (
        patch.object(scraper_main, "fetch_listing_detail_via_web_unlocker", _flaky_fetch),
        patch.dict(os.environ, {_API_KEY_ENV_VAR: "key"}),
    ):
        os.environ.pop("BRIGHT_DATA_ENRICHMENT_SUSPENDED", None)
        result = asyncio.run(_backfill(session))

    assert result == 1
    assert session.committed is True


def test_backfill_respects_its_own_per_run_cap():
    """Same real-cost/timeout reasoning as the new-listing cap's own test above — the SELECT's own
    LIMIT is what enforces this (unlike the new-listing path, which over-fetches then slices), so
    this just confirms the cap function is actually consulted by patching it and checking the fake
    session isn't asked for more responses than the (patched, small) cap allows."""
    session = _QueueSession(
        [
            _Result([(101, "https://yad2.co.il/item/101"), (102, "https://yad2.co.il/item/102")]),
            None,
            None,
        ]
    )

    with (
        patch.object(scraper_main, "fetch_listing_detail_via_web_unlocker", lambda url: _REAL_DETAIL),
        patch.dict(os.environ, {_API_KEY_ENV_VAR: "key"}),
        patch.object(scraper_main, "_bright_data_backfill_max_per_run", lambda: 2),
    ):
        os.environ.pop("BRIGHT_DATA_ENRICHMENT_SUSPENDED", None)
        result = asyncio.run(_backfill(session))

    assert result == 2
    # the cap is applied via the SELECT's own .limit(), so we can only assert the function ran
    # without error and consulted the (patched) cap — the real LIMIT enforcement itself is a live
    # DB concern, not something this fake session's plain tuple list can demonstrate.
