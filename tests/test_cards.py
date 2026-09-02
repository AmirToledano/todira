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
        deal_type="rent",
        is_broker_listing=False,
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
        street=None,
        neighborhood="ניות",
        city="ירושלים",
        description=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_basic_caption_includes_core_fields():
    # Real field order/layout a user asked for directly (2026-09-02): location before price,
    # every field its own labeled line, ש"ח (not ₪) as the currency.
    caption = format_caption(make_listing())
    assert "🛏️ חדרים: 4" in caption
    assert '📐 שטח: 160 מ"ר' in caption
    assert '💰 מחיר: 16,000 ש"ח' in caption
    assert "📍 מיקום: ירושלים, ניות" in caption
    assert "yad2" in caption
    # location must come before price in the actual rendered order, not just be present somewhere
    assert caption.index("📍 מיקום") < caption.index("💰 מחיר")


def test_deal_type_and_broker_tag_line():
    caption = format_caption(make_listing(deal_type="rent", is_broker_listing=False))
    assert "🏠 שכירות" in caption
    assert "תיווך" not in caption

    caption = format_caption(make_listing(deal_type="sale", is_broker_listing=True))
    assert "🏠 מכירה" in caption
    assert "תיווך" in caption


def test_location_includes_street_when_known():
    caption = format_caption(make_listing(street="דיזנגוף"))
    assert "📍 מיקום: ירושלים, ניות, דיזנגוף" in caption


def test_floor_line_includes_total_when_known():
    caption = format_caption(make_listing(floor=4, floor_total=6))
    assert "🏢 קומה: 4 מתוך 6" in caption


def test_no_features_line_when_nothing_is_known():
    caption = format_caption(make_listing())
    assert "פיצ'רים" not in caption


def test_features_line_lists_known_true_amenities_pipe_separated():
    listing = make_listing(has_parking=True, has_elevator=True, is_renovated=True)
    caption = format_caption(listing)
    assert "🔑 פיצ'רים:" in caption
    assert "חניה" in caption
    assert "מעלית" in caption
    assert "משופצת" in caption
    assert "חניה | מעלית | משופצת" in caption


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
    caption = format_caption(make_listing(price=16000), price_change_from=18000)
    assert caption.startswith("📉")
    assert "ירידת מחיר" in caption
    assert "18,000" in caption


def test_price_increase_header_prepended():
    caption = format_caption(make_listing(price=18000), price_change_from=16000)
    assert caption.startswith("📈")
    assert "עליית מחיר" in caption
    assert "16,000" in caption


def test_no_price_change_header_for_a_new_listing():
    # An explicit real request: a brand-new listing must NOT get any price-change banner.
    caption = format_caption(make_listing())
    assert "📉" not in caption
    assert "📈" not in caption
    assert "ירידת מחיר" not in caption
    assert "עליית מחיר" not in caption


def test_no_price_change_header_when_old_and_new_price_are_equal():
    caption = format_caption(make_listing(price=16000), price_change_from=16000)
    assert "ירידת מחיר" not in caption
    assert "עליית מחיר" not in caption


def test_whatsapp_caption_uses_markdown_not_html():
    listing = make_listing(has_parking=True)
    caption = format_caption_whatsapp(listing)
    assert "<b>" not in caption
    assert "<i>" not in caption
    assert "🛏️ חדרים: 4" in caption
    assert "_🔑 פיצ'רים: חניה_" in caption


def test_whatsapp_price_change_header_is_bold_with_asterisks():
    caption = format_caption_whatsapp(make_listing(price=16000), price_change_from=18000)
    assert "*ירידת מחיר!*" in caption


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


def test_send_listing_card_no_images_sends_a_todi_photo():
    # No real photos -> a real photo of Todi (the user's own dachshund) instead of a bare text
    # message (2026-09-02 request) — see dorin_common/cards.py's _dachshund_photo_path.
    bot = _make_bot()
    listing = make_listing(image_urls=[])
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    bot.send_photo.assert_awaited_once()
    bot.send_message.assert_not_awaited()
    bot.send_media_group.assert_not_awaited()
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs["reply_markup"] is not None
    assert "caption" in kwargs["caption"]
    assert "טודי" in kwargs["caption"]
    assert kwargs["photo"].name.endswith(".jpg")


def test_send_listing_card_one_image_uses_send_photo_with_keyboard():
    bot = _make_bot()
    listing = make_listing(image_urls=["https://img.yad2.co.il/a.jpg"])
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    bot.send_photo.assert_awaited_once()
    assert bot.send_photo.await_args.kwargs["reply_markup"] is not None
    bot.send_media_group.assert_not_awaited()


def test_send_listing_card_multiple_images_still_sends_just_the_first_one():
    # Deliberately NOT a sendMediaGroup gallery (2026-09-02: dropped after a real user report -
    # sendMediaGroup can't carry an inline keyboard, so 2+ photos needed a separate "⬆️ הדירה
    # למעלה" follow-up message just for the buttons, which got confusing once several listings
    # arrived in a burst with delays between them). One send_photo call, first image only, caption
    # and keyboard together - the listing's other photos are still reachable via the caption's own
    # link to the full listing.
    bot = _make_bot()
    listing = make_listing(
        image_urls=["https://img.yad2.co.il/a.jpg", "https://img.yad2.co.il/b.jpg"]
    )
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    bot.send_photo.assert_awaited_once()
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs["photo"] == "https://img.yad2.co.il/a.jpg"
    assert kwargs["caption"] == "caption"
    assert kwargs["reply_markup"] is not None
    bot.send_media_group.assert_not_awaited()
    bot.send_message.assert_not_awaited()


def test_send_listing_card_returns_false_on_telegram_error():
    from telegram.error import TelegramError

    bot = _make_bot()
    bot.send_photo.side_effect = TelegramError("blocked")
    listing = make_listing(image_urls=[])
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is False


def test_send_listing_card_retries_once_on_flood_control_then_succeeds():
    from telegram.error import RetryAfter

    bot = _make_bot()
    bot.send_photo.side_effect = [RetryAfter(retry_after=0), None]
    listing = make_listing(image_urls=[])

    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))

    assert ok is True
    assert bot.send_photo.await_count == 2


def test_dachshund_photo_pick_is_deterministic_per_listing_id():
    from dorin_common.cards import _dachshund_photo_path

    assert _dachshund_photo_path(1) == _dachshund_photo_path(1)
    # different ids can land on different photos, but always a real file on disk
    for listing_id in range(25):
        path = _dachshund_photo_path(listing_id)
        assert path.exists(), f"missing todi asset: {path}"


def test_send_listing_card_no_images_caption_stays_within_telegram_limit():
    from dorin_common.cards import CAPTION_LIMIT

    bot = _make_bot()
    listing = make_listing(image_urls=[])
    long_caption = "א" * CAPTION_LIMIT  # already at the limit before the dachshund suffix
    asyncio.run(send_listing_card(bot, 555, listing, long_caption))
    assert len(bot.send_photo.await_args.kwargs["caption"]) <= CAPTION_LIMIT


def test_send_listing_card_gives_up_after_second_flood_control_hit():
    from telegram.error import RetryAfter

    bot = _make_bot()
    bot.send_photo.side_effect = [RetryAfter(retry_after=0), RetryAfter(retry_after=0)]
    listing = make_listing(image_urls=[])

    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))

    assert ok is False
    assert bot.send_photo.await_count == 2
