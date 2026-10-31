"""2026-10-31: posts to the public Telegram channel (scraper/channel.py)."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import channel  # noqa: E402

from todira_common import alert_hours  # noqa: E402


def _israel(day: str, hour: int) -> dt.datetime:
    local = dt.datetime.fromisoformat(f"{day}T{hour:02d}:10").replace(tzinfo=alert_hours.ISRAEL)
    return local.astimezone(dt.timezone.utc)


def test_the_welcome_goes_once_the_morning_post_once_a_day_and_the_prices_on_friday():
    friday_morning = _israel("2026-11-06", 9)
    assert channel.due_posts({}, _israel("2026-11-01", 20)) == ["intro"]  # the welcome does not wait for the morning
    assert channel.due_posts({"intro": "2026-10-31"}, _israel("2026-11-01", 20)) == []
    assert channel.due_posts({"intro": "x"}, _israel("2026-11-01", 9)) == ["daily"]
    assert channel.due_posts({"intro": "x", "daily": "2026-11-01"}, _israel("2026-11-01", 11)) == []
    assert channel.due_posts({"intro": "x"}, friday_morning) == ["daily", "weekly"]
    assert channel.due_posts({"intro": "x", "daily": "2026-11-06", "weekly": "2026-11-06"}, friday_morning) == []
    assert channel.due_posts({"intro": "x"}, _israel("2026-11-01", 12)) == []


def _listing(listing_id, city="חיפה", rooms=3, price=4000, *, broker=False, hood="הדר", size=70, photos=("p",)):
    return SimpleNamespace(
        id=listing_id, city=city, rooms=Decimal(str(rooms)), price=price, neighborhood=hood, size_sqm=size,
        is_broker_listing=broker, image_urls=list(photos),
    )


class _Session:
    def __init__(self, peer_rows, new_listings=()):
        self.peer_rows, self.new_listings = peer_rows, list(new_listings)

    def execute(self, query):
        return iter(self.peer_rows)

    def scalars(self, query):
        return iter(self.new_listings)


def test_picks_are_cheaper_than_their_peers_private_owners_first():
    peers = [("חיפה", Decimal("3"), 5000)] * 10 + [("עכו", Decimal("3"), 3000)] * 9
    new = [
        _listing(1, price=4800),  # 4% below: not enough
        _listing(2, price=4000, broker=True),  # 20% below, a broker
        _listing(3, price=4500),  # 10% below, private
        _listing(4, price=2000),  # 60% below: more likely a wrong price
        _listing(5, city="עכו", price=2000),  # only 9 peers
        _listing(6, rooms=4, price=1000),  # no 4-room peers at all
    ]
    picks = channel.pick_flats(_Session(peers, new), dt.datetime(2026, 11, 1, 7, tzinfo=dt.timezone.utc))
    assert [(listing.id, round(below, 2)) for listing, below in picks] == [(3, 0.1), (2, 0.2)]


def test_the_caption_links_each_flat_to_its_page_and_never_names_the_bot():
    picks = [(_listing(7, hood="שאר העיר", size=None), 0.123), (_listing(8, city="תל אביב יפו", rooms=1), 0.2)]
    caption = channel.daily_caption(picks)
    assert '1. <a href="https://todira.app/s/7-' in caption and ">חיפה</a>" in caption  # no made-up neighbourhood
    assert "3 חדרים, ₪4,000 לחודש. 12% פחות מדירות דומות בעיר." in caption
    assert "חדר אחד, 70 מ\"ר, ₪4,000 לחודש. 20% פחות" in caption
    assert 'href="https://t.me/AmirDirotBot?start=channel"' in caption and "@AmirDirotBot" not in caption
    assert "—" not in caption
    long_picks = [(_listing(i, city="מודיעין מכבים רעות", hood="שכונה עם שם ארוך מאוד מאוד"), 0.3) for i in range(5)]
    assert len(channel.daily_caption(long_picks)) <= 1024  # Telegram's caption limit


def test_the_friday_post_lists_the_biggest_cities_with_their_pages():
    rows = [("חיפה", Decimal("3"), 4000)] * 12 + [("חיפה", Decimal("2"), 3000)] * 5 + [("עכו", Decimal("3.5"), 3000)] * 10
    text = channel.weekly_text(_Session(rows), dt.datetime(2026, 11, 6, 7, tzinfo=dt.timezone.utc))
    assert text.index(">חיפה</a>: ₪4,000") < text.index(">עכו</a>: ₪3,000")
    assert 'href="https://todira.app/rent/%D7%97%D7%99%D7%A4%D7%94"' in text
    assert channel.weekly_text(_Session([("חיפה", Decimal("3"), 4000)] * 9), dt.datetime.now(dt.timezone.utc)) is None


def test_the_morning_album_skips_flats_without_a_working_photo_and_keeps_two_a_city():
    picks = [(_listing(i, city="חיפה" if i < 4 else "עכו"), 0.2) for i in range(1, 7)]
    bot = SimpleNamespace(send_media_group=AsyncMock(), send_photo=AsyncMock())
    photos = {1: None, 2: b"two", 3: b"three", 4: b"four", 5: b"five", 6: b"six"}
    with patch.object(channel, "pick_flats", return_value=picks), \
         patch.object(channel, "_first_downloadable_photo_jpeg_bytes", side_effect=lambda urls: photos[urls[0]]):
        for number, (listing, _) in enumerate(picks, 1):
            listing.image_urls = [number]
        assert asyncio.run(channel._post(bot, "daily", None, dt.datetime.now(dt.timezone.utc))) is True
    media = bot.send_media_group.await_args.args[1]
    # 1 has no photo that loads; 6 would be a third flat in עכו
    assert [item.media.input_file_content for item in media] == [b"two", b"three", b"four", b"five"]
    assert media[0].caption.count('<a href="https://todira.app/s/') == 4 and media[1].caption is None


@pytest.mark.skipif(not os.environ.get("TODIRA_TEST_DATABASE_URL"), reason="needs a real Postgres")
def test_the_queries_run_on_postgres():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    with Session(create_engine(os.environ["TODIRA_TEST_DATABASE_URL"])) as session:
        now = dt.datetime.now(dt.timezone.utc)
        assert isinstance(channel.pick_flats(session, now), list)
        channel.weekly_text(session, now)
