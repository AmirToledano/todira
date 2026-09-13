"""Tests for _upsert_listings (scraper/main.py) — plain insert-if-new / update-if-existing,
with price-change detection (either direction — see scraper/notifier.py for how drop vs. increase
is decided from the reported (id, old_price) pair) on the update path.

Real photo/amenity/broker enrichment used to be fetched here per-new-listing via a separate,
costly (~25 ZenRows credits each) detail-page request — rejected once that recurring cost was
understood (see PROJECT_STATE.md, 2026-09-02) in favor of a free enrichment normalize() itself
now applies from data already embedded in the search page (see yad2_client._extract_feed_records /
normalize._enrich_from_feed_record). _upsert_listings no longer calls anything expensive — these
tests lock down that it stays a plain SELECT-then-INSERT/UPDATE.

No live DB in CI (same constraint as test_scraper_city_rotation.py's _mark_delisted tests) — a
fake session with a canned, ordered queue of execute() results stands in for SQLAlchemy, matching
the exact sequence _upsert_listings issues per item: [SELECT existing-check] then [INSERT] or
[UPDATE].

2026-09-13: a genuinely-new item also triggers a dedup.find_duplicate_listing call (cross-source
duplicate detection — see scraper/dedup.py's own docstring/tests) BEFORE the INSERT. That call
only ever touches the session (queuing a THIRD response, an `.all()`-returning one) when the item
has city/street/rooms/floor all set — _make_item's minimal payload below deliberately leaves all
of those unset, so find_duplicate_listing short-circuits without executing anything and every
existing test's canned [SELECT, INSERT]/[SELECT, UPDATE] sequence is unaffected. The dedup-specific
tests near the bottom of this file use a fuller payload and queue the extra response explicitly.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"

_spec = importlib.util.spec_from_file_location("scraper_main_upsert", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)

_upsert_listings = scraper_main._upsert_listings
_normalize = scraper_main.normalize


def _make_item(external_id: str, url: str, price: int = 5000, **extra):
    item = _normalize({"id": external_id, "url": url, "price": price, **extra})
    assert item is not None
    return item


class _CannedResult:
    def __init__(self, first_value):
        self._first_value = first_value

    def first(self):
        return self._first_value


class _CannedRows:
    """Stands in for the dedup duplicate-candidate query's result, which reads via `.all()`
    (a list of candidate rows) rather than `.first()`."""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _QueueSession:
    """Returns each queued result in order, one per execute() call — the exact sequence
    _upsert_listings issues per item: [SELECT existing-check] then [INSERT] or [UPDATE]."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.executed_stmts = []

    def execute(self, stmt):
        self.executed_stmts.append(stmt)
        return self._responses.pop(0)

    def commit(self):
        pass


def test_new_listing_is_inserted_and_returns_its_new_id():
    new_item = _make_item("new-1", "https://example.com/new-1")
    session = _QueueSession(
        [
            _CannedResult(None),  # SELECT -> no existing row
            _CannedResult((5001,)),  # INSERT returning id
        ]
    )

    new_ids, price_changes = _upsert_listings(session, [new_item])
    assert new_ids == [5001]
    assert price_changes == []


def test_existing_listing_is_updated_not_inserted():
    existing_item = _make_item("existing-1", "https://example.com/existing-1", price=5000)
    session = _QueueSession(
        [
            _CannedResult((42, 5000)),  # SELECT -> existing row, same price
            _CannedResult(None),  # UPDATE result (never read)
        ]
    )

    new_ids, price_changes = _upsert_listings(session, [existing_item])
    assert new_ids == []
    assert price_changes == []


def test_price_drop_on_existing_listing_is_reported():
    existing_item = _make_item("existing-1", "https://example.com/existing-1", price=4000)
    session = _QueueSession(
        [
            _CannedResult((42, 5000)),  # SELECT -> existing row, price dropped 5000 -> 4000
            _CannedResult(None),  # UPDATE result (never read)
        ]
    )

    new_ids, price_changes = _upsert_listings(session, [existing_item])
    assert new_ids == []
    assert price_changes == [(42, 5000)]


def test_price_increase_on_existing_listing_is_reported():
    existing_item = _make_item("existing-1", "https://example.com/existing-1", price=6000)
    session = _QueueSession(
        [
            _CannedResult((42, 5000)),  # SELECT -> existing row, price rose 5000 -> 6000
            _CannedResult(None),  # UPDATE result (never read)
        ]
    )

    new_ids, price_changes = _upsert_listings(session, [existing_item])
    assert new_ids == []
    assert price_changes == [(42, 5000)]


def test_mixed_new_and_existing_items_in_one_call():
    new_item = _make_item("new-1", "https://example.com/new-1")
    existing_item = _make_item("existing-1", "https://example.com/existing-1", price=4000)

    session = _QueueSession(
        [
            _CannedResult(None),  # SELECT for new_item -> no existing row
            _CannedResult((5001,)),  # INSERT returning id
            _CannedResult((42, 5000)),  # SELECT for existing_item -> existing (id, old_price)
            _CannedResult(None),  # UPDATE result (never read)
        ]
    )

    new_ids, price_changes = _upsert_listings(session, [new_item, existing_item])
    assert new_ids == [5001]
    assert price_changes == [(42, 5000)]


# --- cross-source dedup wiring (2026-09-13) — see scraper/dedup.py for the matching heuristic ---


def _make_dedupable_item(external_id: str, url: str, source: str, price: int = 5000):
    """A new item with every field find_duplicate_listing needs (city/street/rooms/floor) set —
    unlike _make_item above, this one DOES trigger a real duplicate-candidate query."""
    return _make_item(
        external_id, url, price=price,
        source=source, city="תל אביב יפו", street="הרצל", rooms=3.0, floor=2,
    )


def test_new_item_with_no_duplicate_candidates_is_inserted_normally():
    new_item = _make_dedupable_item("new-1", "https://example.com/new-1", source="yad2")
    session = _QueueSession(
        [
            _CannedResult(None),  # SELECT existing-check -> no existing row
            _CannedRows([]),  # dedup candidate query -> no candidates
            _CannedResult((5001,)),  # INSERT returning id
        ]
    )

    new_ids, price_changes = _upsert_listings(session, [new_item])
    assert new_ids == [5001]
    assert price_changes == []
    insert_stmt = session.executed_stmts[-1]
    assert insert_stmt.compile().params.get("duplicate_of_id") is None


def test_new_item_matching_a_duplicate_candidate_is_inserted_but_excluded_from_new_ids():
    new_item = _make_dedupable_item("new-1", "https://example.com/new-1", source="komo")
    session = _QueueSession(
        [
            _CannedResult(None),  # SELECT existing-check -> no existing row
            _CannedRows([(101, "רחוב הרצל", 5050)]),  # a real cross-source match
            _CannedResult((5001,)),  # INSERT returning id (still inserted!)
        ]
    )

    new_ids, price_changes = _upsert_listings(session, [new_item])
    assert new_ids == []  # never notified/enriched as its own listing
    assert price_changes == []
    insert_stmt = session.executed_stmts[-1]
    assert insert_stmt.compile().params["duplicate_of_id"] == 101
