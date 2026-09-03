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
from the cities actually represented in a run's fetched listings, not from a fixed slug list, but
_mark_delisted itself is unchanged — it just takes whatever city-name set it's given. No live DB is
available in CI, so this doesn't execute against a real database - it inspects the *compiled SQL*
of both UPDATE statements _mark_delisted builds, via a fake session that just records what it's
asked to execute, and asserts each one's `city IN (...)` parameter is exactly the given set - never
empty, never "everything"."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

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
    _mark_delisted(session, {"ext-1"}, {"קריית מוצקין"})

    assert len(session.executed) == 2  # delist pass + un-delist pass
    for stmt in session.executed:
        params = stmt.compile().params
        assert params["city_1"] == ["קריית מוצקין"]


def test_mark_delisted_never_scopes_to_a_different_city_than_asked():
    session = _RecordingSession()
    _mark_delisted(session, {"ext-1"}, {"תל אביב יפו", "רמת גן"})

    for stmt in session.executed:
        params = stmt.compile().params
        assert set(params["city_1"]) == {"תל אביב יפו", "רמת גן"}
        assert "קריית מוצקין" not in params["city_1"]
