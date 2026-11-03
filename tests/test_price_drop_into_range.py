"""2026-11-04 (owner): a flat whose price dropped under someone's max price, so it now matches a search it did not match
before, was already sent to them, but as a plain new card. It now says "dropped to your price (was X)"
(scraper/notifier.py _into_range_kwargs, todira_common/cards.py _price_change_header)."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

import notifier  # noqa: E402
from todira_common.cards import _price_change_header  # noqa: E402

_NOW = dt.datetime.now(dt.timezone.utc)


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(notifier, "_had_card_today", lambda *a, **k: False)
    monkeypatch.setattr(notifier, "_release_held", AsyncMock(return_value=0))
    monkeypatch.setattr(notifier.alert_hours, "is_morning", lambda now=None: False)
    monkeypatch.setattr(notifier.alert_hours, "in_window", lambda user, now=None: True)
    monkeypatch.setattr(notifier, "SEND_DELAY_SECONDS", 0, raising=False)


class _FakeBot:
    def __init__(self, token):
        pass

    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, *exc):
        return False


def _by_max_price(filter_row, listing):
    return SimpleNamespace(matched=listing.price is not None and listing.price <= filter_row.price_max)


def _user():
    return SimpleNamespace(id=1, telegram_user_id=555, free_access_granted=False, trial_ends_at=_NOW + dt.timedelta(days=3),
                           paid_until=None, is_active=True, notifications_enabled=True, language="he")


def _run(old_price, *, price_max=5000):
    """One price-change event for a flat now at 4,800: what format_caption is asked for, and how many cards went out."""
    listing = SimpleNamespace(id=10, price=4800, description=None, duplicate_of_id=None)
    filter_row = SimpleNamespace(user_id=1, price_max=price_max)
    user = _user()
    session = SimpleNamespace(get=lambda model, pk: user, add=lambda obj: None, commit=lambda: None,
                              scalars=lambda *a, **k: [])
    sends = AsyncMock(return_value=True)
    with (
        patch.object(notifier, "_candidate_filters", return_value=[filter_row]),
        patch.object(notifier, "evaluate", side_effect=_by_max_price),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "_hidden_by", return_value=False),
        patch.object(notifier, "_complete_card_fields", AsyncMock()),
        patch.object(notifier, "_below_area_pct", return_value=None),
        patch.object(notifier, "_notify_price_change", AsyncMock(return_value=0)),
        patch.object(notifier, "format_caption", return_value="caption") as mock_format,
        patch.object(notifier, "send_listing_card", sends),
        patch.object(notifier, "Bot", _FakeBot),
    ):
        summary = asyncio.run(notifier.run_notifications(session, [], [(listing, old_price)]))
    return mock_format.call_args.kwargs, summary


def test_a_drop_under_the_max_price_is_sent_with_the_dropped_to_your_price_header():
    kwargs, summary = _run(old_price=5600)
    assert summary["notifications_sent"] == 1
    assert kwargs["price_change_from"] == 5600
    assert kwargs["price_into_range"] is True


def test_a_flat_that_already_matched_at_the_old_price_stays_a_plain_new_card():
    kwargs, summary = _run(old_price=4950)
    assert summary["notifications_sent"] == 1
    assert "price_change_from" not in kwargs and "price_into_range" not in kwargs


def test_a_brand_new_flat_has_no_price_header():
    assert notifier._into_range_kwargs(SimpleNamespace(price_max=5000), SimpleNamespace(price=4800), None) == {}


def test_the_header_reads_dropped_to_your_price_with_the_old_price():
    bold = lambda s: f"<b>{s}</b>"  # noqa: E731
    header = _price_change_header(5600, 4800, bold=bold, lang="he", into_range=True)
    assert header == "📉 <b>ירד למחיר שלך!</b> (היה 5,600₪)\n\n"
    # the plain re-notification header for someone who already had the card is unchanged
    assert "ירידת מחיר" in _price_change_header(5600, 4800, bold=bold, lang="he")
    for lang in ("en", "ru", "fr", "ar", "es", "pt", "hi", "fil", "th", "zh"):
        assert "card.price_into_range" not in _price_change_header(5600, 4800, bold=bold, lang=lang, into_range=True)
