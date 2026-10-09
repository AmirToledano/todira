"""todira_common.listing_enrichment (2026-10-05): display-time, background fill of Yad2 listings that are missing their
details; and the website wiring that calls it from /apartments and /liked. 2026-10-09: the fetch goes through
todira_common.yad2_detail (Yad2's own item JSON, Gemini as backup) and `details_fetched_at` marks a listing as read."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from todira_common import gemini_url_detail, listing_enrichment as le, yad2_detail
from todira_common.enums import Source

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))
_spec = importlib.util.spec_from_file_location("website_main_listing_enrichment", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)


class _L:
    def __init__(
        self, id, description=None, source=Source.YAD2, url="https://yad2.co.il/item/x", details_fetched_at=None, **cols
    ):
        self.id, self.description, self.source, self.url = id, description, source, url
        self.details_fetched_at = details_fetched_at
        self.floor_total = cols.get("floor_total")
        self.has_parking = cols.get("has_parking")
        self.has_elevator = cols.get("has_elevator")
        self.move_in_date = cols.get("move_in_date")


class _Store:
    def __init__(self, listings):
        self.by_id = {x.id: x for x in listings}
        self.commits = 0

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, model, pk):
        return self.by_id.get(pk)

    def commit(self):
        self.commits += 1


class _RecordingExecutor:
    def __init__(self):
        self.submitted = []

    def submit(self, fn, *args):
        self.submitted.append(args)


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.setenv(gemini_url_detail.ENABLED_ENV_VAR, "true")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    le._queued.clear()
    yield
    le._queued.clear()


def test_needs_enrichment_only_for_yad2_whose_details_were_never_read():
    assert le.needs_enrichment(_L(1))
    assert le.needs_enrichment(_L(1, description="יש"))  # a description alone does not mean total floors / features were read
    assert not le.needs_enrichment(_L(1, details_fetched_at=object()))
    assert not le.needs_enrichment(_L(1, source=Source.KOMO))


def test_apply_missing_updates_fills_gaps_and_never_overwrites():
    listing = _L(1, description=None, floor_total=7)
    changed = le.apply_missing_updates(listing, {"description": "חדש", "floor_total": 3, "has_parking": True})
    assert changed is True
    assert listing.description == "חדש"
    assert listing.floor_total == 7  # an existing value is kept
    assert listing.has_parking is True
    assert le.apply_missing_updates(listing, {"description": "אחר", "has_parking": False}) is False
    assert listing.description == "חדש" and listing.has_parking is True


def test_enrich_listing_sync_fetches_stores_and_commits(monkeypatch):
    listing = _L(5)
    store = _Store([listing])
    monkeypatch.setattr(le, "get_session", store)
    with patch.object(yad2_detail, "fetch_updates", lambda url: {"description": "תיאור", "has_elevator": True}):
        assert le.enrich_listing_sync(5, listing.url) is True
    assert listing.description == "תיאור" and listing.has_elevator is True
    assert listing.details_fetched_at is not None
    assert store.commits == 1


def test_enrich_listing_sync_does_nothing_when_gemini_returns_nothing_and_never_raises(monkeypatch):
    listing = _L(5)
    store = _Store([listing])
    monkeypatch.setattr(le, "get_session", store)
    with patch.object(yad2_detail, "fetch_updates", lambda url: None):
        assert le.enrich_listing_sync(5, listing.url) is False
    assert listing.description is None and store.commits == 0

    def _boom(url):
        raise RuntimeError("x")

    with patch.object(yad2_detail, "fetch_updates", _boom):
        assert le.enrich_listing_sync(5, listing.url) is False


def test_enrich_listing_sync_never_overwrites_a_description_that_appeared_meanwhile(monkeypatch):
    listing = _L(5, description="כבר מולא")
    store = _Store([listing])
    monkeypatch.setattr(le, "get_session", store)
    with patch.object(yad2_detail, "fetch_updates", lambda url: {"description": "אחר"}):
        assert le.enrich_listing_sync(5, listing.url) is False
    assert listing.description == "כבר מולא"
    assert listing.details_fetched_at is not None  # the read still happened, so it is recorded
    assert store.commits == 1


def test_enrich_listing_sync_records_an_empty_answer_as_read(monkeypatch):
    listing = _L(5)
    store = _Store([listing])
    monkeypatch.setattr(le, "get_session", store)
    with patch.object(yad2_detail, "fetch_updates", lambda url: {}):
        assert le.enrich_listing_sync(5, listing.url) is False
    assert listing.details_fetched_at is not None and store.commits == 1


def test_fill_missing_queues_only_yad2_listings_that_were_never_read(monkeypatch):
    executor = _RecordingExecutor()
    monkeypatch.setattr(le, "_executor", executor)
    listings = [
        _L(1, details_fetched_at=object()), _L(2), _L(3, source=Source.KOMO), _L(4, url="https://yad2.co.il/item/4"),
    ]
    assert le.fill_missing_in_background(listings) == 2
    assert [args[0] for args in executor.submitted] == [2, 4]


def test_fill_missing_queues_a_listing_only_once_and_the_queue_is_bounded(monkeypatch):
    executor = _RecordingExecutor()
    monkeypatch.setattr(le, "_executor", executor)
    assert le.fill_missing_in_background([_L(1)]) == 1
    assert le.fill_missing_in_background([_L(1)]) == 0  # already queued
    monkeypatch.setattr(le, "_MAX_QUEUED", 2)
    assert le.fill_missing_in_background([_L(2), _L(3), _L(4)]) == 1  # one slot left
    assert len(executor.submitted) == 2


def test_fill_missing_does_nothing_when_no_fetcher_is_on(monkeypatch):
    monkeypatch.delenv(gemini_url_detail.ENABLED_ENV_VAR)
    monkeypatch.delenv(yad2_detail.yad2_item_api.ENABLED_ENV_VAR, raising=False)
    executor = _RecordingExecutor()
    monkeypatch.setattr(le, "_executor", executor)
    assert le.fill_missing_in_background([_L(1)]) == 0
    assert executor.submitted == []


def test_website_pages_delegate_to_the_shared_background_filler():
    listings = [_L(1), _L(2)]
    with patch.object(website_main.listing_enrichment, "fill_missing_in_background") as filler:
        website_main._fill_missing_descriptions_in_background(listings)
    filler.assert_called_once_with(listings)
    assert not hasattr(website_main, "bright_data_client")  # no paid fetcher on the website any more
