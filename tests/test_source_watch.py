"""2026-11-08: the same-day warning when a source brings far fewer flats (scraper/source_watch.py)."""
import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import source_watch  # noqa: E402


def test_flags_only_a_source_far_below_its_usual():
    days = [{"yad2": 1500, "komo": 200, "homeless": 5}] * 7
    today = {"yad2": 300, "komo": 150, "homeless": 0}
    assert source_watch.low_sources(today, days) == [("yad2", 300, 1500)]


def test_a_small_source_is_never_flagged_and_a_missing_one_counts_as_zero():
    days = [{"yad2": 1500, "homeless": 10}] * 7
    assert source_watch.low_sources({}, days) == [("yad2", 0, 1500)]
