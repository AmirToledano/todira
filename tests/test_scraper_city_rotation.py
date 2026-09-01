"""Tests for _select_cities_for_run (scraper/main.py) — the credit-conserving rotation that picks
a subset of cities per scraper run instead of hitting every city every run.

scraper/main.py is loaded via importlib under an explicit name rather than `sys.path.insert` +
`import main`, since website/main.py is also named main.py — see conftest.py's comment. scraper/
itself still needs to be on sys.path (conftest.py already adds it) so main.py's own
`from yad2_client import ...` etc. resolve.
"""
from __future__ import annotations

import datetime
import importlib.util
import os
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"

_spec = importlib.util.spec_from_file_location("scraper_main", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)

_select_cities_for_run = scraper_main._select_cities_for_run


CITIES = [f"city-{i}" for i in range(10)]


class _FixedDate(datetime.date):
    """Subclassing datetime.date (not a plain fake) so isinstance checks and other datetime.date
    machinery elsewhere keep working if this ever gets patched in more broadly than today()."""

    _fixed: datetime.date

    @classmethod
    def today(cls):
        return cls._fixed


def _freeze_today(monkeypatch: pytest.MonkeyPatch, day: datetime.date) -> None:
    fixed = type("_Frozen", (_FixedDate,), {"_fixed": day})
    monkeypatch.setattr(scraper_main.datetime, "date", fixed)


def test_batch_size_zero_disables_rotation_returns_all():
    assert _select_cities_for_run(CITIES, 0) == CITIES


def test_batch_size_covering_everything_disables_rotation():
    assert _select_cities_for_run(CITIES, len(CITIES)) == CITIES
    assert _select_cities_for_run(CITIES, len(CITIES) + 5) == CITIES


def test_batch_size_negative_disables_rotation():
    assert _select_cities_for_run(CITIES, -1) == CITIES


def test_returns_exactly_batch_size_cities(monkeypatch):
    _freeze_today(monkeypatch, datetime.date(2026, 1, 1))
    result = _select_cities_for_run(CITIES, 3)
    assert len(result) == 3
    assert all(city in CITIES for city in result)


def test_same_calendar_day_returns_the_same_batch(monkeypatch):
    _freeze_today(monkeypatch, datetime.date(2026, 6, 15))
    first = _select_cities_for_run(CITIES, 4)
    second = _select_cities_for_run(CITIES, 4)
    assert first == second


def test_different_calendar_days_can_return_different_batches(monkeypatch):
    _freeze_today(monkeypatch, datetime.date(2026, 1, 1))
    day1 = _select_cities_for_run(CITIES, 3)
    _freeze_today(monkeypatch, datetime.date(2026, 1, 2))
    day2 = _select_cities_for_run(CITIES, 3)
    assert day1 != day2


def test_wraps_around_the_end_of_the_list(monkeypatch):
    # 10 cities, batch of 4: start = (day_index * 4) % 10 must land in {7, 8, 9} to wrap past the
    # end of the list. Search for a day_index satisfying that instead of hand-computing one, so
    # the test's intent (verify wrap-around) doesn't hinge on redoing the modular arithmetic.
    batch_size = 4
    base = datetime.date(2026, 1, 1)
    for offset in range(len(CITIES)):
        day = base + datetime.timedelta(days=offset)
        start = (day.toordinal() * batch_size) % len(CITIES)
        if start + batch_size > len(CITIES):
            break
    else:
        pytest.fail("no day in range found a wrapping start index — test setup is wrong")

    _freeze_today(monkeypatch, day)
    result = _select_cities_for_run(CITIES, batch_size)
    assert len(result) == batch_size
    expected = CITIES[start:] + CITIES[: start + batch_size - len(CITIES)]
    assert result == expected


def test_every_city_eventually_appears_across_a_full_rotation_cycle(monkeypatch):
    batch_size = 3
    base = datetime.date(2026, 1, 1)
    covered: set[str] = set()
    for offset in range(len(CITIES)):  # one full period of the len(CITIES)-cycle modulo
        _freeze_today(monkeypatch, base + datetime.timedelta(days=offset))
        covered.update(_select_cities_for_run(CITIES, batch_size))
    assert covered == set(CITIES)


# --- _mark_delisted: regression test for a real production bug (2026-09-02) ---
#
# _mark_delisted used to run globally across every city, not just the ones scraped this run.
# Once SCRAPE_CITIES_PER_RUN started rotating a 1-city subset per run, that meant EVERY run
# delisted every listing from every OTHER city (their external_ids are never in a city-scoped
# run's seen_external_ids) - found live via a production query showing literally every
# non-delisted listing in the whole table belonged to the one city just scraped. No live DB is
# available in CI (see this suite's other tests / module docstrings for the same constraint), so
# this doesn't execute against a real database - it inspects the *compiled SQL* of both UPDATE
# statements _mark_delisted builds, via a fake session that just records what it's asked to
# execute, and asserts each one's `city IN (...)` parameter is exactly the scraped-cities set -
# never empty, never "everything".

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
