"""Tests for the 2026-09-15 scrape-speed optimization in scraper/main.py — real, owner-requested,
after walking the actual run-time composition (not guessing): sources previously ran strictly
SEQUENTIALLY in run_once() (_scrape_yad2, then _scrape_komo, then _scrape_homeless), and Komo's/
Homeless's own per-genuinely-new-listing detail/description fetch loops were themselves fully
sequential too. Neither was required for correctness or safety — see _KOMO_DETAIL_FETCH_CONCURRENCY's
own module-level comment in main.py for the full reasoning (independent websites, no change in the
request rate any single site sees; Komo has zero bot-wall of its own; Homeless goes through ZenRows
either way).

Tests the two new pieces of shared machinery directly:
- _fetch_concurrently: bounded-concurrency fan-out over a blocking fetch_fn, used by both
  _scrape_komo and _scrape_homeless.
- _scrape_sources_concurrently: runs every active source's own scrape_fn() at once instead of one
  after another, used by run_once().

Same importlib-loading approach as every other scraper/main.py test in this suite.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import threading
import time
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"

_spec = importlib.util.spec_from_file_location("scraper_main_concurrency", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)


# --- _fetch_concurrently --------------------------------------------------------------------------


def test_fetch_concurrently_returns_results_in_the_same_order_as_items():
    # Each item "takes" a different amount of fake time, deliberately so the FASTEST one would
    # finish first if this just returned completion order instead of item order.
    delays = {"a": 0.03, "b": 0.0, "c": 0.02}

    def _fetch(item):
        time.sleep(delays[item])
        return f"result-{item}"

    results = asyncio.run(scraper_main._fetch_concurrently(["a", "b", "c"], _fetch, concurrency=3))

    assert results == ["result-a", "result-b", "result-c"]


def test_fetch_concurrently_turns_none_and_exceptions_into_none():
    def _fetch(item):
        if item == "raises":
            raise ConnectionError("boom")
        if item == "none":
            return None
        return "ok"

    results = asyncio.run(
        scraper_main._fetch_concurrently(["ok", "none", "raises"], _fetch, concurrency=3)
    )

    assert results == ["ok", None, None]


def test_fetch_concurrently_never_exceeds_the_concurrency_bound():
    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()

    def _fetch(item):
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.02)  # hold the "slot" long enough for others to queue up behind it
        with lock:
            in_flight -= 1
        return item

    asyncio.run(scraper_main._fetch_concurrently(list(range(10)), _fetch, concurrency=3))

    assert max_in_flight <= 3


def test_fetch_concurrently_empty_items_is_a_pure_noop():
    calls = []
    results = asyncio.run(
        scraper_main._fetch_concurrently([], lambda item: calls.append(item), concurrency=3)
    )
    assert results == []
    assert calls == []


# --- _scrape_sources_concurrently -----------------------------------------------------------------


def test_scrape_sources_concurrently_returns_results_in_source_order():
    def _slow_yad2():
        time.sleep(0.03)
        return (["yad2-item"], {"y1"}, 1, 0, True)

    def _fast_komo():
        return (["komo-item"], {"k1"}, 1, 0, True)

    active_sources = (
        (scraper_main.Source.YAD2, _slow_yad2),
        (scraper_main.Source.KOMO, _fast_komo),
    )

    results = asyncio.run(scraper_main._scrape_sources_concurrently(active_sources))

    # Yad2 is listed first and takes longer, but must still come back FIRST in the result tuple —
    # order matches `active_sources`, not completion order.
    assert results[0][0] == ["yad2-item"]
    assert results[1][0] == ["komo-item"]


def test_scrape_sources_concurrently_runs_sources_in_parallel_not_sequentially():
    # Two sources that each sleep 0.1s: sequential would take >=0.2s, concurrent should take
    # noticeably less than that.
    def _slow():
        time.sleep(0.1)
        return ([], set(), 0, 0, True)

    active_sources = (
        (scraper_main.Source.YAD2, _slow),
        (scraper_main.Source.KOMO, _slow),
    )

    start = time.monotonic()
    asyncio.run(scraper_main._scrape_sources_concurrently(active_sources))
    elapsed = time.monotonic() - start

    assert elapsed < 0.18  # well under the ~0.2s sequential execution would need


def test_scrape_sources_concurrently_single_source_still_works():
    def _one():
        return (["item"], {"id1"}, 1, 0, True)

    results = asyncio.run(
        scraper_main._scrape_sources_concurrently(((scraper_main.Source.FACEBOOK_MARKETPLACE, _one),))
    )

    assert results == ((["item"], {"id1"}, 1, 0, True),)
