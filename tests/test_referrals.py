"""2026-10-31: invite a friend, free days for both (todira_common/referrals.py)."""
from __future__ import annotations

import datetime as dt
import os
import uuid
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from todira_common import referrals  # noqa: E402

NOW = dt.datetime(2026, 11, 1, 9, 0, tzinfo=dt.timezone.utc)


def test_a_code_round_trips_and_a_made_up_one_is_refused():
    code = referrals.invite_code(12345)
    assert code.startswith("inv_") and len(code) <= 64
    assert referrals.inviter_id(code) == 12345
    forged = code[:-1] + ("0" if code[-1] != "0" else "1")
    assert referrals.inviter_id(forged) is None
    assert referrals.inviter_id(referrals.invite_code(7).replace("_7_", "_8_")) is None
    for junk in (None, "", "inv_", "ref_abc", "calculator"):
        assert referrals.inviter_id(junk) is None


def test_free_days_go_after_the_access_already_held():
    paying = SimpleNamespace(trial_ends_at=NOW - dt.timedelta(days=1), paid_until=NOW + dt.timedelta(days=20),
                             trial_reminder_sent_at=NOW)
    referrals.add_free_days(paying, 7, NOW)
    assert paying.trial_ends_at == NOW + dt.timedelta(days=27) and paying.trial_reminder_sent_at is None
    expired = SimpleNamespace(trial_ends_at=NOW - dt.timedelta(days=5), paid_until=None, trial_reminder_sent_at=None)
    referrals.add_free_days(expired, 7, NOW)
    assert expired.trial_ends_at == NOW + dt.timedelta(days=7)


def test_the_invite_message_and_share_button():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bot"))
    from handlers.invite import invite_reply

    text, markup = invite_reply(42, "he")
    link = referrals.invite_link(42)
    assert link in text and "שניכם מקבלים 7 ימים חינם" in text
    share = urlsplit(markup.inline_keyboard[0][0].url)
    query = parse_qs(share.query)
    assert share.netloc == "t.me" and query["url"] == [link] and "טודירה" in query["text"][0]


@pytest.mark.skipif(not os.environ.get("TODIRA_TEST_DATABASE_URL"), reason="needs a real Postgres")
def test_both_get_days_once_and_an_inviter_is_capped():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from todira_common.models import User

    engine = create_engine(os.environ["TODIRA_TEST_DATABASE_URL"])
    made = []
    with Session(engine) as session:
        def new_user(**fields):
            user = User(telegram_user_id=800_000_000 + uuid.uuid4().int % 99_999_999, trial_ends_at=NOW, **fields)
            session.add(user)
            session.flush()
            made.append(user)
            return user

        try:
            inviter = new_user()
            friends = [new_user(referred_by_user_id=inviter.id) for _ in range(referrals.MAX_REWARDS + 1)]
            assert referrals.reward(session, friends[0], NOW) is True
            assert referrals.reward(session, friends[0], NOW) is False  # once
            assert friends[0].trial_ends_at == NOW + dt.timedelta(days=7)
            assert inviter.trial_ends_at == NOW + dt.timedelta(days=7) and inviter.referral_days_unannounced == 7
            session.flush()
            for friend in friends[1:]:
                assert referrals.reward(session, friend, NOW) is True
                session.flush()
            assert inviter.referral_days_unannounced == 7 * referrals.MAX_REWARDS  # the 11th friend still got days
            assert referrals.reward(session, new_user(), NOW) is False  # nobody invited this one
        finally:
            session.rollback()


def test_start_remembers_the_inviter_only_when_they_exist():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bot"))
    from handlers import start

    session = SimpleNamespace(get=lambda model, key: SimpleNamespace(id=key) if key == 42 else None)
    assert start._known_inviter(session, referrals.invite_code(42)) == 42
    assert start._known_inviter(session, referrals.invite_code(43)) is None  # no such user
    assert start._known_inviter(session, "calculator") is None
