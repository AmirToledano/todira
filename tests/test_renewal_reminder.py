"""2026-10-05: the "your access ends soon" reminder (scraper/renewal_reminder.py). The owner asked that it
really works, so this covers who is picked, what is sent, and that a period is reminded about exactly once."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

for _dir in ("website", "scraper"):
    _path = str(Path(__file__).resolve().parent.parent / _dir)
    if _path not in sys.path:
        sys.path.insert(0, _path)

import renewal_reminder as rr  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402
from telegram.error import Forbidden  # noqa: E402

NOW = dt.datetime(2026, 10, 5, 12, 0, tzinfo=dt.timezone.utc)
PAID_UNTIL = dt.datetime(2026, 10, 7, 20, 0, tzinfo=dt.timezone.utc)  # 2 days away


class _Session:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def _user(**kw):
    base = dict(
        id=1, telegram_user_id=111, language="he", paid_until=PAID_UNTIL, renewal_reminder_for=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class _Bot:
    sent: list = []
    error: Exception | None = None

    def __init__(self, token=None):
        pass

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def send_message(self, chat_id, text):
        if _Bot.error:
            raise _Bot.error
        _Bot.sent.append((chat_id, text))


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    _Bot.sent = []
    _Bot.error = None
    monkeypatch.setattr(rr, "Bot", _Bot)
    monkeypatch.setattr(rr, "signed_login_query", lambda uid: "t=TOKEN")


def _run(users, session=None):
    session = session or _Session()
    with patch.object(rr, "_due_users", lambda s, n: users):
        return asyncio.run(rr._run(session, NOW)), session


def test_telegram_user_gets_one_reminder_with_date_and_login_link_and_is_marked():
    user = _user()
    sent, session = _run([user])
    assert sent == 1
    chat_id, text = _Bot.sent[0]
    assert chat_id == 111
    assert "07.10.2026" in text  # the access end date, Israel time
    assert "/upgrade?t=TOKEN" in text
    assert user.renewal_reminder_for == PAID_UNTIL  # marked for THIS paid period
    assert session.commits == 1


def test_blocked_bot_is_marked_done_but_not_counted():
    _Bot.error = Forbidden("bot was blocked by the user")
    user = _user()
    sent, _ = _run([user])
    assert sent == 0
    assert user.renewal_reminder_for == PAID_UNTIL  # never retried


def test_other_telegram_failure_is_retried_next_run():
    _Bot.error = RuntimeError("network")
    user = _user()
    sent, session = _run([user])
    assert sent == 0
    assert user.renewal_reminder_for is None
    assert session.commits == 0


def test_a_user_without_telegram_is_not_messaged_and_is_retried_next_run():
    user = _user(telegram_user_id=None)
    sent, session = _run([user])
    assert sent == 0
    assert user.renewal_reminder_for is None
    assert session.commits == 0


def test_selection_query_is_valid_sql_and_covers_the_rules():
    class _Capture:
        def scalars(self, stmt):
            self.sql = str(stmt.compile(dialect=postgresql.dialect()))
            return []

    session = _Capture()
    assert rr._due_users(session, NOW) == []
    sql = session.sql
    for needle in ("paid_until", "renewal_reminder_for", "takbull_subscription_uniqid", "cancel_at_period_end"):
        assert needle in sql


def test_reminder_text_exists_in_all_five_languages():
    from todira_common.bot_strings import BOT_STRINGS

    entry = BOT_STRINGS["renewal.reminder"]
    for lang in ("he", "en", "ru", "fr", "ar"):
        assert "{date}" in entry[lang] and "{url}" in entry[lang]


# --- 2026-10-16: the one reminder before the free trial ends ---------------------------------------


def _trial_run(users, session=None):
    session = session or _Session()
    with patch.object(rr, "_due_trial_users", lambda s, n: users):
        return asyncio.run(rr._run_trial(session, NOW)), session


def _trial_user(**kw):
    base = dict(id=2, telegram_user_id=222, language="he", trial_ends_at=NOW + dt.timedelta(hours=20),
                trial_reminder_sent_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_trial_user_gets_one_reminder_saying_when_with_an_upgrade_link_and_is_marked():
    user = _trial_user()  # NOW is 15:00 in Israel; the trial ends 11:00 the next day
    sent, session = _trial_run([user])
    assert sent == 1
    chat_id, text = _Bot.sent[0]
    assert chat_id == 222
    assert "מחר ב־11:00" in text
    assert "/upgrade?t=TOKEN" in text
    assert user.trial_reminder_sent_at == NOW
    assert session.commits == 1


def test_trial_ending_later_today_says_today():
    assert rr._trial_when(NOW + dt.timedelta(hours=3), NOW, "he") == "היום ב־18:00"
    assert rr._trial_when(NOW + dt.timedelta(hours=20), NOW, "en") == "tomorrow at 11:00"


def test_trial_send_failure_is_retried_and_a_blocked_bot_is_marked_done():
    _Bot.error = RuntimeError("network")
    user = _trial_user()
    sent, session = _trial_run([user])
    assert (sent, user.trial_reminder_sent_at, session.commits) == (0, None, 0)
    _Bot.error = Forbidden("bot was blocked by the user")
    sent, _ = _trial_run([user])
    assert sent == 0 and user.trial_reminder_sent_at == NOW


def test_trial_user_without_telegram_is_skipped():
    sent, session = _trial_run([_trial_user(telegram_user_id=None)])
    assert sent == 0 and session.commits == 0 and _Bot.sent == []


def test_trial_selection_query_is_valid_sql_and_covers_the_rules():
    class _Capture:
        def scalars(self, stmt):
            self.sql = str(stmt.compile(dialect=postgresql.dialect()))
            return []

    session = _Capture()
    assert rr._due_trial_users(session, NOW) == []
    for needle in ("trial_ends_at", "trial_reminder_sent_at", "paid_until", "free_access_granted", "is_active"):
        assert needle in session.sql


def test_trial_texts_exist_in_all_five_languages():
    from todira_common.bot_strings import BOT_STRINGS

    for lang in ("he", "en", "ru", "fr", "ar"):
        assert "{when}" in BOT_STRINGS["trial.reminder"][lang] and "{url}" in BOT_STRINGS["trial.reminder"][lang]
        assert "{time}" in BOT_STRINGS["trial.when_today"][lang] and "{time}" in BOT_STRINGS["trial.when_tomorrow"][lang]
