"""Tests for _mark_delisted (scraper/main.py) — a regression guard for a real production bug
(2026-09-02) plus its follow-on fix (2026-09-03).

scraper/main.py is loaded via importlib under an explicit name rather than `sys.path.insert` +
`import main`, since website/main.py is also named main.py — see conftest.py's comment. scraper/
itself still needs to be on sys.path (conftest.py already adds it) so main.py's own
`from yad2_client import ...` etc. resolve.

_mark_delisted used to run globally across every city, not just the ones scraped this run. Once
SCRAPE_CITIES_PER_RUN started rotating a 1-city subset per run (a mechanism removed 2026-09-03 in
favor of yad2_client.py's region sweep — see that module's REGION_SLUGS comment), that meant EVERY
run delisted every listing from every OTHER city (their external_ids are never in a city-scoped
run's seen_external_ids) — found live via a production query showing literally every non-delisted
listing in the whole table belonged to the one city just scraped. The fix (scoping to
scraped_city_names) still holds after the switch to region sweeps: run_once() now derives that set
from the cities actually represented in a run's fetched listings, not from a fixed slug list.

2026-09-13: _mark_delisted also now takes an explicit `source` (Komo/Homeless going live alongside
Yad2 — see run_once()'s own _ALL_SOURCE_SCRAPERS list, filtered by _active_source_scrapers()) — each source's delisting pass must never touch
another source's rows, same reasoning as the city-scoping fix above, just one more dimension. No
live DB is available in CI, so this doesn't execute against a real database - it inspects the
*compiled SQL* of both UPDATE statements _mark_delisted builds, via a fake session that just
records what it's asked to execute, and asserts each one's `city IN (...)` AND `source = ...`
parameters are exactly what was passed - never empty, never "everything", never another source."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from todira_common.enums import Source

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"

_spec = importlib.util.spec_from_file_location("scraper_main", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)

_mark_delisted = scraper_main._mark_delisted


class _FakeUpdateResult:
    def fetchall(self):
        return []


class _RecordingSession:
    """Records every statement passed to execute() without touching a real database - just
    enough of SQLAlchemy's Session interface for _mark_delisted to run against."""

    def __init__(self):
        self.executed = []

    def execute(self, stmt):
        self.executed.append(stmt)
        return _FakeUpdateResult()

    def commit(self):
        pass


def test_mark_delisted_scopes_both_updates_to_the_scraped_cities_only():
    session = _RecordingSession()
    _mark_delisted(session, Source.YAD2, {"ext-1"}, {"קריית מוצקין"})

    assert len(session.executed) == 2  # delist pass + un-delist pass
    for stmt in session.executed:
        params = stmt.compile().params
        assert params["city_1"] == ["קריית מוצקין"]
        assert params["source_1"] == Source.YAD2


def test_mark_delisted_never_scopes_to_a_different_city_than_asked():
    session = _RecordingSession()
    _mark_delisted(session, Source.YAD2, {"ext-1"}, {"תל אביב יפו", "רמת גן"})

    for stmt in session.executed:
        params = stmt.compile().params
        assert set(params["city_1"]) == {"תל אביב יפו", "רמת גן"}
        assert "קריית מוצקין" not in params["city_1"]


def test_mark_delisted_scopes_updates_to_the_given_source_only():
    session = _RecordingSession()
    _mark_delisted(session, Source.KOMO, {"ext-1"}, {"תל אביב יפו"})

    assert len(session.executed) == 2
    for stmt in session.executed:
        params = stmt.compile().params
        assert params["source_1"] == Source.KOMO


def test_mark_delisted_only_delists_after_the_min_staleness_window():
    """2026-09-25 real bug fix — Yad2's own map API caps at ~200 markers per request (confirmed
    live: 8,552 delisted vs. 1,860 active Yad2 rent rows in production, an implausible 82% delist
    rate), so a genuinely-active listing merely outside one run's capped sample looked identical to
    a truly-removed one. The delist UPDATE (only — the un-delist pass has no such guard, since
    reappearing is always good news, no grace period needed there) must only affect rows whose
    scraped_at is already older than the staleness window — never a row just refreshed this exact
    run, which would defeat the whole point of the grace period."""
    session = _RecordingSession()
    _mark_delisted(session, Source.YAD2, {"ext-1"}, {"תל אביב יפו"}, min_hours_before_delist=5)

    delist_stmt, undelist_stmt = session.executed
    delist_sql = str(delist_stmt.compile())
    undelist_sql = str(undelist_stmt.compile())
    assert "scraped_at" in delist_sql and "make_interval" in delist_sql
    assert "scraped_at" not in undelist_sql


def test_seen_listings_are_marked_as_seen_even_when_not_restored():
    """2026-10-22: a known Komo ad is never re-fetched, so its scraped_at stayed at the day it was first stored and the
    month rule deleted ads that were still published. Every live ad a run saw gets scraped_at = now (skipping rows
    already refreshed in the last hour), scoped to that one source."""

    class _Result(_FakeUpdateResult):
        rowcount = 7

    class _Session(_RecordingSession):
        def execute(self, stmt):
            self.executed.append(stmt)
            return _Result()

    session = _Session()
    assert scraper_main._touch_seen_listings(session, Source.KOMO, {"a", "b"}) == 7
    (stmt,) = session.executed
    params = stmt.compile().params
    sql = str(stmt.compile())
    assert params["source_1"] == Source.KOMO and sorted(params["seen_ids"]) == ["a", "b"]
    assert "scraped_at" in sql and "is_delisted" in sql and "make_interval" in sql
    assert scraper_main._touch_seen_listings(_Session(), Source.KOMO, set()) == 0


def test_komo_delisting_covers_every_city_it_has_live_ads_in(monkeypatch):
    """2026-10-22: Komo's id list is nationwide; delisting was scoped only to the cities of that run's NEW ads."""
    src = (_SCRAPER_DIR / "main.py").read_text()
    assert "scraped_city_names |= _live_cities(Source.KOMO)" in src


def test_yad2_published_verdict_from_the_item_endpoint():
    assert scraper_main._yad2_still_published(None) is None  # could not ask
    assert scraper_main._yad2_still_published({}) is False  # 404/410 or no record
    assert scraper_main._yad2_still_published({"statusId": 1}) is True
    assert scraper_main._yad2_still_published({"statusId": 2}) is False
    assert scraper_main._yad2_still_published({"price": 5000}) is True  # a record without a status


def test_yad2_asks_before_hiding_and_keeps_what_is_still_published(monkeypatch):
    """2026-10-22: 47 of 60 Yad2 ads hidden as taken down were still published."""
    from todira_common import yad2_item_api

    class _Rows:
        def __init__(self, rows=()):
            self.rows = list(rows)

        def fetchall(self):
            return self.rows

        def all(self):
            return self.rows

    candidates = [(1, "https://www.yad2.co.il/item/aaa"), (2, "https://www.yad2.co.il/item/bbb"),
                  (3, "https://www.yad2.co.il/item/ccc"), (4, "https://www.yad2.co.il/item/ddd")]
    answers = {"aaa": {"statusId": 1}, "bbb": {}, "ccc": None, "ddd": {"statusId": 1}}

    class _Session:
        def __init__(self):
            self.executed = []

        def execute(self, stmt):
            self.executed.append(stmt)
            return _Rows(candidates if stmt.is_select else [])

        def commit(self):
            pass

    monkeypatch.setattr(yad2_item_api, "is_enabled", lambda: True)
    monkeypatch.setattr(yad2_item_api, "fetch_item", lambda token: answers[token])
    session = _Session()
    assert scraper_main._mark_delisted_yad2_verified(session, {"x"}, {"חיפה"}) == 1  # only bbb is gone
    updates = [str(s.compile()) for s in session.executed if not s.is_select]
    params = [s.compile().params for s in session.executed if not s.is_select]
    # un-delist the seen, hide the week-old, hide the gone, mark the published as seen
    assert any("delisted_at" in u for u in updates) and any(p.get("id_1") == [2] for p in params)
    assert any(p.get("id_1") == [1] and "scraped_at" in u for u, p in zip(updates, params))
    # stopped at the first unanswered ad (ccc): ddd was never asked, never touched
    assert not any(p.get("id_1") and 4 in p["id_1"] for p in params)


def test_komo_recheck_walks_the_whole_list_in_turn(monkeypatch):
    flags = {}
    monkeypatch.setattr(scraper_main.app_flags, "get_flag", lambda s, k: flags.get(k))
    monkeypatch.setattr(scraper_main.app_flags, "set_flag", lambda s, k, v: flags.__setitem__(k, v))

    class _Ctx:
        def __enter__(self):
            return object()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(scraper_main, "get_session", lambda: _Ctx())
    monkeypatch.setenv("KOMO_RECHECK_PER_RUN", "2")
    ids = ["1", "2", "3", "4", "5"]
    assert scraper_main._komo_recheck_slice(ids) == ["1", "2"]
    assert scraper_main._komo_recheck_slice(ids) == ["3", "4"]
    assert scraper_main._komo_recheck_slice(ids) == ["5"]
    assert scraper_main._komo_recheck_slice(ids) == ["1", "2"]  # a new lap
