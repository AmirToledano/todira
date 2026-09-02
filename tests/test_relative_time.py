"""Tests for website/i18n.py's relative_time_label — "עלתה לפני X שניות/דקות/שעות/ימים" on a
listing card, replacing the old fixed dd/mm posted date (2026-09-02 request).
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

from i18n import relative_time_label  # noqa: E402


def _now() -> dt.datetime:
    # Computed fresh per call, not once at module import — pytest collects every test module
    # before running any of them, so a module-level "now" can drift several seconds by the time
    # a test actually runs in a big suite, flipping exact-second-boundary assertions below.
    return dt.datetime.now(dt.timezone.utc)


def test_none_posted_at_returns_empty_string():
    assert relative_time_label(None, "he") == ""


def test_under_a_minute_shows_seconds():
    text = relative_time_label(_now() - dt.timedelta(seconds=30), "he")
    assert text in ("עלתה לפני 30 שניות", "עלתה לפני 29 שניות")


def test_under_an_hour_shows_minutes():
    text = relative_time_label(_now() - dt.timedelta(minutes=5), "he")
    assert text == "עלתה לפני 5 דקות"


def test_under_a_day_shows_hours():
    text = relative_time_label(_now() - dt.timedelta(hours=3), "he")
    assert text == "עלתה לפני 3 שעות"


def test_a_day_or_more_shows_days():
    text = relative_time_label(_now() - dt.timedelta(days=2), "he")
    assert text == "עלתה לפני 2 ימים"


def test_naive_datetime_is_treated_as_utc():
    naive = (_now() - dt.timedelta(minutes=10)).replace(tzinfo=None)
    assert relative_time_label(naive, "he") == "עלתה לפני 10 דקות"


def test_future_timestamp_clamped_to_zero_not_negative():
    text = relative_time_label(_now() + dt.timedelta(seconds=5), "he")
    assert text == "עלתה לפני 0 שניות"


def test_falls_back_to_english_when_language_supported():
    text = relative_time_label(_now() - dt.timedelta(hours=2), "en")
    assert text == "Posted 2 hours ago"


def test_unit_boundaries_pick_the_larger_unit():
    assert "שניות" in relative_time_label(_now() - dt.timedelta(seconds=45), "he")
    assert "דקות" in relative_time_label(_now() - dt.timedelta(seconds=90), "he")
    assert "דקות" in relative_time_label(_now() - dt.timedelta(minutes=45), "he")
    assert "שעות" in relative_time_label(_now() - dt.timedelta(minutes=90), "he")
    assert "שעות" in relative_time_label(_now() - dt.timedelta(hours=12), "he")
    assert "ימים" in relative_time_label(_now() - dt.timedelta(hours=36), "he")
