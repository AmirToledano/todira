"""Unit tests for dorin_common/cards.py — Telegram/WhatsApp caption rendering for a Listing.

Pure string-formatting logic (no I/O, no DB) — SimpleNamespace stands in for a real Listing row,
same approach test_matching.py already uses, since format_caption/format_caption_whatsapp only
ever read attributes off whatever's passed in.
"""
from __future__ import annotations

from types import SimpleNamespace

from dorin_common.cards import format_caption, format_caption_whatsapp


def make_listing(**overrides):
    defaults = dict(
        id=1,
        url="https://www.yad2.co.il/item/abc123",
        source="yad2",
        rooms=4,
        floor=2,
        floor_total=3,
        size_sqm=160,
        price=16000,
        move_in_date=None,
        has_parking=None,
        has_elevator=None,
        has_balcony=None,
        pets_allowed=None,
        is_renovated=None,
        is_roommate_friendly=None,
        safe_room_type=None,
        furniture=None,
        neighborhood="ניות",
        city="ירושלים",
        description=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_basic_caption_includes_core_fields():
    caption = format_caption(make_listing())
    assert "4 חדרים" in caption
    assert "160 מ" in caption
    assert "16,000 ₪" in caption
    assert "ניות, ירושלים" in caption
    assert "yad2" in caption


def test_no_features_line_when_nothing_is_known():
    caption = format_caption(make_listing())
    assert "פיצ'רים" not in caption


def test_features_line_lists_known_true_amenities():
    listing = make_listing(has_parking=True, has_elevator=True, is_renovated=True)
    caption = format_caption(listing)
    assert "🔑 פיצ'רים:" in caption
    assert "חניה" in caption
    assert "מעלית" in caption
    assert "משופצת" in caption


def test_features_line_excludes_false_and_unknown_amenities():
    listing = make_listing(has_parking=True, has_elevator=False, has_balcony=None)
    caption = format_caption(listing)
    assert "חניה" in caption
    assert "מעלית" not in caption
    assert "מרפסת" not in caption


def test_features_line_includes_safe_room_and_furniture():
    listing = make_listing(safe_room_type="safe_room", furniture="furnished")
    caption = format_caption(listing)
    assert 'ממ"ד' in caption
    assert "מרוהטת" in caption


def test_features_line_is_italicized_in_telegram_html():
    listing = make_listing(has_parking=True)
    caption = format_caption(listing)
    assert "<i>🔑 פיצ'רים:" in caption
    assert "</i>" in caption


def test_price_drop_header_prepended():
    caption = format_caption(make_listing(), price_drop_from=18000)
    assert "ירידת מחיר" in caption
    assert "18,000" in caption


def test_whatsapp_caption_uses_markdown_not_html():
    listing = make_listing(has_parking=True)
    caption = format_caption_whatsapp(listing)
    assert "<b>" not in caption
    assert "<i>" not in caption
    assert "*4 חדרים*" in caption
    assert "_🔑 פיצ'רים: חניה_" in caption


def test_whatsapp_caption_includes_the_raw_url_not_an_html_link():
    caption = format_caption_whatsapp(make_listing())
    assert "https://www.yad2.co.il/item/abc123" in caption
    assert "<a href" not in caption


# --- send_listing_card (2026-09-02) — real Yad2 photos, added once the scraper started actually
# capturing them (see scraper/normalize.py's enrich_from_detail). Telegram's sendMediaGroup can't
# carry an inline keyboard, so 2+ photos need a follow-up message for the ❤️/🙈/🎉 buttons - the
# one quirk worth locking down with a test.
import asyncio  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

from dorin_common.cards import send_listing_card  # noqa: E402


def _make_bot():
    return SimpleNamespace(
        send_message=AsyncMock(),
        send_photo=AsyncMock(),
        send_media_group=AsyncMock(),
    )


def test_send_listing_card_no_images_sends_plain_text_message():
    bot = _make_bot()
    listing = make_listing(image_urls=[])
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    bot.send_message.assert_awaited_once()
    bot.send_photo.assert_not_awaited()
    bot.send_media_group.assert_not_awaited()
    assert bot.send_message.await_args.kwargs["reply_markup"] is not None


def test_send_listing_card_one_image_uses_send_photo_with_keyboard():
    bot = _make_bot()
    listing = make_listing(image_urls=["https://img.yad2.co.il/a.jpg"])
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    bot.send_photo.assert_awaited_once()
    assert bot.send_photo.await_args.kwargs["reply_markup"] is not None
    bot.send_media_group.assert_not_awaited()


def test_send_listing_card_multiple_images_uses_media_group_plus_keyboard_followup():
    bot = _make_bot()
    listing = make_listing(
        image_urls=["https://img.yad2.co.il/a.jpg", "https://img.yad2.co.il/b.jpg"]
    )
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    bot.send_media_group.assert_awaited_once()
    media = bot.send_media_group.await_args.kwargs["media"]
    assert len(media) == 2
    assert media[0].caption == "caption"
    # sendMediaGroup itself can't carry an inline keyboard - a follow-up message does
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["reply_markup"] is not None
    bot.send_photo.assert_not_awaited()


def test_send_listing_card_returns_false_on_telegram_error():
    from telegram.error import TelegramError

    bot = _make_bot()
    bot.send_message.side_effect = TelegramError("blocked")
    listing = make_listing(image_urls=[])
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is False


def test_send_listing_card_retries_once_on_flood_control_then_succeeds():
    from telegram.error import RetryAfter

    bot = _make_bot()
    bot.send_message.side_effect = [RetryAfter(retry_after=0), None]
    listing = make_listing(image_urls=[])

    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))

    assert ok is True
    assert bot.send_message.await_count == 2


def test_send_listing_card_gives_up_after_second_flood_control_hit():
    from telegram.error import RetryAfter

    bot = _make_bot()
    bot.send_message.side_effect = [RetryAfter(retry_after=0), RetryAfter(retry_after=0)]
    listing = make_listing(image_urls=[])

    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))

    assert ok is False
    assert bot.send_message.await_count == 2
