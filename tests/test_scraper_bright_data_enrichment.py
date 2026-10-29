"""Tests for _enrich_new_listings_via_bright_data / _backfill_missing_yad2_descriptions (scraper/main.py).

2026-10-05: the (historically named) Bright Data enrichment fetches listing details with no paid fallback (owner decision).
2026-10-09: through todira_common/yad2_detail.py — Yad2's own item JSON first, Gemini as backup. These tests keep the
original regression guard: the fake session has NO `scalars()` method, only `execute()`. This project's session factory
is `expire_on_commit=False` (todira_common/db.py), so loading ORM `Listing` objects here, updating via Core
`table.update()` and then having run_once() re-query the same ids would silently hand back STALE pre-enrichment objects
from the identity map; the fix is plain (id, url) tuples via Core, so a revert fails loudly (AttributeError).
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
_detail = scraper_main.yad2_detail

_UPDATES = {"description": "דירה יפה ומוארת", "floor_total": 4}


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _QueueSession:
    """One queued response per execute() call — and NO `scalars()` method, deliberately."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.executed_stmts = []
        self.committed = False

    def execute(self, stmt):
        self.executed_stmts.append(stmt)
        return self._responses.pop(0)

    def commit(self):
        self.committed = True


@pytest.fixture(autouse=True)
def _detail_on(monkeypatch):
    monkeypatch.setenv(scraper_main._BRIGHT_DATA_ENRICH_MAX_PER_RUN_ENV_VAR, "15")
    monkeypatch.setenv(scraper_main._BRIGHT_DATA_BACKFILL_MAX_PER_RUN_ENV_VAR, "15")
    monkeypatch.setattr(_detail, "is_enabled", lambda: True)


def _fetch_returning(value):
    return patch.object(_detail, "fetch_updates", lambda url: value)


def test_detail_fetching_disabled_is_a_pure_noop(monkeypatch):
    monkeypatch.setattr(_detail, "is_enabled", lambda: False)
    session = _QueueSession([])  # would raise IndexError if execute() were ever called
    assert asyncio.run(_enrich(session, [1, 2, 3])) == 0
    assert asyncio.run(_backfill(session)) == 0
    assert session.executed_stmts == []


def test_backfill_is_off_when_its_cap_is_zero(monkeypatch):
    monkeypatch.setenv(scraper_main._BRIGHT_DATA_BACKFILL_MAX_PER_RUN_ENV_VAR, "0")
    session = _QueueSession([])
    assert asyncio.run(_backfill(session)) == 0
    assert session.executed_stmts == []


def test_does_not_need_the_bright_data_key(monkeypatch):
    """The Bright Data API key and kill-switch no longer gate this path."""
    monkeypatch.delenv("BRIGHT_DATA_API_KEY", raising=False)
    monkeypatch.setenv("BRIGHT_DATA_ENRICHMENT_SUSPENDED", "true")
    session = _QueueSession([_Result([(101, "https://yad2.co.il/item/101")]), None])
    with _fetch_returning(_UPDATES):
        assert asyncio.run(_enrich(session, [101])) == 1


def test_empty_new_ids_is_a_pure_noop():
    session = _QueueSession([])
    assert asyncio.run(_enrich(session, [])) == 0
    assert session.executed_stmts == []


def test_enriches_a_new_listing_and_applies_updates():
    session = _QueueSession([_Result([(101, "https://yad2.co.il/item/101")]), None])
    with _fetch_returning(_UPDATES):
        result = asyncio.run(_enrich(session, [101]))
    assert result == 1
    assert session.committed is True
    params = session.executed_stmts[1].compile().params
    assert params["description"] == "דירה יפה ומוארת"
    assert params["floor_total"] == 4


def test_no_answer_is_not_counted_and_never_falls_back_to_a_paid_fetch():
    session = _QueueSession([_Result([(101, "https://yad2.co.il/item/101")])])  # an UPDATE would raise IndexError
    assert not hasattr(scraper_main, "fetch_listing_detail_via_web_unlocker")  # no paid fetcher is even imported
    with _fetch_returning(None):
        result = asyncio.run(_enrich(session, [101]))
    assert result == 0
    assert len(session.executed_stmts) == 1


def test_an_empty_answer_marks_the_listing_as_read_but_is_not_counted():
    """{} = Yad2 answered and states nothing usable (or the ad is gone): nothing to retry, so details_fetched_at is set."""
    session = _QueueSession([_Result([(101, "https://yad2.co.il/item/101")]), None])
    with _fetch_returning({}):
        result = asyncio.run(_enrich(session, [101]))
    assert result == 0
    assert len(session.executed_stmts) == 2
    assert "details_fetched_at" in str(session.executed_stmts[1])


def test_an_answer_sets_details_fetched_at_next_to_the_fields():
    session = _QueueSession([_Result([(101, "https://yad2.co.il/item/101")]), None])
    with _fetch_returning(_UPDATES):
        asyncio.run(_enrich(session, [101]))
    assert "details_fetched_at" in str(session.executed_stmts[1])


def test_one_listing_raising_does_not_abort_the_batch():
    session = _QueueSession(
        [_Result([(101, "https://yad2.co.il/item/101"), (102, "https://yad2.co.il/item/102")]), None]
    )

    def _flaky(url):
        if url.endswith("101"):
            raise ConnectionError("boom")
        return _UPDATES

    with patch.object(_detail, "fetch_updates", _flaky):
        result = asyncio.run(_enrich(session, [101, 102]))
    assert result == 1
    assert session.committed is True


def test_enrichment_respects_the_per_run_cap():
    session = _QueueSession(
        [
            _Result([(101, "https://yad2.co.il/item/101"), (102, "https://yad2.co.il/item/102"),
                     (103, "https://yad2.co.il/item/103")]),
            None,
            None,
        ]
    )
    fetched = []

    def _tracking(url):
        fetched.append(url)
        return _UPDATES

    with (
        patch.object(_detail, "fetch_updates", _tracking),
        patch.object(scraper_main, "_bright_data_enrich_max_per_run", lambda: 2),
    ):
        result = asyncio.run(_enrich(session, [101, 102, 103]))
    assert result == 2
    assert len(fetched) == 2
    assert "103" not in "".join(fetched)


def test_default_cap_and_serial_concurrency():
    assert scraper_main._DEFAULT_BRIGHT_DATA_ENRICH_MAX_PER_RUN == 50
    assert scraper_main._BRIGHT_DATA_ENRICH_CONCURRENCY == 1


def test_backfill_no_missing_listings_is_a_pure_noop():
    session = _QueueSession([_Result([])])
    assert asyncio.run(_backfill(session)) == 0
    assert session.committed is False


def test_backfill_fetches_and_applies_updates_for_an_existing_listing():
    session = _QueueSession([_Result([(101, "https://yad2.co.il/item/101")]), None])
    with _fetch_returning(_UPDATES):
        result = asyncio.run(_backfill(session))
    assert result == 1
    assert session.committed is True
    params = session.executed_stmts[1].compile().params
    assert params["description"] == "דירה יפה ומוארת"


def test_backfill_one_listing_raising_does_not_abort_the_batch():
    session = _QueueSession(
        [_Result([(101, "https://yad2.co.il/item/101"), (102, "https://yad2.co.il/item/102")]), None]
    )

    def _flaky(url):
        if url.endswith("101"):
            raise ConnectionError("boom")
        return _UPDATES

    with patch.object(_detail, "fetch_updates", _flaky):
        result = asyncio.run(_backfill(session))
    assert result == 1
    assert session.committed is True


# --- 2026-10-09: the end-of-run catch-up that reads descriptions for floors / amenities / property type / entry date --------

from types import SimpleNamespace  # noqa: E402

_fill_from_text = scraper_main._fill_missing_fields_from_descriptions


class _TextResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def _text_row(row_id, description, **cols):
    base = {name: None for name in scraper_main.text_features.COLUMNS}
    base.update(cols)
    return SimpleNamespace(id=row_id, description=description, **base)


def test_text_catch_up_is_off_when_its_cap_is_zero(monkeypatch):
    monkeypatch.setenv(scraper_main._TEXT_FEATURES_MAX_ENV_VAR, "0")
    session = _QueueSession([])
    assert _fill_from_text(session) == 0
    assert session.executed_stmts == []


def test_text_catch_up_fills_only_empty_columns_and_marks_every_row_read(monkeypatch):
    monkeypatch.setenv(scraper_main._TEXT_FEATURES_MAX_ENV_VAR, "100")
    rows = [
        _text_row(1, "קומה 2 מתוך 5, חניה, מעלית", has_parking=False),  # parking is already known: the text must not touch it
        _text_row(2, "דירה יפה ומוארת"),  # nothing stated: still marked read
    ]
    session = _QueueSession([_TextResult(rows), None, None])
    filled = _fill_from_text(session)
    first = session.executed_stmts[1].compile().params
    second = session.executed_stmts[2].compile().params
    assert filled == 3  # floor, floor_total, has_elevator for row 1 (parking is already known); nothing for row 2
    assert "has_parking" not in first and first["floor_total"] == 5 and first["has_elevator"] is True
    assert "text_parsed_at" in str(session.executed_stmts[1]) and "text_parsed_at" in str(session.executed_stmts[2])
    assert "floor" not in second
    assert session.committed is True


def test_text_catch_up_reads_in_batches_until_nothing_is_left(monkeypatch):
    """2026-10-14: descriptions are read a batch at a time (each committed), not all TEXT_FEATURES_MAX_PER_RUN at once."""
    monkeypatch.setenv(scraper_main._TEXT_FEATURES_MAX_ENV_VAR, "5")
    monkeypatch.setattr(scraper_main, "_TEXT_FEATURES_BATCH", 2)
    batches = [[_text_row(1, "x"), _text_row(2, "x")], [_text_row(3, "x"), _text_row(4, "x")], [_text_row(5, "x")]]
    queue = []
    for batch in batches:
        queue.append(_TextResult(batch))
        queue.extend([None] * len(batch))
    session = _QueueSession(queue)
    _fill_from_text(session)
    selects = [stmt for stmt in session.executed_stmts if str(stmt).lstrip().upper().startswith("SELECT")]
    assert len(selects) == 3
    assert [stmt.compile().params.get("param_1") for stmt in selects] == [2, 2, 1]


def test_backfill_stops_when_the_run_reaches_its_time_budget(monkeypatch):
    """2026-10-19 (owner: scan every 30 minutes): the catch-up works in batches and stops at the run's time budget,
    so a run ends before the next one is due; the rest waits for the next run."""
    monkeypatch.setenv(scraper_main._BRIGHT_DATA_BACKFILL_MAX_PER_RUN_ENV_VAR, "100")
    monkeypatch.setattr(scraper_main, "_BACKFILL_BATCH", 2)
    rows = [(i, f"https://yad2.co.il/item/{i}") for i in range(1, 7)]
    left = iter([100.0, 100.0, 100.0, -1.0])  # the check before the query, two batches, then the budget is gone
    monkeypatch.setattr(scraper_main, "_run_time_left", lambda: next(left))
    session = _QueueSession([_Result(rows)] + [None] * 4)
    fetched = []

    def _fetch(url):
        fetched.append(url)
        return _UPDATES

    with patch.object(_detail, "fetch_updates", _fetch):
        assert asyncio.run(_backfill(session)) == 4
    assert len(fetched) == 4


def test_backfill_is_skipped_before_its_query_when_the_run_is_past_its_budget(monkeypatch):
    """2026-10-29: past the budget the step used to run its query and then backfill nothing."""
    monkeypatch.setenv(scraper_main._BRIGHT_DATA_BACKFILL_MAX_PER_RUN_ENV_VAR, "100")
    monkeypatch.setattr(scraper_main, "_run_time_left", lambda: -1.0)
    session = _QueueSession([])
    assert asyncio.run(_backfill(session)) == 0
    assert session.executed_stmts == []


def test_the_run_budget_is_unlimited_outside_a_run(monkeypatch):
    monkeypatch.setattr(scraper_main, "_RUN_STARTED_AT", None)
    assert scraper_main._run_time_left() == float("inf")
