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
import sys
import types
from pathlib import Path

import pytest

if "patchright" not in sys.modules:
    patchright_stub = types.ModuleType("patchright")
    sync_api_stub = types.ModuleType("patchright.sync_api")
    sync_api_stub.TimeoutError = TimeoutError
    sync_api_stub.sync_playwright = None
    patchright_stub.sync_api = sync_api_stub
    sys.modules["patchright"] = patchright_stub
    sys.modules["patchright.sync_api"] = sync_api_stub

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
