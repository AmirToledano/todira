"""2026-11-03: the owner's Sunday report (scraper/weekly_report.py)."""
from __future__ import annotations

import datetime as dt
import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import weekly_report  # noqa: E402

from todira_common import alert_hours  # noqa: E402


def _israel(day: str, hour: int) -> dt.datetime:
    return dt.datetime.fromisoformat(f"{day}T{hour:02d}:10").replace(tzinfo=alert_hours.ISRAEL).astimezone(dt.timezone.utc)


def test_it_is_due_once_on_sunday_morning():
    assert weekly_report.due(None, _israel("2026-11-08", 9)) == "2026-45"  # Sunday
    assert weekly_report.due("2026-45", _israel("2026-11-08", 10)) is None
    assert weekly_report.due(None, _israel("2026-11-08", 12)) is None
    assert weekly_report.due(None, _israel("2026-11-09", 9)) is None  # Monday


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value

    def one(self):
        return self.value

    def all(self):
        return self.value


class _Session:
    def __init__(self):
        self.answers = iter([3, 7, (1, 39), 2, [("site_visit", 40), ("bot_message", 5), ("src_fblead", 4)], 2500])

    def execute(self, query):
        return _Result(next(self.answers))


def test_the_report_is_counts_only():
    text = weekly_report.build(_Session(), dt.datetime(2026, 11, 8, 8, tzinfo=dt.timezone.utc))
    assert "משתמשים חדשים: 3" in text and "עם גישה עכשיו: 7" in text
    assert "תשלומים: 1 (₪39)" in text and "התחילו לשלם ולא סיימו: 2" in text
    assert "ביקורים באתר: 40" in text and "השתמשו בבוט: 5" in text and "דירות חדשות: 2,500" in text
    assert "תגובות לידים בפייסבוק: 4" in text
    assert "—" not in text


@pytest.mark.skipif(not os.environ.get("TODIRA_TEST_DATABASE_URL"), reason="needs a real Postgres")
def test_the_queries_run_on_postgres():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    with Session(create_engine(os.environ["TODIRA_TEST_DATABASE_URL"])) as session:
        assert "סיכום השבוע" in weekly_report.build(session, dt.datetime.now(dt.timezone.utc))
