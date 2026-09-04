"""Tests for scraper/notifier.py's 2026-09-05 access gating — the proactive "new match" push
must lock the description/link for a lite/expired user exactly like the bot's own on-demand
handlers (dorin_common/cards.py's format_caption), not just show everything to everyone.
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
        trial_ends_at=_NOW - dt.timedelta(days=1),
        paid_until=None,
        is_active=True,
        notifications_enabled=True,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_has_access_for_expired_user_is_false():
    assert notifier._has_access_for(_user()) is False


def test_has_access_for_user_within_trial_is_true():
    assert notifier._has_access_for(_user(trial_ends_at=_NOW + dt.timedelta(days=1))) is True


def test_has_access_for_owner_is_true_even_if_expired():
    with patch.object(notifier, "OWNER_TELEGRAM_USER_ID", "555"):
        assert notifier._has_access_for(_user(telegram_user_id=555)) is True


def test_notify_new_matches_passes_has_access_false_for_an_expired_user():
    listing = SimpleNamespace(id=10, price=5000, description=None)
    filter_row = SimpleNamespace(user_id=1)
    user = _user()
    session = SimpleNamespace(get=lambda model, pk: user, add=lambda obj: None, commit=lambda: None)
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "_candidate_filters", return_value=[filter_row]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "format_caption") as mock_format,
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)),
    ):
        mock_format.return_value = "caption"
        asyncio.run(notifier._notify_new_matches(bot, session, listing))

    mock_format.assert_called_once()
    _, kwargs = mock_format.call_args
    assert kwargs["has_access"] is False
    assert kwargs["upgrade_url"] == f"{notifier.WEBSITE_URL}/upgrade?uid=555"


def test_notify_new_matches_passes_has_access_true_for_a_trial_user():
    listing = SimpleNamespace(id=10, price=5000, description=None)
    filter_row = SimpleNamespace(user_id=1)
    user = _user(trial_ends_at=_NOW + dt.timedelta(days=2))
    session = SimpleNamespace(get=lambda model, pk: user, add=lambda obj: None, commit=lambda: None)
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "_candidate_filters", return_value=[filter_row]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "format_caption") as mock_format,
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)),
    ):
        mock_format.return_value = "caption"
        asyncio.run(notifier._notify_new_matches(bot, session, listing))

    assert mock_format.call_args.kwargs["has_access"] is True


# --- _maybe_fetch_description (2026-09-05, Bright Data on-demand enrichment) — answers the
# owner's own sequencing question: fetch only after matching is done, and only when at least one
# recipient about to be notified is a paying user.


def test_maybe_fetch_description_skips_when_not_configured():
    listing = SimpleNamespace(description=None, url="https://yad2.co.il/item/1")
    session = SimpleNamespace(commit=lambda: None)
    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: False),
        patch.object(notifier.bright_data_client, "fetch_listing_description") as mock_fetch,
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, [_user(trial_ends_at=_NOW + dt.timedelta(days=1))]))
    mock_fetch.assert_not_called()


def test_maybe_fetch_description_skips_when_already_cached():
    listing = SimpleNamespace(description="כבר יש תיאור", url="https://yad2.co.il/item/1")
    session = SimpleNamespace(commit=lambda: None)
    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: True),
        patch.object(notifier.bright_data_client, "fetch_listing_description") as mock_fetch,
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, [_user(trial_ends_at=_NOW + dt.timedelta(days=1))]))
    mock_fetch.assert_not_called()


def test_maybe_fetch_description_skips_when_no_recipient_is_paying():
    listing = SimpleNamespace(description=None, url="https://yad2.co.il/item/1")
    session = SimpleNamespace(commit=lambda: None)
    free_users = [_user(), _user(id=2, telegram_user_id=556)]  # both expired trial, no payment
    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: True),
        patch.object(notifier.bright_data_client, "fetch_listing_description") as mock_fetch,
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, free_users))
    mock_fetch.assert_not_called()


def test_maybe_fetch_description_fetches_and_caches_when_a_recipient_is_paying():
    listing = SimpleNamespace(description=None, url="https://yad2.co.il/item/1")
    committed = []
    session = SimpleNamespace(commit=lambda: committed.append(True))
    recipients = [_user(), _user(id=2, telegram_user_id=556, trial_ends_at=_NOW + dt.timedelta(days=1))]

    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: True),
        patch.object(
            notifier.bright_data_client, "fetch_listing_description", lambda url: "תיאור אמיתי"
        ),
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, recipients))

    assert listing.description == "תיאור אמיתי"
    assert committed == [True]


def test_maybe_fetch_description_does_not_cache_on_fetch_failure():
    listing = SimpleNamespace(description=None, url="https://yad2.co.il/item/1")
    committed = []
    session = SimpleNamespace(commit=lambda: committed.append(True))
    recipients = [_user(trial_ends_at=_NOW + dt.timedelta(days=1))]

    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: True),
        patch.object(notifier.bright_data_client, "fetch_listing_description", lambda url: None),
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, recipients))

    assert listing.description is None
    assert committed == []


def test_notify_price_change_also_passes_has_access():
    listing = SimpleNamespace(id=10, price=4000, description=None)
    filter_row = SimpleNamespace(user_id=1)
    user = _user()
    session = SimpleNamespace(
        scalars=lambda stmt: [1],
        get=lambda model, pk: user,
        scalar=lambda stmt: filter_row,
        add=lambda obj: None,
        commit=lambda: None,
    )
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "format_caption") as mock_format,
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)),
    ):
        mock_format.return_value = "caption"
        asyncio.run(notifier._notify_price_change(bot, session, listing, old_price=5000))

    kwargs = mock_format.call_args.kwargs
    assert kwargs["has_access"] is False
    assert kwargs["price_change_from"] == 5000
