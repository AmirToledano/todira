"""Tests for the 2026-09-07 lazy, background Bright Data description fetch on the website:
/apartments and /liked kick off a fire-and-forget fetch for any listing shown to a PAYING viewer
whose description is still missing — extends scraper/notifier.py's original discovery-time-only
trigger to also cover a listing whose paying match happened AFTER discovery (a filter edited later,
a user who upgraded after the listing was scraped). See common/dorin_common/bright_data_client.py's
own module docstring for why this lives in dorin_common (shared by the scraper and website images)
rather than the old scraper/bright_data_client.py.

Same importlib-loading approach as the other website test files (see test_website_paid_access.py's
own comment) — website/main.py shares a basename with scraper/main.py so it can't go through a
bare `import main`.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location(
    "website_main_bright_data_lazy_fetch", _WEBSITE_DIR / "main.py"
)
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)


class _FakeListing:
    def __init__(self, id, description=None, url="https://yad2.co.il/item/x"):
        self.id = id
        self.description = description
        self.url = url


class _FakeGetSession:
    """A single-listing store keyed by id, supporting only the .get() call
    _ensure_description_sync makes — a fresh instance simulates a fresh `with get_session()`."""

    def __init__(self, listings: list[_FakeListing]):
        self._by_id = {listing.id: listing for listing in listings}
        self.committed = False

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, model, pk):
        return self._by_id.get(pk)

    def commit(self):
        self.committed = True


def test_fill_missing_descriptions_does_nothing_when_bright_data_not_configured():
    listing = _FakeListing(id=1, description=None)
    with (
        patch.object(website_main.bright_data_client, "is_configured", return_value=False),
        patch.object(website_main.threading, "Thread") as thread_mock,
    ):
        website_main._fill_missing_descriptions_in_background([listing])
    thread_mock.assert_not_called()


def test_fill_missing_descriptions_skips_listings_that_already_have_one():
    already_has_one = _FakeListing(id=1, description="כבר יש תיאור")
    missing = _FakeListing(id=2, description=None, url="https://yad2.co.il/item/missing")
    with (
        patch.object(website_main.bright_data_client, "is_configured", return_value=True),
        patch.object(website_main.threading, "Thread") as thread_mock,
    ):
        website_main._fill_missing_descriptions_in_background([already_has_one, missing])
    thread_mock.assert_called_once_with(
        target=website_main._ensure_description_sync,
        args=(2, "https://yad2.co.il/item/missing"),
        daemon=True,
    )


def test_fill_missing_descriptions_fires_one_thread_per_missing_listing():
    a = _FakeListing(id=1, description=None, url="https://yad2.co.il/item/a")
    b = _FakeListing(id=2, description=None, url="https://yad2.co.il/item/b")
    with (
        patch.object(website_main.bright_data_client, "is_configured", return_value=True),
        patch.object(website_main.threading, "Thread") as thread_mock,
    ):
        website_main._fill_missing_descriptions_in_background([a, b])
    assert thread_mock.call_count == 2
    started_ids = {call.kwargs["args"][0] for call in thread_mock.call_args_list}
    assert started_ids == {1, 2}


def test_ensure_description_sync_fetches_and_caches():
    session = _FakeGetSession([_FakeListing(id=5, description=None, url="https://yad2.co.il/item/5")])
    with (
        patch.object(
            website_main.bright_data_client, "fetch_listing_description", return_value="תיאור אמיתי"
        ),
        patch.object(website_main, "get_session", session),
    ):
        website_main._ensure_description_sync(5, "https://yad2.co.il/item/5")

    assert session._by_id[5].description == "תיאור אמיתי"
    assert session.committed


def test_ensure_description_sync_never_overwrites_a_description_already_filled_in():
    """Two concurrent lazy fetches for the same listing (e.g. two paying viewers loading /apartments
    at once) must not race — whichever fetch's DB write lands first wins, and the other never
    clobbers it, even if its own Bright Data response returned something different."""
    session = _FakeGetSession(
        [_FakeListing(id=5, description="כבר מולא בינתיים", url="https://yad2.co.il/item/5")]
    )
    with (
        patch.object(
            website_main.bright_data_client, "fetch_listing_description", return_value="תיאור אחר"
        ),
        patch.object(website_main, "get_session", session),
    ):
        website_main._ensure_description_sync(5, "https://yad2.co.il/item/5")

    assert session._by_id[5].description == "כבר מולא בינתיים"
    assert not session.committed


def test_ensure_description_sync_does_nothing_on_a_failed_fetch():
    session = _FakeGetSession([_FakeListing(id=5, description=None, url="https://yad2.co.il/item/5")])
    with (
        patch.object(website_main.bright_data_client, "fetch_listing_description", return_value=None),
        patch.object(website_main, "get_session", session),
    ):
        website_main._ensure_description_sync(5, "https://yad2.co.il/item/5")

    assert session._by_id[5].description is None
    assert not session.committed
