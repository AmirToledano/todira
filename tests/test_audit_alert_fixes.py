"""2026-11-02 audit fixes in the alert path (scraper/notifier.py, scraper/checkin.py, todira_common/area_price.py)."""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

import notifier  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from todira_common import area_price  # noqa: E402


class _Bot:
    def __init__(self, token):
        pass

    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, *exc):
        return False


def test_a_row_the_site_wrote_first_does_not_end_the_run():
    class _Session:
        def __init__(self):
            self.rolled_back = False

        def add(self, row):
            pass

        def commit(self):
            raise IntegrityError("insert", {}, Exception("duplicate"))

        def rollback(self):
            self.rolled_back = True

    session = _Session()
    job = notifier._Send(user=SimpleNamespace(id=1, is_active=True, telegram_user_id=5), listing=SimpleNamespace(id=9),
                         caption="c", lang="he")
    with patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)), \
         patch.object(notifier, "SEND_DELAY_SECONDS", 0):
        assert asyncio.run(notifier._send_one(SimpleNamespace(), session, job)) is True
    assert session.rolled_back


def test_only_the_main_run_releases_held_alerts(monkeypatch):
    release = AsyncMock(return_value=0)
    monkeypatch.setattr(notifier, "_release_held", release)
    monkeypatch.setattr(notifier.alert_hours, "is_morning", lambda now=None: False)
    with patch.object(notifier, "Bot", _Bot):
        asyncio.run(notifier.run_notifications(SimpleNamespace(), [], [], spread_morning=False))
        release.assert_not_called()
        asyncio.run(notifier.run_notifications(SimpleNamespace(), [], [], spread_morning=True))
        release.assert_called_once()


def test_no_area_price_tag_for_a_room_in_a_shared_flat_or_an_ad_without_rooms(monkeypatch):
    monkeypatch.setattr(area_price, "area_price_comparison",
                        lambda session, listing: {"solid": True, "diff_pct": -57})
    whole_flat = SimpleNamespace(rooms=3, description="דירת 3 חדרים")
    assert area_price.below_area_pct(None, whole_flat) == 57
    assert area_price.below_area_pct(None, SimpleNamespace(rooms=None, description="דירה")) is None
    room = SimpleNamespace(rooms=1, description="חדר בדירת שותפים בפלורנטין")
    assert area_price.below_area_pct(None, room) is None
