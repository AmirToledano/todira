"""2026-10-20 (owner): the morning summary in his inbox group."""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))
_spec = importlib.util.spec_from_file_location("daily_summary_mod", _WEBSITE_DIR / "daily_summary.py")
daily_summary = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(daily_summary)


def test_yesterday_is_the_israel_day_before():
    start, end = daily_summary.yesterday_bounds(dt.datetime(2026, 10, 20, 6, 0, tzinfo=dt.timezone.utc))  # 09:00 Israel
    assert start.isoformat() == "2026-10-19T00:00:00+03:00" and end.isoformat() == "2026-10-20T00:00:00+03:00"


def test_the_message_has_the_numbers_and_nothing_personal():
    text = daily_summary.summary_text({
        "date": "19.10", "signups": 7, "payments": 2, "income": 69.8, "alerts": 1234, "alerted_users": 40,
        "new_listings": 2300, "messages": 1, "paying_now": 5, "trial_now": 60, "users_total": 140,
    })
    assert "19.10" in text and "נרשמו: <b>7</b>" in text and "₪69.8" in text and "1,234" in text and "2,300" in text
    assert "5 משלמים, 60 בתקופת ניסיון, 140 משתמשים" in text


def test_the_message_has_the_site_and_trial_lines():
    text = daily_summary.summary_text({
        "date": "23.10", "signups": 0, "payments": 0, "income": 0, "alerts": 10, "alerted_users": 2,
        "new_listings": 5, "messages": 0, "paying_now": 0, "trial_now": 24, "users_total": 26,
        "visitors": 15, "sources": {"instagram": 2, "other": 1}, "bot_clicks": 3, "assistant_questions": 4,
        "bot_active": 6, "trial_ending": [("26.10", 3), ("27.10", 11)],
    })
    assert "נכנסו לאתר: <b>15</b> (הגיעו מ: אינסטגרם 2, אחר 1)" in text
    assert "עברו מהאתר לבוט: <b>3</b>" in text and "שאלות לעוזר באתר: <b>4</b>" in text
    assert "פעילים בבוט: <b>6</b>" in text
    assert "ניסיון נגמר השבוע: <b>14</b> (26.10 (3), 27.10 (11))" in text


def test_it_goes_to_the_inbox_group_first(monkeypatch):
    from todira_common import owner_inbox

    monkeypatch.setattr(owner_inbox, "inbox_chat_id", lambda fresh=False: "-100123")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("OWNER_TELEGRAM_USER_ID", "999")

    class _Resp:
        status_code = 200

    with patch.object(daily_summary.httpx, "post", return_value=_Resp()) as post:
        assert daily_summary.send("hi") is True
    assert post.call_args.kwargs["json"]["chat_id"] == "-100123"


def test_the_job_is_scheduled_in_the_morning():
    values = (Path(__file__).resolve().parent.parent / "charts" / "todira" / "values.yaml").read_text()
    assert 'dailySummary:\n  schedule: "52 8 * * *"' in values
