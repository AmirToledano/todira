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
