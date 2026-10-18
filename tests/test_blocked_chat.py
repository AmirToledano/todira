"""2026-10-18: a chat that blocked the bot failed on every scraper run and was offered the same listings again each
time. send_listing_card now returns cards.BLOCKED for it (falsy) and the notifier pauses that user."""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from telegram.error import Forbidden, TelegramError

from todira_common import cards


def _listing():
    return SimpleNamespace(id=7, image_urls=[])


def _send(side_effect):
    bot = SimpleNamespace(send_photo=AsyncMock(side_effect=side_effect))
    with patch.object(cards, "_dachshund_photo_path", return_value="x.jpg"):
        return asyncio.run(cards.send_listing_card(bot, 5, _listing(), "caption", "he"))


def test_a_blocked_chat_is_reported_as_blocked_and_still_counts_as_not_sent():
    result = _send(Forbidden("Forbidden: bot was blocked by the user"))
    assert result is cards.BLOCKED
    assert not result


def test_other_failures_stay_a_plain_false():
    assert _send(TelegramError("boom")) is False


def test_the_notifier_pauses_a_user_whose_chat_is_blocked():
    import notifier

    user = SimpleNamespace(is_active=True)
    session = SimpleNamespace(commit=lambda: None)
    notifier._pause_blocked_user(session, user)
    assert user.is_active is False
