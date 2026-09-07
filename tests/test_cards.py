"""Unit tests for dorin_common/cards.py — Telegram/WhatsApp caption rendering for a Listing, plus
send_listing_card's send behavior and _build_collage_sync's photo-compositing (both against a fake
bot / mocked httpx — no real Telegram or network calls).

The format_caption*/make_listing tests are pure string-formatting logic (no I/O, no DB) —
SimpleNamespace stands in for a real Listing row, same approach test_matching.py already uses,
since format_caption/format_caption_whatsapp only ever read attributes off whatever's passed in.
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
    # 2026-09-03 rewrite, matching the reference bot dorin.app 1:1: location before price, every
    # field its own BOLD-labeled line, ₪ (not "ש"ח") as the currency, no source tag anywhere.
    caption = format_caption(make_listing(), has_access=True)
    assert "🛏️ <b>חדרים:</b> 4" in caption
    assert '📐 <b>שטח:</b> 160 מ"ר' in caption
    assert "💰 <b>מחיר:</b> 16,000₪" in caption
    assert "📍<b>ירושלים</b> - ניות" in caption
    assert "🏷️" not in caption  # the old "🏷️ {source}" footer line is gone
    # location must come before price in the actual rendered order, not just be present somewhere
    assert caption.index("📍") < caption.index("💰")


def test_no_prefix_line_for_a_plain_rent_or_sale_listing():
    caption = format_caption(make_listing(deal_type="rent", is_broker_listing=False), has_access=True)
    assert "תיווך" not in caption
    assert "סאבלט" not in caption

    caption = format_caption(make_listing(deal_type="sale", is_broker_listing=False), has_access=True)
    assert "תיווך" not in caption
    assert "סאבלט" not in caption


def test_broker_prefix_line_shown_regardless_of_deal_type():
    caption = format_caption(make_listing(deal_type="sale", is_broker_listing=True), has_access=True)
    assert "🏢<b>תיווך</b>" in caption

    caption = format_caption(make_listing(deal_type="rent", is_broker_listing=True), has_access=True)
    assert "🏢<b>תיווך</b>" in caption


def test_sublet_prefix_line_shown_when_not_broker():
    caption = format_caption(make_listing(deal_type="sublet", is_broker_listing=False), has_access=True)
    assert "🏢<b>סאבלט</b>" in caption
    assert "תיווך" not in caption


def test_broker_prefix_wins_over_sublet_if_somehow_both():
    caption = format_caption(make_listing(deal_type="sublet", is_broker_listing=True), has_access=True)
    assert "🏢<b>תיווך</b>" in caption
    assert "סאבלט" not in caption


def test_location_street_is_a_google_maps_link_on_telegram():
    caption = format_caption(make_listing(street="דיזנגוף 10"), has_access=True)
    assert '📍<b>ירושלים</b> - ניות <a href="https://www.google.com/maps/search/' in caption
    assert ">דיזנגוף 10</a>" in caption
    assert "דיזנגוף+10" in caption or "%D7%93%D7%99%D7%96%D7%A0%D7%92%D7%95%D7%A3" in caption


def test_location_without_street_has_no_maps_link():
    caption = format_caption(make_listing(), has_access=True)
    assert "google.com/maps" not in caption


def test_floor_line_includes_total_when_known():
    caption = format_caption(make_listing(floor=4, floor_total=6), has_access=True)
    assert "🏢 <b>קומה:</b> 4 מתוך 6" in caption


def test_move_in_date_is_day_month_year_not_iso():
    import datetime

    caption = format_caption(make_listing(move_in_date=datetime.date(2026, 9, 21)), has_access=True)
    assert "📅 <b>כניסה:</b> 21.09.2026" in caption
    assert "2026-09-21" not in caption


def test_no_features_line_when_nothing_is_known():
    caption = format_caption(make_listing(), has_access=True)
    assert "פיצ'רים" not in caption


def test_features_line_uses_a_distinct_emoji_per_feature_pipe_separated():
    listing = make_listing(has_parking=True, has_elevator=True, is_renovated=True)
    caption = format_caption(listing, has_access=True)
    assert "🔑 <b>פיצ'רים:</b>" in caption
    assert "🚗חניה | 🛗מעלית | ✨משופצת" in caption


def test_features_line_excludes_false_and_unknown_amenities():
    listing = make_listing(has_parking=True, has_elevator=False, has_balcony=None)
    caption = format_caption(listing, has_access=True)
    assert "🚗חניה" in caption
    assert "🛗מעלית" not in caption
    assert "🌿מרפסת" not in caption


def test_features_line_includes_safe_room_and_furniture_with_their_own_emoji():
    listing = make_listing(safe_room_type="safe_room", furniture="furnished")
    caption = format_caption(listing, has_access=True)
    assert '🛡️ממ"ד' in caption
    assert "🛋️מרוהטת" in caption


def test_features_line_is_not_italicized_anymore():
    listing = make_listing(has_parking=True)
    caption = format_caption(listing, has_access=True)
    assert "<i>" not in caption


def test_description_gets_a_note_emoji_prefix():
    caption = format_caption(make_listing(description="דירה מקסימה"), has_access=True)
    assert "📝 דירה מקסימה" in caption


def test_footer_link_text_and_no_source_tag():
    caption = format_caption(make_listing(), has_access=True)
    assert '<a href="https://www.yad2.co.il/item/abc123">לפרטי הדירה המלאים &gt;&gt;</a>' in caption
    assert "🏷️" not in caption


def test_caption_starts_with_an_invisible_rtl_mark():
    # 2026-09-03: real user report + screenshot - Telegram rendered the caption's alignment
    # starting from the middle/left instead of the right, because nearly every line starts with
    # an emoji (no strong bidi direction of its own). An invisible U+200F forces RTL regardless.
    caption = format_caption(make_listing(), has_access=True)
    assert caption.startswith("‏")


def test_every_body_line_carries_its_own_rtl_mark_not_just_the_first():
    # A second real user report the same day: the block kept drifting further left line by line -
    # a single mark at the very front of the caption only anchors the FIRST line's direction, not
    # every line independently. Every real content line needs its own leading mark.
    caption = format_caption(make_listing(has_parking=True), has_access=True)
    lines = [line for line in caption.split("\n") if line]
    for line in lines:
        assert line.startswith("‏"), f"line missing its own RTL mark: {line!r}"


def test_blank_spacer_line_has_no_stray_rtl_mark():
    caption = format_caption(make_listing(has_parking=True), has_access=True)
    lines = caption.split("\n")
    assert "" in lines  # the spacer before the features line


def test_blank_line_separates_floor_from_features():
    caption = format_caption(make_listing(has_parking=True, floor=4, floor_total=6), has_access=True)
    lines = caption.split("\n")
    floor_index = next(i for i, line in enumerate(lines) if "קומה" in line)
    features_index = next(i for i, line in enumerate(lines) if "פיצ'רים" in line)
    assert features_index == floor_index + 2
    assert lines[floor_index + 1] == ""


def test_price_drop_header_prepended():
    caption = format_caption(make_listing(price=16000), price_change_from=18000, has_access=True)
    assert caption.lstrip("‏").startswith("📉")
    assert "ירידת מחיר" in caption
    assert "18,000" in caption


def test_price_increase_header_prepended():
    caption = format_caption(make_listing(price=18000), price_change_from=16000, has_access=True)
    assert caption.lstrip("‏").startswith("📈")
    assert "עליית מחיר" in caption
    assert "16,000" in caption


def test_no_price_change_header_for_a_new_listing():
    # An explicit real request: a brand-new listing must NOT get any price-change banner.
    caption = format_caption(make_listing(), has_access=True)
    assert "📉" not in caption
    assert "📈" not in caption
    assert "ירידת מחיר" not in caption
    assert "עליית מחיר" not in caption


def test_no_price_change_header_when_old_and_new_price_are_equal():
    caption = format_caption(make_listing(price=16000), price_change_from=16000, has_access=True)
    assert "ירידת מחיר" not in caption
    assert "עליית מחיר" not in caption


def test_whatsapp_caption_uses_markdown_not_html():
    listing = make_listing(has_parking=True)
    caption = format_caption_whatsapp(listing, has_access=True)
    assert "<b>" not in caption
    assert "<i>" not in caption
    assert "🛏️ *חדרים:* 4" in caption
    assert "🔑 *פיצ'רים:* 🚗חניה" in caption
    assert "_" not in caption  # no more italics markdown either


def test_whatsapp_street_stays_plain_text_with_a_separate_maps_line():
    # WhatsApp text messages can't make custom text a link (only raw URLs auto-link), unlike
    # Telegram's HTML <a> tag — same underlying Google Maps URL, just on its own tappable line
    # right after the location line instead of inline.
    caption = format_caption_whatsapp(make_listing(street="דיזנגוף 10"), has_access=True)
    assert "📍*ירושלים* - ניות דיזנגוף 10" in caption
    assert "<a href" not in caption
    lines = caption.split("\n")
    # Every line carries its own leading RTL mark (see _build_body_lines) right before its emoji,
    # so the location line no longer literally starts with "📍" - "in", not "startswith".
    location_line = next(i for i, line in enumerate(lines) if "📍" in line)
    assert lines[location_line + 1].startswith("🗺️ https://www.google.com/maps/search/")


def test_whatsapp_price_change_header_is_bold_with_asterisks():
    caption = format_caption_whatsapp(make_listing(price=16000), price_change_from=18000, has_access=True)
    assert "*ירידת מחיר!*" in caption


def test_whatsapp_caption_includes_the_raw_url_not_an_html_link():
    caption = format_caption_whatsapp(make_listing(), has_access=True)
    assert "https://www.yad2.co.il/item/abc123" in caption
    assert "<a href" not in caption


def test_whatsapp_footer_has_no_source_tag():
    caption = format_caption_whatsapp(make_listing(), has_access=True)
    assert "🏷️" not in caption


# --- has_access gating (2026-09-05) — a lite/expired user must not get the description or a
# working link out to the actual listing, only paying/trial/owner users do. See
# dorin_common/cards.py's format_caption docstring for why has_access has no default value.


def test_no_access_hides_the_description():
    listing = make_listing(description="דירה מדהימה עם נוף לים")
    caption = format_caption(listing, has_access=False)
    assert "דירה מדהימה" not in caption
    assert "📝" not in caption


def test_no_access_omits_the_real_listing_url():
    listing = make_listing(url="https://www.yad2.co.il/item/secret123")
    caption = format_caption(listing, has_access=False)
    assert "secret123" not in caption


def test_no_access_shows_a_lock_line_with_the_upgrade_url():
    caption = format_caption(make_listing(), has_access=False, upgrade_url="https://todira.app/upgrade?uid=555")
    assert "🔒" in caption
    assert "https://todira.app/upgrade?uid=555" in caption


def test_no_access_without_an_upgrade_url_still_shows_a_generic_lock_line():
    caption = format_caption(make_listing(), has_access=False)
    assert "🔒" in caption


def test_no_access_still_shows_the_basic_teaser_fields():
    # Price/rooms/city/amenities are NOT gated — only the description + real link are, so a lite
    # user still knows a match exists and roughly what it looks like.
    listing = make_listing(has_parking=True)
    caption = format_caption(listing, has_access=False)
    assert "💰 <b>מחיר:</b> 16,000₪" in caption
    assert "🛏️ <b>חדרים:</b> 4" in caption
    assert "🚗חניה" in caption


def test_has_access_true_is_unaffected_by_upgrade_url_being_set():
    listing = make_listing(description="תיאור אמיתי")
    caption = format_caption(listing, has_access=True, upgrade_url="https://x/upgrade")
    assert "תיאור אמיתי" in caption
    assert "🔒" not in caption
    assert "https://x/upgrade" not in caption


def test_whatsapp_no_access_hides_description_and_url_shows_lock_line():
    listing = make_listing(description="תיאור סודי", url="https://www.yad2.co.il/item/secret456")
    caption = format_caption_whatsapp(
        listing, has_access=False, upgrade_url="https://todira.app/upgrade?uid=555"
    )
    assert "תיאור סודי" not in caption
    assert "secret456" not in caption
    assert "🔒" in caption
    assert "https://todira.app/upgrade?uid=555" in caption


# --- send_listing_card (2026-09-02) — real Yad2 photos, added once the scraper started actually
# capturing them (see scraper/normalize.py's enrich_from_detail). Telegram's sendMediaGroup can't
# carry an inline keyboard, so 2+ photos need a follow-up message for the ❤️/🙈/🎉 buttons - the
# one quirk worth locking down with a test.
import asyncio  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

import dorin_common.cards as cards_module  # noqa: E402
from dorin_common.cards import send_listing_card  # noqa: E402


def _make_bot():
    return SimpleNamespace(
        send_message=AsyncMock(),
        send_photo=AsyncMock(),
        send_media_group=AsyncMock(),
    )


def test_send_listing_card_no_images_sends_a_todi_photo():
    # No real photos -> the branded Todi-the-detective illustration instead of a bare text message
    # (2026-09-02 request) — see dorin_common/cards.py's _dachshund_photo_path.
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
    assert "למפרסם" in kwargs["caption"]
    assert kwargs["photo"].name.endswith(".jpg")


def test_send_listing_card_one_image_uses_send_photo_with_keyboard():
    bot = _make_bot()
    listing = make_listing(image_urls=["https://img.yad2.co.il/a.jpg"])
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    bot.send_photo.assert_awaited_once()
    assert bot.send_photo.await_args.kwargs["reply_markup"] is not None
    bot.send_media_group.assert_not_awaited()


def test_send_listing_card_multiple_images_sends_a_generated_collage(monkeypatch):
    # 2026-09-03 request, matching the reference bot dorin.app's own style: 2+ real photos get ONE
    # composited collage image instead of just the first one. Still deliberately NOT a
    # sendMediaGroup gallery (2026-09-02: dropped after a real user report - sendMediaGroup can't
    # carry an inline keyboard, so 2+ photos needed a separate "⬆️ הדירה למעלה" follow-up message
    # just for the buttons) — one send_photo call, one image (now a collage instead of the bare
    # first URL), caption and keyboard together. _build_collage_sync itself does real network
    # downloads (see its own docstring) - monkeypatched here so this stays a fast, network-free
    # unit test, same reasoning as this suite's other httpx-touching tests (e.g. test_yad2_client.py).
    monkeypatch.setattr(cards_module, "_build_collage_sync", lambda urls: b"fake-jpeg-bytes")

    bot = _make_bot()
    listing = make_listing(
        image_urls=["https://img.yad2.co.il/a.jpg", "https://img.yad2.co.il/b.jpg"]
    )
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    bot.send_photo.assert_awaited_once()
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs["photo"] == b"fake-jpeg-bytes"
    assert kwargs["caption"] == "caption"
    assert kwargs["reply_markup"] is not None
    bot.send_media_group.assert_not_awaited()
    bot.send_message.assert_not_awaited()


def test_send_listing_card_falls_back_to_first_photo_when_collage_build_fails(monkeypatch):
    # _build_collage_sync returns None on any failure (a bad URL, a timeout, a corrupt image) — a
    # collage is a nice-to-have, never something that should block sending the listing at all.
    monkeypatch.setattr(cards_module, "_build_collage_sync", lambda urls: None)

    bot = _make_bot()
    listing = make_listing(
        image_urls=["https://img.yad2.co.il/a.jpg", "https://img.yad2.co.il/b.jpg"]
    )
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs["photo"] == "https://img.yad2.co.il/a.jpg"


def test_send_listing_card_single_image_never_attempts_a_collage(monkeypatch):
    # Nothing to collage with exactly 1 real photo — _build_collage_sync must not even be called.
    called = []
    monkeypatch.setattr(
        cards_module, "_build_collage_sync", lambda urls: called.append(urls) or None
    )

    bot = _make_bot()
    listing = make_listing(image_urls=["https://img.yad2.co.il/a.jpg"])
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    assert called == []
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs["photo"] == "https://img.yad2.co.il/a.jpg"


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


def test_dachshund_photo_path_resolves_to_the_mascot_asset():
    # A single branded illustration (2026-09-02), not a rotating photo pool - every call
    # resolves to the same real file.
    from dorin_common.cards import _dachshund_photo_path

    path = _dachshund_photo_path()
    assert path.exists(), f"missing todi illustration asset: {path}"
    assert path.name == "todi_detective.jpg"


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


# --- _build_collage_sync (2026-09-03) — real PIL compositing against mocked httpx.get responses,
# so this stays a fast, network-free unit test (see the module-level comment above
# test_send_listing_card_multiple_images_sends_a_generated_collage for why).

import httpx as _httpx_module  # noqa: E402
from PIL import Image as _PILImage  # noqa: E402

from dorin_common.cards import _build_collage_sync  # noqa: E402


def _fake_jpeg_bytes(color, size=(200, 300)):
    """A real, valid JPEG (not just arbitrary bytes) — _build_collage_sync actually decodes each
    download with PIL, so a fake image needs to be one. Non-square (200x300) deliberately, to
    exercise the center-crop-to-square step with a real aspect ratio mismatch."""
    buffer = __import__("io").BytesIO()
    _PILImage.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _mock_httpx_get(monkeypatch, url_to_response: dict):
    """url_to_response maps a URL to either JPEG bytes (200 OK) or an Exception instance (raised
    as if the request itself failed)."""

    def fake_get(url, timeout=None):
        result = url_to_response[url]
        if isinstance(result, Exception):
            raise result
        return _httpx_module.Response(200, content=result, request=_httpx_module.Request("GET", url))

    monkeypatch.setattr(_httpx_module, "get", fake_get)


def test_build_collage_two_photos_makes_a_2x1_grid(monkeypatch):
    _mock_httpx_get(
        monkeypatch,
        {
            "u1": _fake_jpeg_bytes("red"),
            "u2": _fake_jpeg_bytes("blue"),
        },
    )
    result = _build_collage_sync(["u1", "u2"])
    assert result is not None
    image = _PILImage.open(__import__("io").BytesIO(result))
    assert image.size == (800, 400)  # 2 columns x 1 row, 400px tiles


def test_build_collage_three_photos_makes_a_2x2_grid_with_one_empty_slot(monkeypatch):
    _mock_httpx_get(
        monkeypatch,
        {
            "u1": _fake_jpeg_bytes("red"),
            "u2": _fake_jpeg_bytes("blue"),
            "u3": _fake_jpeg_bytes("green"),
        },
    )
    result = _build_collage_sync(["u1", "u2", "u3"])
    assert result is not None
    image = _PILImage.open(__import__("io").BytesIO(result))
    assert image.size == (800, 800)  # 2 columns x 2 rows to fit a 3rd tile


def test_build_collage_caps_at_four_photos_even_if_more_are_given(monkeypatch):
    _mock_httpx_get(
        monkeypatch,
        {f"u{i}": _fake_jpeg_bytes("red") for i in range(1, 7)},
    )
    result = _build_collage_sync([f"u{i}" for i in range(1, 7)])
    assert result is not None
    image = _PILImage.open(__import__("io").BytesIO(result))
    assert image.size == (800, 800)  # exactly 4 tiles' worth, not 6


def test_build_collage_skips_photos_that_fail_to_download(monkeypatch):
    _mock_httpx_get(
        monkeypatch,
        {
            "u1": _fake_jpeg_bytes("red"),
            "u2": _httpx_module.ConnectError("boom"),
            "u3": _fake_jpeg_bytes("green"),
        },
    )
    result = _build_collage_sync(["u1", "u2", "u3"])
    assert result is not None  # 2 of 3 succeeded, still enough to build something
    image = _PILImage.open(__import__("io").BytesIO(result))
    assert image.size == (800, 400)  # only the 2 successful tiles


def test_build_collage_returns_none_when_fewer_than_two_photos_succeed(monkeypatch):
    _mock_httpx_get(
        monkeypatch,
        {
            "u1": _fake_jpeg_bytes("red"),
            "u2": _httpx_module.ConnectError("boom"),
        },
    )
    assert _build_collage_sync(["u1", "u2"]) is None


def test_build_collage_returns_none_when_every_download_fails(monkeypatch):
    _mock_httpx_get(
        monkeypatch,
        {
            "u1": _httpx_module.ConnectError("boom"),
            "u2": _httpx_module.ConnectError("boom"),
        },
    )
    assert _build_collage_sync(["u1", "u2"]) is None
