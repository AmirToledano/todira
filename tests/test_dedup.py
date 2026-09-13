"""Tests for scraper/dedup.py's find_duplicate_listing — the cross-source duplicate-detection
heuristic (city + normalized street + rooms + floor + price-within-tolerance). See that module's
own docstring for why this is a heuristic (false negatives accepted, false positives avoided) and
for the exact matching rules being tested here.

No live DB in CI (same constraint as every other scraper/main.py-adjacent test in this suite) — a
fake session whose execute() returns a canned list of candidate rows stands in for the real
`select(...).where(...)` query find_duplicate_listing issues.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"

_dedup_spec = importlib.util.spec_from_file_location("scraper_dedup", _SCRAPER_DIR / "dedup.py")
dedup = importlib.util.module_from_spec(_dedup_spec)
_dedup_spec.loader.exec_module(dedup)

_main_spec = importlib.util.spec_from_file_location("scraper_main_dedup", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_main_spec)
_main_spec.loader.exec_module(scraper_main)

_normalize = scraper_main.normalize
find_duplicate_listing = dedup.find_duplicate_listing
_normalize_street_for_matching = dedup._normalize_street_for_matching
_prices_plausibly_match = dedup._prices_plausibly_match


def _make_item(*, source="yad2", city="תל אביב יפו", street="הרצל", rooms=3.0, floor=2, price=5000):
    item = _normalize(
        {
            "id": "x1",
            "url": "https://example.com/x1",
            "city": city,
            "street": street,
            "rooms": rooms,
            "floor": floor,
            "price": price,
        },
        source=source,
    )
    assert item is not None
    return item


class _CannedRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._result = _CannedRowsResult(rows)
        self.executed_stmts = []

    def execute(self, stmt):
        self.executed_stmts.append(stmt)
        return self._result


# --- _normalize_street_for_matching ------------------------------------------------------------


def test_street_normalization_strips_common_prefixes_and_punctuation():
    assert _normalize_street_for_matching("רחוב הרצל") == "הרצל"
    assert _normalize_street_for_matching("רח' הרצל") == "הרצל"
    assert _normalize_street_for_matching("הרצל") == "הרצל"


def test_street_normalization_collapses_whitespace():
    assert _normalize_street_for_matching("הרצל   12") == _normalize_street_for_matching("הרצל 12")


def test_street_normalization_returns_none_for_missing_or_empty():
    assert _normalize_street_for_matching(None) is None
    assert _normalize_street_for_matching("") is None
    assert _normalize_street_for_matching("   ") is None


# --- _prices_plausibly_match ---------------------------------------------------------------------


def test_prices_match_within_tolerance():
    assert _prices_plausibly_match(5000, 5100) is True  # well within 5%


def test_prices_dont_match_far_outside_tolerance():
    assert _prices_plausibly_match(5000, 8000) is False


def test_prices_never_match_when_either_is_none():
    assert _prices_plausibly_match(None, 5000) is False
    assert _prices_plausibly_match(5000, None) is False
    assert _prices_plausibly_match(None, None) is False


def test_price_tolerance_has_an_absolute_floor_for_cheap_listings():
    # 5% of 1000 is only 50 - the absolute floor (150) should still allow this real-world case of
    # two sources rounding/quoting a cheap listing slightly differently.
    assert _prices_plausibly_match(1000, 1120) is True


# --- find_duplicate_listing -----------------------------------------------------------------------


def test_finds_a_real_cross_source_duplicate():
    item = _make_item(source="komo")
    session = _FakeSession([(101, "רחוב הרצל", 5050)])  # same street (prefixed), close price

    assert find_duplicate_listing(session, item) == 101


def test_no_match_when_street_text_differs():
    item = _make_item(source="komo")
    session = _FakeSession([(101, "אלנבי", 5000)])

    assert find_duplicate_listing(session, item) is None


def test_no_match_when_price_is_too_far_off():
    item = _make_item(source="komo", price=5000)
    session = _FakeSession([(101, "הרצל", 9000)])

    assert find_duplicate_listing(session, item) is None


def test_no_query_at_all_when_item_is_missing_street():
    item = _make_item(source="komo", street=None)
    session = _FakeSession([(101, "הרצל", 5000)])

    assert find_duplicate_listing(session, item) is None
    assert session.executed_stmts == []  # short-circuited before ever touching the DB


def test_no_query_at_all_when_item_is_missing_rooms_or_floor():
    item_no_rooms = _make_item(source="komo", rooms=None)
    item_no_floor = _make_item(source="komo", floor=None)
    session = _FakeSession([(101, "הרצל", 5000)])

    assert find_duplicate_listing(session, item_no_rooms) is None
    assert find_duplicate_listing(session, item_no_floor) is None
    assert session.executed_stmts == []


def test_no_match_when_no_candidates_returned():
    item = _make_item(source="komo")
    session = _FakeSession([])

    assert find_duplicate_listing(session, item) is None


def test_picks_first_matching_candidate_among_several():
    item = _make_item(source="komo")
    session = _FakeSession(
        [
            (101, "אלנבי", 5000),  # different street - skipped
            (102, "רחוב הרצל", 5000),  # matches
            (103, "הרצל", 5000),  # would also match - never reached
        ]
    )

    assert find_duplicate_listing(session, item) == 102
