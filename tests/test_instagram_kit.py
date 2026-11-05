"""2026-11-05: the weekly Instagram carousel for the owner (scraper/instagram_kit.py)."""
from __future__ import annotations

import datetime as dt
import io
import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from PIL import Image  # noqa: E402

import instagram_kit  # noqa: E402

from todira_common import alert_hours  # noqa: E402

ROWS = [("תל אביב", 7800), ("ירושלים", 6200), ("באר שבע", 3600), ("חיפה", 4300)]


def _israel(day: str, hour: int) -> dt.datetime:
    return dt.datetime.fromisoformat(f"{day}T{hour:02d}:10").replace(tzinfo=alert_hours.ISRAEL).astimezone(dt.timezone.utc)


def test_due_once_on_thursday_morning():
    assert instagram_kit.due(None, _israel("2026-11-05", 9)) == "2026-45"  # Thursday
    assert instagram_kit.due("2026-45", _israel("2026-11-05", 10)) is None
    assert instagram_kit.due(None, _israel("2026-11-05", 12)) is None
    assert instagram_kit.due(None, _israel("2026-11-06", 9)) is None  # Friday


def test_four_portrait_slides_with_and_without_raqm():
    for raqm in (True, False):
        pngs = instagram_kit.slides(ROWS, _israel("2026-11-05", 9), raqm=raqm if raqm is False else None)
        assert len(pngs) == 4
        for png in pngs:
            assert Image.open(io.BytesIO(png)).size == (1080, 1350)


def test_caption_names_cheapest_and_dearest_and_no_dashes():
    text = instagram_kit.caption(ROWS)
    assert "באר שבע, ₪3,600" in text
    assert "תל אביב, ₪7,800" in text
    assert "הקישור בביו" in text
    assert "—" not in text and "–" not in text


def test_not_sent_with_too_few_cities(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setattr(instagram_kit.app_flags, "get_flag", lambda session, key: None)
    import channel

    monkeypatch.setattr(channel, "weekly_prices", lambda session, now: ROWS[:2])
    sent = []
    monkeypatch.setattr(instagram_kit, "_send", lambda *a: sent.append(a) or True)
    assert instagram_kit.run_instagram_kit(object(), _israel("2026-11-05", 9)) == {}
    assert not sent
