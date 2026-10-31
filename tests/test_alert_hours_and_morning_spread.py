"""2026-10-31 (owner): alert hours and days per person, matches held outside them, and morning cards spaced out."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

import notifier  # noqa: E402

from todira_common import alert_hours  # noqa: E402


def _at(weekday_date: str, hour: int, minute: int = 0) -> dt.datetime:
    """An Israel-time moment as UTC. 2026-11-01 is a Sunday, 2026-11-06 a Friday."""
    local = dt.datetime.fromisoformat(weekday_date).replace(hour=hour, minute=minute, tzinfo=alert_hours.ISRAEL)
    return local.astimezone(dt.timezone.utc)


def _user(**overrides):
    defaults = dict(id=1, telegram_user_id=555, alert_from_hour=None, alert_to_hour=None, alerts_on_weekend=True,
                    is_active=True, notifications_enabled=True, language="he")
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_no_choice_means_always():
    assert alert_hours.in_window(_user(), _at("2026-11-01", 3))
    assert alert_hours.in_window(SimpleNamespace(), _at("2026-11-06", 23))  # a row without the columns at all
    assert alert_hours.hours_pair(_user()) == ("08:30", "23:00")


def test_hours_from_inclusive_to_exclusive():
    user = _user(alert_from_hour=9, alert_to_hour=20)
    assert not alert_hours.in_window(user, _at("2026-11-01", 8, 59))
    assert alert_hours.in_window(user, _at("2026-11-01", 9))
    assert alert_hours.in_window(user, _at("2026-11-01", 19, 59))
    assert not alert_hours.in_window(user, _at("2026-11-01", 20))
    assert alert_hours.hours_pair(user) == ("09:00", "20:00")


def test_no_weekend_means_no_friday_and_saturday():
    user = _user(alerts_on_weekend=False)
    assert not alert_hours.in_window(user, _at("2026-11-06", 12))  # Friday
    assert not alert_hours.in_window(user, _at("2026-11-07", 12))  # Saturday
    assert alert_hours.in_window(user, _at("2026-11-08", 12))  # Sunday


def test_morning_is_before_ten_israel_time():
    assert alert_hours.is_morning(_at("2026-11-01", 9, 30))
    assert not alert_hours.is_morning(_at("2026-11-01", 10))


def test_a_match_outside_the_hours_is_held_not_sent():
    listing = SimpleNamespace(id=10, price=5000, description=None)
    user = _user(alert_from_hour=18, alert_to_hour=22)
    session = SimpleNamespace(get=lambda model, pk: user)
    with (
        patch.object(notifier, "_candidate_filters", return_value=[SimpleNamespace(user_id=1)]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "_hidden_by", return_value=False),
        patch.object(notifier, "_hold") as hold,
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)) as send,
    ):
        asyncio.run(notifier._notify_new_matches(SimpleNamespace(), session, listing, now=_at("2026-11-01", 10)))
    send.assert_not_called()
    hold.assert_called_once_with(session, 1, 10)


def test_a_morning_run_queues_instead_of_sending():
    listing = SimpleNamespace(id=10, price=5000, description=None)
    user = _user()
    queue = []
    with (
        patch.object(notifier, "_candidate_filters", return_value=[SimpleNamespace(user_id=1)]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "_hidden_by", return_value=False),
        patch.object(notifier, "_complete_card_fields", AsyncMock()),
        patch.object(notifier, "_below_area_pct", return_value=None),
        patch.object(notifier, "format_caption", return_value="caption"),
        patch.object(notifier, "_has_access_for", return_value=True),
        patch.object(notifier, "_access_state_for", return_value="full"),
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)) as send,
    ):
        matched, sent, _ = asyncio.run(
            notifier._notify_new_matches(SimpleNamespace(), SimpleNamespace(get=lambda m, pk: user), listing, queue=queue)
        )
    send.assert_not_called()
    assert (matched, sent) == (1, 0)
    assert [(job.user.id, job.listing.id) for job in queue] == [(1, 10)]


def _spread(jobs):
    """Runs _send_spread on a fake clock; returns (seconds since start, user id, listing id) per card sent."""
    clock = {"t": 0.0}
    sent = []

    async def fake_sleep(seconds):
        clock["t"] += max(seconds, 0)

    async def fake_send(bot, chat_id, listing, caption, lang):
        sent.append((round(clock["t"], 1), chat_id, listing.id))
        return True

    session = SimpleNamespace(add=lambda row: None, commit=lambda: None)
    with (
        patch.object(notifier.asyncio, "sleep", fake_sleep),
        patch.object(notifier, "send_listing_card", fake_send),
        patch.object(notifier, "_already_notified", return_value=False),
    ):
        count = asyncio.run(notifier._send_spread(SimpleNamespace(), session, jobs, clock=lambda: clock["t"]))
    assert count == len(sent)
    return sent


def _job(user, listing_id):
    return notifier._Send(user=user, listing=SimpleNamespace(id=listing_id), caption="c", lang="he")


def test_one_persons_morning_cards_are_spaced_out():
    alice = _user(id=1, telegram_user_id=111)
    sent = _spread([_job(alice, n) for n in range(4)])
    times = [t for t, _, _ in sent]
    assert [listing for _, _, listing in sent] == [0, 1, 2, 3]
    assert all(b - a >= notifier.MORNING_GAP_SECONDS for a, b in zip(times, times[1:]))


def test_other_people_are_sent_in_the_gaps():
    alice, bob = _user(id=1, telegram_user_id=111), _user(id=2, telegram_user_id=222)
    sent = _spread([_job(alice, 1), _job(alice, 2), _job(bob, 3)])
    assert [chat for _, chat, _ in sent] == [111, 222, 111]
    assert sent[1][0] < notifier.MORNING_GAP_SECONDS  # bob does not wait for alice's gap


def test_a_long_list_still_ends_within_the_limit():
    alice = _user(id=1, telegram_user_id=111)
    sent = _spread([_job(alice, n) for n in range(60)])
    assert len(sent) == 60
    assert sent[-1][0] <= notifier.MORNING_SPREAD_MAX_SECONDS + 60 * notifier.SEND_DELAY_SECONDS


def test_a_card_already_sent_by_a_price_change_is_not_sent_again():
    alice = _user(id=1, telegram_user_id=111)
    session = SimpleNamespace(add=lambda row: None, commit=lambda: None)
    with (
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)) as send,
        patch.object(notifier, "_already_notified", return_value=True),
    ):
        assert asyncio.run(notifier._send_spread(SimpleNamespace(), session, [_job(alice, 1)])) == 0
    send.assert_not_called()
