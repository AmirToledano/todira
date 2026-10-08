"""2026-10-08: Homeless pagination (scraper/main.py _homeless_read_category and friends, homeless_client.fetch_search_page).

Homeless lists ~53 cards per page at /rent/<n> and /sale/<n>; ZenRows credits are scarce, so a run reads the first pages plus a few
rolling pages from a stored cursor. These tests pin: which pages are read, how the cursor moves and wraps, that an old ad found only
by a rolling page is never announced, that a failed page costs one error and not the run, that the usual per-run delisting is off
for Homeless, and that an ad is only delisted for a deal type whose lap completed recently.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
from pathlib import Path

import pytest

import homeless_client as hc

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"
_spec = importlib.util.spec_from_file_location("scraper_main_homeless_pages", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)


def _card(card_id: str) -> dict:
    return {"id": card_id, "url": f"https://www.homeless.co.il/rent/viewad,{card_id}.aspx"}


def _no_sleep(_seconds: float) -> None:
    return None


def _pages(mapping: dict[int, list[str] | None]):
    """fetch_page stand-in: page number -> card ids (None = the fetch failed); records the pages asked for."""
    asked: list[int] = []

    def fake(_base_url, page):
        asked.append(page)
        ids = mapping.get(page, [])
        if ids is None:
            raise scraper_main.HomelessFetchError("simulated RESP001")
        return [_card(i) for i in ids]

    fake.asked = asked
    return fake


def test_page_url_page_one_is_the_base_url():
    assert hc.page_url(hc.SEARCH_PAGE_URL, 1) == "https://www.homeless.co.il/rent/"
    assert hc.page_url(hc.SEARCH_PAGE_URL, 2) == "https://www.homeless.co.il/rent/2"
    assert hc.page_url(hc.SALE_SEARCH_PAGE_URL, 40) == "https://www.homeless.co.il/sale/40"


def test_fetch_search_page_retries_a_failed_page_then_succeeds(monkeypatch):
    calls = []

    def fake_fetch(url):
        calls.append(url)
        if len(calls) < 3:
            raise hc.HomelessFetchError("RESP001")
        return "<html></html>"

    monkeypatch.setattr(hc, "_fetch_search_html", fake_fetch)
    assert hc.fetch_search_page(hc.SEARCH_PAGE_URL, 7, sleep=_no_sleep) == []
    assert calls == ["https://www.homeless.co.il/rent/7"] * 3


def test_fetch_search_page_raises_when_every_attempt_fails(monkeypatch):
    def always_fail(_url):
        raise hc.HomelessFetchError("RESP001")

    monkeypatch.setattr(hc, "_fetch_search_html", always_fail)
    with pytest.raises(hc.HomelessFetchError):
        hc.fetch_search_page(hc.SEARCH_PAGE_URL, 7, sleep=_no_sleep)


def test_a_run_reads_the_first_pages_and_the_rolling_pages_from_the_cursor():
    fetch = _pages({1: ["a1", "a2"], 2: ["b1", "b2"], 5: ["c1", "c2", "c3", "c4", "c5"], 6: ["d1", "d2", "d3", "d4", "d5"]})
    cards, rolling_only, next_cursor, errors, wrapped = scraper_main._homeless_read_category(
        "base/", 5, fetch_page=fetch, sleep=_no_sleep
    )
    assert fetch.asked == [1, 2, 5, 6]
    assert {c["id"] for c in cards} == {"a1", "a2", "b1", "b2", "c1", "c2", "c3", "c4", "c5", "d1", "d2", "d3", "d4", "d5"}
    assert rolling_only == {"c1", "c2", "c3", "c4", "c5", "d1", "d2", "d3", "d4", "d5"}  # not on the first pages
    assert (next_cursor, errors, wrapped) == (7, 0, False)


def test_an_ad_on_both_a_first_page_and_a_rolling_page_counts_as_fresh():
    fetch = _pages({1: ["a1", "shared", "a3", "a4", "a5"], 2: ["b1", "b2", "b3", "b4", "b5"], 3: ["shared", "x1", "x2", "x3", "x4", "x5"]})
    _cards, rolling_only, *_ = scraper_main._homeless_read_category("base/", 3, fetch_page=fetch, sleep=_no_sleep)
    assert "shared" not in rolling_only and "x1" in rolling_only


def test_a_page_past_the_end_wraps_the_cursor_back_to_the_start_of_the_rolling_range():
    # page 80 only repeats ads we already hold: that is the end of the list
    fetch = _pages({1: ["a1", "a2", "a3", "a4"], 2: ["b1", "b2", "b3", "b4"], 80: ["a1", "b1", "a2", "b2"]})
    cards, rolling_only, next_cursor, errors, wrapped = scraper_main._homeless_read_category(
        "base/", 80, fetch_page=fetch, sleep=_no_sleep
    )
    assert wrapped is True and next_cursor == 3 and rolling_only == set() and errors == 0
    assert fetch.asked == [1, 2, 80]  # stopped after the page that showed the end


def test_a_failed_page_costs_one_error_and_the_cursor_still_moves_on():
    fetch = _pages({1: ["a1"] * 1, 2: ["b1"], 10: None, 11: ["n1", "n2", "n3", "n4", "n5"]})
    cards, rolling_only, next_cursor, errors, wrapped = scraper_main._homeless_read_category(
        "base/", 10, fetch_page=fetch, sleep=_no_sleep
    )
    assert errors == 1 and next_cursor == 12 and wrapped is False
    assert rolling_only == {"n1", "n2", "n3", "n4", "n5"}


def test_a_failed_first_page_is_an_error_but_the_other_pages_still_count():
    fetch = _pages({1: None, 2: ["b1", "b2"], 3: ["c1", "c2", "c3", "c4", "c5"], 4: ["d1", "d2", "d3", "d4", "d5"]})
    cards, _rolling, next_cursor, errors, _wrapped = scraper_main._homeless_read_category(
        "base/", 3, fetch_page=fetch, sleep=_no_sleep
    )
    assert errors == 1 and next_cursor == 5 and len(cards) == 12


def test_the_cursor_never_points_into_the_first_pages():
    fetch = _pages({1: ["a1"], 2: ["b1"], 3: ["n1", "n2", "n3", "n4", "n5"], 4: ["m1", "m2", "m3", "m4", "m5"]})
    _c, _r, next_cursor, _e, _w = scraper_main._homeless_read_category("base/", 0, fetch_page=fetch, sleep=_no_sleep)
    assert fetch.asked == [1, 2, 3, 4] and next_cursor == 5


def test_only_a_deal_type_with_a_recent_completed_lap_is_healthy():
    now = dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.timezone.utc)
    state = {
        "rent": {"page": 9, "wrapped_at": (now - dt.timedelta(days=2)).isoformat()},
        "sale": {"page": 4, "wrapped_at": (now - dt.timedelta(days=9)).isoformat()},
    }
    assert scraper_main._homeless_healthy_deal_types(state, now) == {"rent"}
    assert scraper_main._homeless_healthy_deal_types({"rent": {"page": 3, "wrapped_at": None}}, now) == set()
    assert scraper_main._homeless_healthy_deal_types({}, now) == set()


def test_pagination_is_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("HOMELESS_PAGINATION", raising=False)
    assert not scraper_main._homeless_pagination_enabled()
    monkeypatch.setenv("HOMELESS_PAGINATION", "true")
    assert scraper_main._homeless_pagination_enabled()


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.updates = 0

    def execute(self, statement):
        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        if statement.__class__.__name__ == "Update":
            self.updates += 1
            return _Result([])
        return _Result(self.rows)

    def commit(self):
        return None


def test_older_ads_found_only_by_a_rolling_page_are_stored_quietly():
    scraper_main._HOMELESS_ROLLING_ONLY_IDS.clear()
    scraper_main._HOMELESS_ROLLING_ONLY_IDS.update({"old-1"})
    session = _FakeSession([(1, "old-1"), (2, "fresh-1")])
    assert scraper_main._quiet_backlog(session, [1, 2]) == [2]
    assert session.updates == 1
    scraper_main._HOMELESS_ROLLING_ONLY_IDS.clear()


def test_nothing_is_quieted_when_no_rolling_ads_were_found():
    scraper_main._HOMELESS_ROLLING_ONLY_IDS.clear()
    scraper_main._KOMO_BACKLOG_IDS.clear()
    session = _FakeSession([(1, "x")])
    assert scraper_main._quiet_backlog(session, [1]) == [1]
    assert session.updates == 0


def test_homeless_is_a_partial_view_source_only_while_pagination_is_on(monkeypatch):
    monkeypatch.setenv("HOMELESS_PAGINATION", "true")
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_load_homeless_cursor", lambda: {})
    monkeypatch.setattr(scraper_main, "_save_homeless_cursor", lambda state: None)
    monkeypatch.setattr(
        scraper_main,
        "_homeless_read_category",
        lambda base_url, cursor: ([_card("h1")], set(), 3, 0, False),
    )
    monkeypatch.setattr(scraper_main, "_fetch_concurrently", lambda *a, **k: _noop_coro())
    monkeypatch.setattr(scraper_main, "_homeless_max_new_description_fetches_per_run", lambda: 0)
    scraper_main._PARTIAL_VIEW_SOURCES.discard(scraper_main.Source.HOMELESS)
    try:
        scraper_main._scrape_homeless()
        assert scraper_main.Source.HOMELESS in scraper_main._PARTIAL_VIEW_SOURCES
    finally:
        scraper_main._PARTIAL_VIEW_SOURCES.discard(scraper_main.Source.HOMELESS)
        scraper_main._HOMELESS_ROLLING_ONLY_IDS.clear()


async def _noop_coro():
    return []


# --- Komo catch-up backlog (2026-10-08) ------------------------------------------------------------------------------------


def test_komo_ads_far_below_the_newest_known_id_are_backlog():
    known = {"4941000", "4940900", "100"}
    backlog = scraper_main._komo_backlog_ids(["4941050", "4939000", "4912000", "4940000"], known)
    # newest known 4941000: gap 1500 allowed, 4939000 (2000 below) and 4912000 are old, 4941050 and 4940000 (1000 below) are not
    assert backlog == {"4939000", "4912000"}


def test_komo_has_no_backlog_rule_without_a_reference_id():
    assert scraper_main._komo_backlog_ids(["1", "2"], set()) == set()
    assert scraper_main._komo_backlog_ids(["1", "2"], {"not-a-number"}) == set()


def test_komo_backlog_ads_are_stored_quietly_and_fresh_ones_still_announced():
    scraper_main._HOMELESS_ROLLING_ONLY_IDS.clear()
    scraper_main._KOMO_BACKLOG_IDS.clear()
    scraper_main._KOMO_BACKLOG_IDS.update({"old-komo"})
    session = _FakeSession([(1, "old-komo"), (2, "fresh-komo")])
    assert scraper_main._quiet_backlog(session, [1, 2]) == [2]
    assert session.updates == 1
    scraper_main._KOMO_BACKLOG_IDS.clear()
