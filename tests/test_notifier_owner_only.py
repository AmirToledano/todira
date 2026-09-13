"""Tests for the 2026-09-13 only_telegram_user_id restriction (scraper/notifier.py) — added
alongside main.py's NOTIFICATIONS_SUSPENDED resume-catchup mechanism. Explicit owner request: keep
real Telegram pushes landing on their OWN phone during a scraper catch-up (to keep verifying the
pipeline actually works end to end) while every other real user is silently skipped until the
restriction is lifted on a later run. Same test setup/style as test_notifier_access_gating.py.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

import notifier

_NOW = dt.datetime.now(dt.timezone.utc)


def _user(**overrides):
    defaults = dict(
        id=1,
        telegram_user_id=555,
        free_access_granted=False,
        trial_ends_at=_NOW + dt.timedelta(days=1),
        paid_until=None,
        is_active=True,
        notifications_enabled=True,
        whatsapp_phone_number=None,
        whatsapp_notifications_opted_in=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_notify_new_matches_skips_a_non_owner_user_when_restricted():
    listing = SimpleNamespace(id=10, price=5000, description=None)
    filter_row = SimpleNamespace(user_id=1)
    user = _user(telegram_user_id=555)
    session = SimpleNamespace(get=lambda model, pk: user, add=lambda obj: None, commit=lambda: None)
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "_candidate_filters", return_value=[filter_row]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)) as mock_send,
    ):
        matched, sent = asyncio.run(
            notifier._notify_new_matches(bot, session, listing, only_telegram_user_id="999")
        )

    mock_send.assert_not_called()
    assert matched == 1  # still counted as a real match, just not notified
    assert sent == 0


def test_notify_new_matches_still_notifies_the_matching_owner_id():
    listing = SimpleNamespace(id=10, price=5000, description=None)
    filter_row = SimpleNamespace(user_id=1)
    user = _user(telegram_user_id=555)
    session = SimpleNamespace(get=lambda model, pk: user, add=lambda obj: None, commit=lambda: None)
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "_candidate_filters", return_value=[filter_row]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "format_caption", return_value="caption"),
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)) as mock_send,
    ):
        matched, sent = asyncio.run(
            notifier._notify_new_matches(bot, session, listing, only_telegram_user_id="555")
        )

    mock_send.assert_called_once()
    assert sent == 1


def test_notify_price_change_skips_a_non_owner_user_when_restricted():
    listing = SimpleNamespace(id=10, price=4000, description=None)
    user = _user(telegram_user_id=555)
    filter_row = SimpleNamespace(user_id=1)
    session = SimpleNamespace(
        scalars=lambda stmt: [1],
        get=lambda model, pk: user,
        scalar=lambda stmt: filter_row,
        add=lambda obj: None,
        commit=lambda: None,
    )
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)) as mock_send,
    ):
        sent = asyncio.run(
            notifier._notify_price_change(bot, session, listing, 5000, only_telegram_user_id="999")
        )

    mock_send.assert_not_called()
    assert sent == 0


def test_run_notifications_threads_only_telegram_user_id_through(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    listing = SimpleNamespace(id=10, price=5000)

    calls = []

    async def _fake_notify_new_matches(bot, session, listing, *, only_telegram_user_id=None):
        calls.append(("new", only_telegram_user_id))
        return 0, 0

    class _FakeBot:
        def __init__(self, token):
            pass

        async def __aenter__(self):
            return SimpleNamespace()

        async def __aexit__(self, *exc):
            return False

    with (
        patch.object(notifier, "_notify_new_matches", _fake_notify_new_matches),
        patch.object(notifier, "Bot", _FakeBot),
    ):
        asyncio.run(
            notifier.run_notifications(
                SimpleNamespace(), [listing], [], only_telegram_user_id="555"
            )
        )

    assert calls == [("new", "555")]
