"""2026-11-10 (owner: a link from the bot opened a blank page for minutes): /apartments opens at once with placeholder
cards when the matches are not cached yet, and its script fetches the first batch (fragment, offset 0), which carries
the total count. With the matches cached, the page renders the cards directly as before."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_website_reactions as base  # its fakes and the loaded website module

website_main = base.website_main


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def _session(listings):
    user = base._FakeUser(id=2, telegram_user_id=222, filter=base._FakeFilter())

    class _S(base._FakeSession):
        def scalars(self, stmt):
            self._n = getattr(self, "_n", 0) + 1
            return base._Scalars([] if self._n == 1 else listings)

    return _S(user, scalar_queue=[user], listings=listings)


def test_uncached_page_opens_with_placeholders_and_the_first_batch_brings_the_count(client, monkeypatch):
    monkeypatch.setenv("APARTMENTS_DEFER_FIRST_BATCH", "1")
    website_main._match_ids_cache.clear()
    listings = [base._FakeListing(id=1), base._FakeListing(id=2)]
    with base.patch.object(website_main, "get_session", base._fake_get_session(_session(listings))):
        page = client.get("/apartments", params={"uid": 222}).text
    assert 'data-deferred="1"' in page and 'class="listing-card skeleton-card"' in page
    assert 'id="apt-total-count">…<' in page and "yad2.co.il/item/1" not in page
    with base.patch.object(website_main, "get_session", base._fake_get_session(_session(listings))):
        first = client.get("/apartments", params={"uid": 222, "offset": 0, "fragment": 1}).text
    assert 'data-total-count="2"' in first and "yad2.co.il/item/1" in first and "yad2.co.il/item/2" in first


def test_cached_matches_render_directly(client, monkeypatch):
    monkeypatch.setenv("APARTMENTS_DEFER_FIRST_BATCH", "1")
    listings = [base._FakeListing(id=1)]
    with base.patch.object(website_main, "get_session", base._fake_get_session(_session(listings))):
        client.get("/apartments", params={"uid": 222, "offset": 0, "fragment": 1})  # fills the cache
    with base.patch.object(website_main, "get_session", base._fake_get_session(_session(listings))):
        page = client.get("/apartments", params={"uid": 222}).text
    assert 'class="listing-card skeleton-card"' not in page and "yad2.co.il/item/1" in page


def test_an_empty_first_batch_shows_the_empty_state(client, monkeypatch):
    monkeypatch.setenv("APARTMENTS_DEFER_FIRST_BATCH", "1")
    website_main._match_ids_cache.clear()
    with base.patch.object(website_main, "get_session", base._fake_get_session(_session([]))):
        first = client.get("/apartments", params={"uid": 222, "offset": 0, "fragment": 1}).text
    assert 'data-total-count="0"' in first and "empty-state" in first

