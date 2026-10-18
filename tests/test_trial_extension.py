"""2026-10-18 (owner): the free trial is 10 days, everyone already registered got 7 more (migration 0030), Telegram
users get one message about it (bot/announce_trial_extension.py) and signed-in site visitors see a notice."""
from __future__ import annotations

import asyncio
import datetime as dt
import importlib.util
import io
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import announce_trial_extension as announce
from telegram.error import Forbidden, TelegramError

_ROOT = Path(__file__).resolve().parent.parent
_WEBSITE_DIR = _ROOT / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))
_spec = importlib.util.spec_from_file_location("website_main_trial_gift", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

import i18n  # noqa: E402

NOW = dt.datetime.now(dt.timezone.utc)


def test_new_accounts_get_ten_days_by_default():
    from todira_common.models import User

    assert "10 days" in str(User.__table__.c.trial_ends_at.server_default.arg)
    migration = (_ROOT / "migrations" / "versions" / "0030_ten_day_trial.py").read_text()
    assert "interval '7 days'" in migration and "interval '10 days'" in migration


def test_no_page_still_promises_three_days():
    for key in ("home.stat_free_value", "home.faq3_a", "onboarding.trial_title", "terms.s1_body", "terms.s10_body"):
        for lang, text in i18n.TRANSLATIONS[key].items():
            assert "10" in text, (key, lang)
            assert not re.search(r"(?<![\d.,])3[\s-]*(?:ימי|ימים|day|дн|jour|أيام)", text), (key, lang)


def test_the_message_names_the_new_end_date_in_israel_time():
    end = dt.datetime(2026, 10, 28, 22, 30, tzinfo=dt.timezone.utc)  # 29.10 01:30 in Israel
    text = announce.message_for("he", end)
    assert "29.10" in text and "7 ימים" in text and "/apartments" in text


def test_each_chat_gets_it_once_and_blocked_chats_are_counted():
    end = NOW + dt.timedelta(days=5)
    targets = [(1, "he", end), (2, "en", end), (3, "he", end), (4, "he", end)]
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=[None, Forbidden("blocked"), TelegramError("x")]))
    log = io.StringIO()
    counts = asyncio.run(announce.send_all(bot, targets, already_sent={1}, log_file=log))
    assert counts == {"sent": 1, "skipped_already_sent": 1, "blocked": 1, "failed": 1}
    assert log.getvalue() == "2\n"  # only the chat it reached is recorded
    assert "English" not in bot.send_message.call_args_list[0].kwargs["text"]
    assert "gift" in bot.send_message.call_args_list[0].kwargs["text"]


def _row(**overrides):
    values = dict(created_at=NOW - dt.timedelta(days=3), trial_ends_at=NOW + dt.timedelta(days=4), paid_until=None,
                  free_access_granted=False)
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    "overrides, shown",
    [
        ({}, True),
        ({"trial_ends_at": NOW - dt.timedelta(hours=1)}, False),  # trial over
        ({"paid_until": NOW + dt.timedelta(days=3)}, False),  # paid
        ({"free_access_granted": True}, False),
        ({"created_at": website_main.TRIAL_GIFT_CUTOFF + dt.timedelta(hours=1)}, False),  # signed up after the change
    ],
)
def test_the_site_notice_is_only_for_accounts_the_extension_helped(overrides, shown):
    if NOW >= website_main.TRIAL_GIFT_NOTICE_UNTIL:
        pytest.skip("the notice period is over")
    assert (website_main._trial_gift_until(_row(**overrides)) is not None) is shown


def test_everyone_registered_before_gets_access_until_26_10_at_10_israel_time():
    migration = (_ROOT / "migrations" / "versions" / "0031_trial_until_26_10.py").read_text()
    assert "2026-10-26 07:00:00+00" in migration  # 10:00 Israel time (UTC+3)
    assert "trial_ends_at < " in migration  # never shortens a later trial
    assert "pass_test" in migration
