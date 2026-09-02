"""Tests for _upsert_listings (scraper/main.py) — specifically the 2026-09-02 addition of
per-listing detail-page enrichment (see yad2_client.fetch_listing_detail /
normalize.enrich_from_detail): a real, separate ZenRows request per listing, so it must only ever
fire for a listing genuinely NEW to the DB this run, never for one already known (an update).

No live DB in CI (same constraint as test_scraper_city_rotation.py's _mark_delisted tests) — a
fake session with a canned, ordered queue of execute() results stands in for SQLAlchemy, matching
the exact sequence _upsert_listings calls (SELECT existing-check, then INSERT or UPDATE).
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


def _make_item(external_id: str, url: str, price: int = 5000):
    item = _normalize({"id": external_id, "url": url, "price": price})
    assert item is not None
    return item


class _CannedResult:
    def __init__(self, first_value):
        self._first_value = first_value

    def first(self):
        return self._first_value


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


def test_detail_fetch_and_enrich_only_called_for_genuinely_new_listings(monkeypatch):
    fetch_calls: list[str] = []
    enrich_calls: list[tuple] = []

    def fake_fetch_detail(url):
        fetch_calls.append(url)
        return {"token": "fake"}

    def fake_enrich(item, detail):
        enrich_calls.append((item.external_id, detail))
        return item.model_copy(update={"description": "enriched"})

    monkeypatch.setattr(scraper_main, "fetch_listing_detail", fake_fetch_detail)
    monkeypatch.setattr(scraper_main, "enrich_from_detail", fake_enrich)

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

    new_ids, _price_drops = _upsert_listings(session, [new_item, existing_item])

    assert fetch_calls == ["https://example.com/new-1"]
    assert [c[0] for c in enrich_calls] == ["new-1"]
    assert new_ids == [5001]


def test_failed_detail_fetch_does_not_call_enrich_and_still_inserts(monkeypatch):
    def fake_fetch_detail(url):
        return None  # e.g. no __NEXT_DATA__, network error, etc.

    def fake_enrich(item, detail):
        raise AssertionError("enrich_from_detail must not be called when detail fetch failed")

    monkeypatch.setattr(scraper_main, "fetch_listing_detail", fake_fetch_detail)
    monkeypatch.setattr(scraper_main, "enrich_from_detail", fake_enrich)

    new_item = _make_item("new-1", "https://example.com/new-1")
    session = _QueueSession(
        [
            _CannedResult(None),  # SELECT -> no existing row
            _CannedResult((5001,)),  # INSERT returning id
        ]
    )

    new_ids, _price_drops = _upsert_listings(session, [new_item])
    assert new_ids == [5001]


def test_detail_fetch_never_called_for_an_existing_listing_even_on_price_drop(monkeypatch):
    def fake_fetch_detail(url):
        raise AssertionError("must never re-fetch detail for a listing already in the DB")

    monkeypatch.setattr(scraper_main, "fetch_listing_detail", fake_fetch_detail)

    existing_item = _make_item("existing-1", "https://example.com/existing-1", price=4000)
    session = _QueueSession(
        [
            _CannedResult((42, 5000)),  # SELECT -> existing row, price dropped 5000 -> 4000
            _CannedResult(None),  # UPDATE result (never read)
        ]
    )

    new_ids, price_drops = _upsert_listings(session, [existing_item])
    assert new_ids == []
    assert price_drops == [(42, 5000)]
