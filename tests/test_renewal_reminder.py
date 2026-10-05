"""2026-10-05: the "your access ends soon" reminder (scraper/renewal_reminder.py). The owner asked that it
really works, so this covers who is picked, what is sent on which channel, that nothing is ever sent
outside the free WhatsApp window, and that a period is reminded about exactly once."""
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
        whatsapp_phone_number=None, whatsapp_notifications_opted_in=False, whatsapp_last_inbound_at=None,
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
    monkeypatch.setattr(rr.whatsapp_guard, "is_paused", lambda session: False)
    monkeypatch.setattr(rr, "signed_login_query", lambda uid: "t=TOKEN")
    monkeypatch.setattr(rr, "generate_wid_token", lambda phone: "WIDTOKEN")


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


def test_whatsapp_only_user_is_reminded_only_inside_the_free_window():
    wa_calls = []
    with patch.object(rr.whatsapp_client, "send_text_message", lambda to, body: wa_calls.append((to, body)) or True):
        closed = _user(
            telegram_user_id=None, whatsapp_phone_number="972500000000", whatsapp_notifications_opted_in=True,
            whatsapp_last_inbound_at=NOW - dt.timedelta(hours=30),
        )
        sent, _ = _run([closed])
        assert sent == 0 and wa_calls == []  # outside the window: nothing, and not marked
        assert closed.renewal_reminder_for is None

        open_ = _user(
            telegram_user_id=None, whatsapp_phone_number="972500000000", whatsapp_notifications_opted_in=True,
            whatsapp_last_inbound_at=NOW - dt.timedelta(hours=2),
        )
        sent, _ = _run([open_])
        assert sent == 1 and len(wa_calls) == 1
        assert "wid=WIDTOKEN" in wa_calls[0][1]
        assert open_.renewal_reminder_for == PAID_UNTIL


def test_whatsapp_user_not_opted_in_is_never_messaged():
    wa_calls = []
    with patch.object(rr.whatsapp_client, "send_text_message", lambda to, body: wa_calls.append(1) or True):
        user = _user(
            telegram_user_id=None, whatsapp_phone_number="972500000000", whatsapp_notifications_opted_in=False,
            whatsapp_last_inbound_at=NOW,
        )
        sent, _ = _run([user])
    assert sent == 0 and wa_calls == []


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
