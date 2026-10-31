"""2026-10-31: held alerts and the morning check-in against a real Postgres (the SQL is the point). Runs only when
TODIRA_TEST_DATABASE_URL points at a migrated database; every row it makes is removed at the end."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("TODIRA_TEST_DATABASE_URL"), reason="needs a real Postgres")

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

import checkin  # noqa: E402
import notifier  # noqa: E402
from sqlalchemy import create_engine, delete  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from todira_common import alert_hours  # noqa: E402
from todira_common.models import ActivityDay, Filter, HeldAlert, Listing, SentNotification, User  # noqa: E402


@pytest.fixture
def db():
    engine = create_engine(os.environ["TODIRA_TEST_DATABASE_URL"])
    with Session(engine) as session:
        made: list = []
        yield session, made
        session.rollback()
        for row in reversed(made):
            session.delete(session.merge(row))
        session.commit()


def _israel(day: str, hour: int) -> dt.datetime:
    return dt.datetime.fromisoformat(day).replace(hour=hour, tzinfo=alert_hours.ISRAEL).astimezone(dt.timezone.utc)


def _user_with_filter(session, made, **user_fields):
    tg = 900_000_000 + uuid.uuid4().int % 99_999_999
    user = User(telegram_user_id=tg, language="he", **user_fields)
    session.add(user)
    session.flush()
    made.append(user)
    session.add(Filter(user_id=user.id, deal_type="rent", cities=["תל אביב"]))
    session.commit()
    return user


def _listing(session, made, first_seen_at):
    listing = Listing(
        source="yad2", external_id=f"test-{uuid.uuid4().hex}", url="https://example.invalid/x", deal_type="rent",
        price=5000, rooms=3, city="תל אביב", first_seen_at=first_seen_at,
    )
    session.add(listing)
    session.commit()
    made.append(listing)
    return listing


def test_a_held_match_goes_out_when_the_hours_open(db):
    session, made = db
    night = _israel("2026-11-01", 7)
    user = _user_with_filter(session, made, alert_from_hour=9, alert_to_hour=20)
    listing = _listing(session, made, night)

    send = AsyncMock(return_value=True)
    with (
        patch.object(notifier, "send_listing_card", send),
        patch.object(notifier, "_complete_card_fields", AsyncMock()),
        patch.object(notifier, "_below_area_pct", return_value=None),
        patch.object(notifier.asyncio, "sleep", AsyncMock()),
    ):
        asyncio.run(notifier._notify_new_matches(SimpleNamespace(), session, listing, now=night))
        send.assert_not_called()
        assert session.get(HeldAlert, (user.id, listing.id)) is not None

        # still closed at 08:00: nothing happens
        assert asyncio.run(notifier._release_held(SimpleNamespace(), session, _israel("2026-11-01", 8), None)) == 0
        assert session.get(HeldAlert, (user.id, listing.id)) is not None

        sent = asyncio.run(notifier._release_held(SimpleNamespace(), session, _israel("2026-11-01", 9), None))
    assert sent == 1
    assert send.await_args.args[1] == user.telegram_user_id
    session.expire_all()
    assert session.get(HeldAlert, (user.id, listing.id)) is None
    session.execute(delete(SentNotification).where(SentNotification.user_id == user.id))
    session.commit()


def test_the_check_in_asks_only_someone_with_alerts_every_day_and_no_activity(db):
    session, made = db
    now = _israel("2026-11-04", 9)
    quiet = _user_with_filter(session, made)
    active = _user_with_filter(session, made)
    listings = [_listing(session, made, now - dt.timedelta(days=5)) for _ in range(15)]
    for user in (quiet, active):
        for day_back in (1, 2, 3):
            for listing in listings[(day_back - 1) * 5: day_back * 5]:
                session.add(SentNotification(user_id=user.id, listing_id=listing.id, reason="new",
                                             sent_at=_israel("2026-11-04", 12) - dt.timedelta(days=day_back)))
    session.add(ActivityDay(day=dt.date(2026, 11, 2), kind="bot_button", who=f"t{active.telegram_user_id}"))
    session.commit()
    try:
        due = {user.id: total for user, total in checkin.due_users(session, now)}
        assert due.get(quiet.id) == 15
        assert active.id not in due

        quiet.checkin_sent_at = now - dt.timedelta(days=2)
        session.commit()
        assert quiet.id not in {user.id for user, _ in checkin.due_users(session, now)}
    finally:
        session.execute(delete(SentNotification).where(SentNotification.user_id.in_([quiet.id, active.id])))
        session.execute(delete(ActivityDay).where(ActivityDay.who == f"t{active.telegram_user_id}"))
        session.commit()
