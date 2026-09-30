"""Unit tests for todira_common/cards.py — Telegram/WhatsApp caption rendering for a Listing, plus
send_listing_card's send behavior and _build_collage_sync's photo-compositing (both against a fake
bot / mocked httpx — no real Telegram or network calls).

The format_caption*/make_listing tests are pure string-formatting logic (no I/O, no DB) —
SimpleNamespace stands in for a real Listing row, same approach test_matching.py already uses,
since format_caption/format_caption_whatsapp only ever read attributes off whatever's passed in.
"""
from __future__ import annotations

from types import SimpleNamespace

from todira_common.cards import (
    CAPTION_LIMIT,
    _fit_to_limit,
    format_caption,
    format_caption_whatsapp,
)
from todira_common.bot_strings import bot_text


def _b(text: str) -> str:
    """The plain `<b>...</b>` shape _build_body_lines' own `bold` closure builds for Telegram —
    every caption line is plain HTML text now (see cards.py's own module comment above
    _normalize_line_breaks for the full RTL-marks-removal history), so this is simply what
    production emits, not a pre-transform input the way it used to be."""
    return f"<b>{text}</b>"


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
    # 2026-09-03 rewrite, matching the reference bot 1:1: location before price, every
    # field its own BOLD-labeled line, ₪ (not "ש"ח") as the currency, no source tag anywhere.
    caption = format_caption(make_listing(), has_access=True)
    assert f"🛏️ {_b('חדרים:')} 4" in caption
    assert f'📐 {_b("שטח:")} 160 מ"ר' in caption
    assert f"💰 {_b('מחיר:')} 16,000₪" in caption
    assert f"📍{_b('ירושלים')} - ניות" in caption
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
    assert f"🏢 {_b('תיווך')}" in caption

    caption = format_caption(make_listing(deal_type="rent", is_broker_listing=True), has_access=True)
    assert f"🏢 {_b('תיווך')}" in caption


def test_sublet_prefix_line_shown_when_not_broker():
    caption = format_caption(make_listing(deal_type="sublet", is_broker_listing=False), has_access=True)
    assert f"🏢 {_b('סאבלט')}" in caption
    assert "תיווך" not in caption


def test_broker_prefix_wins_over_sublet_if_somehow_both():
    caption = format_caption(make_listing(deal_type="sublet", is_broker_listing=True), has_access=True)
    assert f"🏢 {_b('תיווך')}" in caption
    assert "סאבלט" not in caption


def test_location_street_is_a_google_maps_link_on_telegram():
    caption = format_caption(make_listing(street="דיזנגוף 10"), has_access=True)
    assert f'📍{_b("ירושלים")} - ניות <a href="https://www.google.com/maps/search/' in caption
    assert ">דיזנגוף 10</a>" in caption
    assert "דיזנגוף+10" in caption or "%D7%93%D7%99%D7%96%D7%A0%D7%92%D7%95%D7%A3" in caption


def test_location_without_street_has_no_maps_link():
    caption = format_caption(make_listing(), has_access=True)
    assert "google.com/maps" not in caption


def test_street_with_a_literal_quote_mark_renders_plain_not_as_quot_entity():
    # Real bug, found 2026-09-30 via an owner screenshot: a street name containing Hebrew
    # gershayim (e.g. "הפלמ"ח 1", an abbreviation punctuation mark, not markup) rendered as
    # literal, garbled "הפלמ&quot;ח 1" text in a real Telegram message. Root cause: html.escape's
    # own default (quote=True) escapes a bare `"` to `&quot;` even in plain element CONTENT, where
    # Telegram's own HTML parser doesn't recognize &quot; as a named entity (unlike &lt;/&gt;/&amp;)
    # — only inside an attribute value does a literal `"` need escaping at all, and street/city
    # text is never placed inside one. See format_caption's own escape=/description escaping.
    caption = format_caption(make_listing(street='הפלמ"ח 1'), has_access=True)
    assert "&quot;" not in caption
    assert 'הפלמ"ח 1' in caption

    caption_desc = format_caption(make_listing(description='דירה ברח\' פלמ"ח, קומה גבוהה'), has_access=True)
    assert "&quot;" not in caption_desc
    assert 'פלמ"ח' in caption_desc


def test_floor_line_includes_total_when_known():
    caption = format_caption(make_listing(floor=4, floor_total=6), has_access=True)
    assert f"🏢 {_b('קומה:')} 4 מתוך 6" in caption


def test_move_in_date_is_day_month_year_not_iso():
    import datetime

    caption = format_caption(make_listing(move_in_date=datetime.date(2026, 9, 21)), has_access=True)
    assert f"📅 {_b('כניסה:')} 21.09.2026" in caption
    assert "2026-09-21" not in caption


def test_no_features_line_when_nothing_is_known():
    caption = format_caption(make_listing(), has_access=True)
    assert "פיצ'רים" not in caption


def test_features_line_uses_a_distinct_emoji_per_feature_pipe_separated():
    listing = make_listing(has_parking=True, has_elevator=True, is_renovated=True)
    caption = format_caption(listing, has_access=True)
    features_label = _b("פיצ'רים:")
    assert f"🔑 {features_label} 🚗חניה | 🛗מעלית | ✨משופצת" in caption


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


def test_caption_has_no_bidi_control_characters():
    # 2026-09-30, the actual resolution to a long RTL-alignment saga (see cards.py's own module
    # comment above _normalize_line_breaks for the full history): a real reference bot's own
    # message, copied directly out of Telegram Desktop, contains ZERO invisible bidi marks and
    # renders correctly right-aligned on its own. Every earlier mark-based attempt this project
    # tried (a bare RLM, RLE/PDF embeddings, RLI/PDI isolates + ZWNJ) left a persistent
    # misalignment that no further mark tuning closed — dropping every mark fixed it instead.
    # This test locks in that resolution: no caption, in any language, should ever carry one of
    # these control characters again.
    for lang in ("he", "ar", "en", "ru", "fr"):
        caption = format_caption(make_listing(street="דיזנגוף 10"), has_access=True, lang=lang)
        for mark in ("‏", "‎", "⁧", "⁩", "‌", "‫", "‬"):
            assert mark not in caption, f"stray bidi control character {mark!r} in lang={lang} caption"


def test_multiline_description_keeps_every_physical_line():
    # 2026-09-18: real user screenshots showed a scraped description containing several physical
    # lines (e.g. "דירת 5 חדרים...\nחדשה מהקבלן...\n2 חניות\nמחסן") — every physical line must
    # still be present and in order in the final caption.
    multiline_description = "דירת 5 חדרים יפיפייה\nחדשה מהקבלן עדיין לא אוכלסה\n2 חניות\nמחסן"
    caption = format_caption(make_listing(description=multiline_description), has_access=True)
    assert "📝 דירת 5 חדרים יפיפייה" in caption
    assert "חדשה מהקבלן עדיין לא אוכלסה" in caption
    assert "2 חניות" in caption
    assert "מחסן" in caption


def test_whatsapp_multiline_description_keeps_every_physical_line():
    multiline_description = "דירת 5 חדרים יפיפייה\nחדשה מהקבלן עדיין לא אוכלסה\n2 חניות\nמחסן"
    caption = format_caption_whatsapp(
        make_listing(description=multiline_description), has_access=True
    )
    assert "📝 דירת 5 חדרים יפיפייה" in caption
    assert "חדשה מהקבלן עדיין לא אוכלסה" in caption
    assert "2 חניות" in caption
    assert "מחסן" in caption


def test_carriage_return_only_description_still_splits_into_separate_lines():
    # 2026-09-21: real Homeless listings use a bare "\r" as their line separator, not "\n" —
    # _normalize_line_breaks (splitlines()-based) handles "\r" too.
    cr_description = "דירה להשכרה\rבמרכז העיר\rקומה 3"
    caption = format_caption(make_listing(description=cr_description), has_access=True)
    assert "📝 דירה להשכרה" in caption
    assert "במרכז העיר" in caption
    assert "קומה 3" in caption


def test_long_single_line_description_is_not_manually_pre_wrapped():
    # 2026-09-30: manual pre-wrapping (this file used to force short lines to keep a client
    # soft-wrap from interacting badly with bidi marks) is gone along with the marks themselves —
    # Telegram/WhatsApp are left to wrap long lines on their own, same as the real reference bot
    # this approach was modeled on.
    long_description = "יחידת דיור משופצת כולל גינה כניסה 20.10.26"
    caption = format_caption(make_listing(description=long_description), has_access=True)
    assert f"📝 {long_description}" in caption


def test_no_photos_banner_stays_valid_html():
    # cards.py's send_listing_card builds this exact banner (bot_text("card.no_photos_banner")
    # rstripped, "\n\n" appended) before prepending it to the caption — tested here at the same
    # level as every other format test in this file, since send_listing_card itself needs a fake
    # Telegram Bot to exercise (covered separately below).
    banner_text = bot_text("card.no_photos_banner", "he").rstrip("\n")
    result = f"{banner_text}\n\n"
    assert result.endswith("\n\n"), "the blank-line gap before the caption must survive"
    assert "<b>" in result and "</b>" in result


def test_blank_spacer_line_stays_truly_blank():
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
    assert caption.startswith("📉")
    assert "ירידת מחיר" in caption
    assert "18,000" in caption


def test_price_increase_header_prepended():
    caption = format_caption(make_listing(price=18000), price_change_from=16000, has_access=True)
    assert caption.startswith("📈")
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


def test_fit_to_limit_is_a_noop_when_already_within_budget():
    assert _fit_to_limit("H", "B", "F", limit=100) == "HBF"


def test_fit_to_limit_drops_whole_body_lines_never_a_partial_one():
    # Real production bug, 2026-09-14: the old blind `[:CAPTION_LIMIT]` character slice could
    # land inside an <a>...</a> tag - dropping whole lines instead can never do that, since every
    # real <a> tag in this file opens and closes within one line.
    body = "aaaa\nbbbb\ncccc\ndddd"
    result = _fit_to_limit("", body, "FOOTER", limit=15)
    assert result.endswith("FOOTER")
    kept_body = result[: -len("FOOTER")]
    for line in kept_body.split("\n"):
        assert line == "" or line in {"aaaa", "bbbb", "cccc", "dddd"}


def test_fit_to_limit_never_drops_the_footer():
    result = _fit_to_limit("", "way too much body content here", "FOOTER", limit=5)
    assert result.endswith("FOOTER")


def test_overflowing_caption_never_cuts_an_html_tag_in_half():
    # Real production bug, 2026-09-14: 18+ real sends in one live run failed with
    # `telegram.error.BadRequest: Can't parse entities: can't find end tag...` /
    # `unclosed start tag at byte offset ...` - a content-heavy listing (a price-change header +
    # a long street/maps <a> link + several features) pushed the caption past CAPTION_LIMIT with
    # NO description involved at all, so the description-only length budget never even engaged,
    # and the final blind slice landed inside an <a> tag.
    listing = make_listing(
        street="רחוב עם שם ארוך מאוד " * 10,
        has_parking=True,
        has_elevator=True,
        has_balcony=True,
        pets_allowed=True,
        is_renovated=True,
        is_roommate_friendly=True,
        safe_room_type="safe_room",
        furniture="furnished",
    )
    caption = format_caption(listing, price_change_from=10000, has_access=True)
    assert len(caption) <= CAPTION_LIMIT
    assert caption.count("<a ") == caption.count("</a>")
    # The footer - the listing's own link - must always survive intact, never sacrificed to make
    # room for body content.
    assert "לפרטי הדירה המלאים" in caption


# --- has_access gating — a lite/expired user must not get a working link out to the actual
# listing; the description IS shown to everyone as of 2026-09-12 (reversing the original
# 2026-09-05 decision). See todira_common/cards.py's format_caption docstring for that history and
# why has_access has no default value.


def test_no_access_still_shows_the_description():
    listing = make_listing(description="דירה מדהימה עם נוף לים")
    caption = format_caption(listing, has_access=False)
    assert "דירה מדהימה" in caption
    assert "📝" in caption


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
    # Price/rooms/city/amenities/description are NOT gated — only the real link is, so a lite
    # user still sees everything about the match except where to actually go for it.
    listing = make_listing(has_parking=True)
    caption = format_caption(listing, has_access=False)
    assert f"💰 {_b('מחיר:')} 16,000₪" in caption
    assert f"🛏️ {_b('חדרים:')} 4" in caption
    assert "🚗חניה" in caption


def test_has_access_true_is_unaffected_by_upgrade_url_being_set():
    listing = make_listing(description="תיאור אמיתי")
    caption = format_caption(listing, has_access=True, upgrade_url="https://x/upgrade")
    assert "תיאור אמיתי" in caption
    assert "🔒" not in caption
    assert "https://x/upgrade" not in caption


def test_view_url_replaces_the_raw_listing_url_when_given():
    """2026-09-27 real owner request, matching dorin.app: the outbound link should land on this
    project's own listing page, not send the viewer straight to the raw external source (Yad2/
    Facebook/whatever it was scraped from)."""
    listing = make_listing(url="https://www.yad2.co.il/item/secret789")
    caption = format_caption(
        listing, has_access=True, view_url="https://todira.app/apartments?uid=1&listing=77"
    )
    assert "https://todira.app/apartments?uid=1&amp;listing=77" in caption
    assert "secret789" not in caption


def test_no_view_url_falls_back_to_the_raw_listing_url():
    listing = make_listing(url="https://www.yad2.co.il/item/secret789")
    caption = format_caption(listing, has_access=True)
    assert "secret789" in caption


def test_whatsapp_no_access_still_shows_description_but_hides_url_shows_lock_line():
    listing = make_listing(description="תיאור סודי", url="https://www.yad2.co.il/item/secret456")
    caption = format_caption_whatsapp(
        listing, has_access=False, upgrade_url="https://todira.app/upgrade?uid=555"
    )
    assert "תיאור סודי" in caption
    assert "secret456" not in caption
    assert "🔒" in caption
    assert "https://todira.app/upgrade?uid=555" in caption


def test_telegram_caption_escapes_html_in_scraped_fields():
    # Found live 2026-09-07: city/neighborhood/street/description/url are all scraped from Yad2
    # (and, for description, potentially Bright Data), not written by this project — with
    # parse_mode=HTML, a raw "<"/"&"/">" in any of them could either break the caption's HTML
    # parsing or let scraped text inject an arbitrary tag into a real-formatted message.
    listing = make_listing(
        city="<script>city</script>",
        neighborhood="A & B <b>fake bold</b>",
        street="Main <i>St</i>",
        description="נכס עם <img src=x> תיאור & פרטים",
        url="https://www.yad2.co.il/item/\"onmouseover=alert(1)",
    )
    caption = format_caption(listing, has_access=True)
    assert "<script>" not in caption
    assert "&lt;script&gt;" in caption
    assert "<b>fake bold</b>" not in caption
    assert "A &amp; B &lt;b&gt;fake bold&lt;/b&gt;" in caption
    assert "<i>St</i>" not in caption
    assert "<img" not in caption
    assert '"onmouseover=alert(1)' not in caption


def test_whatsapp_caption_does_not_html_escape_plain_text():
    # WhatsApp captions are plain text, not HTML — raw "&"/"<" must pass through unescaped there.
    listing = make_listing(city="A & B", neighborhood="C <D>")
    caption = format_caption_whatsapp(listing, has_access=True)
    assert "A & B" in caption
    assert "C <D>" in caption


# --- lang (2026-09-26 "full compatibility" follow-up) — every field label/feature/footer now
# goes through bot_strings.bot_text(key, lang) instead of a fixed Hebrew string. `lang` defaults
# to DEFAULT_LANG ("he") so every existing call site above (and every real caller that predates
# this) keeps behaving exactly as before without passing it.


def test_format_caption_defaults_to_hebrew_when_lang_omitted():
    caption = format_caption(make_listing(), has_access=True)
    assert "מחיר:" in caption
    assert "חדרים:" in caption


def test_format_caption_renders_english_labels():
    caption = format_caption(make_listing(), has_access=True, lang="en")
    assert "Price:" in caption
    assert "Rooms:" in caption
    assert "Full listing details" in caption
    assert "מחיר" not in caption


def test_format_caption_renders_arabic_labels():
    caption = format_caption(make_listing(), has_access=True, lang="ar")
    assert "السعر:" in caption


def test_format_caption_renders_russian_and_french_labels():
    ru_caption = format_caption(make_listing(), has_access=True, lang="ru")
    assert "Цена:" in ru_caption
    fr_caption = format_caption(make_listing(), has_access=True, lang="fr")
    assert "Prix" in fr_caption


def test_format_caption_upgrade_lock_line_is_translated():
    caption = format_caption(make_listing(), has_access=False, lang="en")
    assert "Upgrade your subscription" in caption
    caption_with_url = format_caption(
        make_listing(), has_access=False, upgrade_url="https://x/upgrade", lang="en"
    )
    assert "upgrade your subscription" in caption_with_url


def test_format_caption_price_change_header_is_translated():
    caption = format_caption(
        make_listing(price=16000), has_access=True, price_change_from=18000, lang="en"
    )
    assert "Price drop!" in caption
    assert "was 18,000" in caption


def test_format_caption_whatsapp_renders_english_labels():
    caption = format_caption_whatsapp(make_listing(), has_access=True, lang="en")
    assert "Price:" in caption
    assert "Full listing details" in caption


def test_listing_keyboard_buttons_are_translated():
    from todira_common.cards import listing_keyboard

    markup = listing_keyboard(1, "en")
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert any("Save" in b.text for b in buttons)
    assert any("Hide" in b.text for b in buttons)
    assert any("Found an apartment" in b.text for b in buttons)


# --- send_listing_card (2026-09-02) — real Yad2 photos, added once the scraper started actually
# capturing them (see scraper/normalize.py's enrich_from_detail). Telegram's sendMediaGroup can't
# carry an inline keyboard, so 2+ photos need a follow-up message for the ❤️/🙈/🎉 buttons - the
# one quirk worth locking down with a test.
import asyncio  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

import todira_common.cards as cards_module  # noqa: E402
from todira_common.cards import send_listing_card  # noqa: E402


def _make_bot():
    return SimpleNamespace(
        send_message=AsyncMock(),
        send_photo=AsyncMock(),
        send_media_group=AsyncMock(),
    )


def test_send_listing_card_no_images_sends_a_todi_photo():
    # No real photos -> the branded Todi-the-detective illustration instead of a bare text message
    # (2026-09-02 request) — see todira_common/cards.py's _dachshund_photo_path.
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


def test_send_listing_card_one_image_uses_send_photo_with_keyboard(monkeypatch):
    # 2026-09-21: the single photo is now downloaded/validated (see
    # _first_downloadable_photo_jpeg_bytes) rather than its raw URL handed straight to
    # bot.send_photo — monkeypatched here for the same network-free-unit-test reason as the
    # collage tests below.
    monkeypatch.setattr(
        cards_module, "_first_downloadable_photo_jpeg_bytes", lambda urls: b"fake-jpeg-bytes"
    )
    bot = _make_bot()
    listing = make_listing(image_urls=["https://img.yad2.co.il/a.jpg"])
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    bot.send_photo.assert_awaited_once()
    assert bot.send_photo.await_args.kwargs["reply_markup"] is not None
    assert bot.send_photo.await_args.kwargs["photo"] == b"fake-jpeg-bytes"
    bot.send_media_group.assert_not_awaited()


def test_send_listing_card_multiple_images_sends_a_generated_collage(monkeypatch):
    # 2026-09-03 request, matching the reference bot's own style: 2+ real photos get ONE
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


def test_send_listing_card_falls_back_to_first_downloadable_photo_when_collage_build_fails(
    monkeypatch,
):
    # _build_collage_sync returns None on any failure (a bad URL, a timeout, a corrupt image) — a
    # collage is a nice-to-have, never something that should block sending the listing at all.
    # 2026-09-21: the fallback itself is now validated bytes (_first_downloadable_photo_jpeg_bytes),
    # not the raw first URL blindly trusted — see that function's own docstring for the real bug
    # this replaced.
    monkeypatch.setattr(cards_module, "_build_collage_sync", lambda urls: None)
    monkeypatch.setattr(
        cards_module, "_first_downloadable_photo_jpeg_bytes", lambda urls: b"fake-jpeg-bytes"
    )

    bot = _make_bot()
    listing = make_listing(
        image_urls=["https://img.yad2.co.il/a.jpg", "https://img.yad2.co.il/b.jpg"]
    )
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs["photo"] == b"fake-jpeg-bytes"


def test_send_listing_card_single_image_never_attempts_a_collage(monkeypatch):
    # Nothing to collage with exactly 1 real photo — _build_collage_sync must not even be called.
    called = []
    monkeypatch.setattr(
        cards_module, "_build_collage_sync", lambda urls: called.append(urls) or None
    )
    monkeypatch.setattr(
        cards_module, "_first_downloadable_photo_jpeg_bytes", lambda urls: b"fake-jpeg-bytes"
    )

    bot = _make_bot()
    listing = make_listing(image_urls=["https://img.yad2.co.il/a.jpg"])
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    assert called == []
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs["photo"] == b"fake-jpeg-bytes"


def test_send_listing_card_falls_back_to_mascot_when_every_photo_url_is_dead(monkeypatch):
    # 2026-09-21: real bug, live screenshot — a listing WITH photo URLs that all fail to download
    # used to hand the (dead) first URL straight to bot.send_photo, which Telegram then rendered
    # as a generic broken-image placeholder instead of falling back to the Todi mascot. The mascot
    # fallback must now also trigger when every candidate photo fails to download, not just when
    # image_urls is empty.
    monkeypatch.setattr(cards_module, "_first_downloadable_photo_jpeg_bytes", lambda urls: None)

    bot = _make_bot()
    listing = make_listing(image_urls=["https://www.komo.co.il/dead-photo.jpg"])
    ok = asyncio.run(send_listing_card(bot, 555, listing, "caption"))
    assert ok is True
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs["photo"].name.endswith(".jpg")
    assert "למפרסם" in kwargs["caption"]


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
    from todira_common.cards import _dachshund_photo_path

    path = _dachshund_photo_path()
    assert path.exists(), f"missing todi illustration asset: {path}"
    assert path.name == "todi_detective.jpg"


def test_send_listing_card_no_images_caption_stays_within_telegram_limit():
    from todira_common.cards import CAPTION_LIMIT

    bot = _make_bot()
    listing = make_listing(image_urls=[])
    long_caption = "א" * CAPTION_LIMIT  # already at the limit before the dachshund suffix
    asyncio.run(send_listing_card(bot, 555, listing, long_caption))
    assert len(bot.send_photo.await_args.kwargs["caption"]) <= CAPTION_LIMIT


def test_send_listing_card_no_images_drops_the_banner_entirely_when_it_would_overflow_the_limit():
    # 2026-09-28: real bug found via a fresh code-review sweep — the no-photos banner used to be
    # prepended and the combined string then raw-sliced to CAPTION_LIMIT with a plain [:LIMIT], a
    # cut that could land mid-HTML-tag inside the CAPTION's own markup (e.g. a listing's <a href=
    # "..."> link) whenever banner+caption together ran over the limit, since the slice has no
    # idea where a tag boundary is. The banner is now dropped entirely in that case instead — the
    # caption itself is already a complete, valid string on its own, so it's sent whole and untouched.
    from todira_common.cards import CAPTION_LIMIT

    bot = _make_bot()
    listing = make_listing(image_urls=[])
    long_caption = "א" * CAPTION_LIMIT  # already at the limit — no room for the banner at all
    asyncio.run(send_listing_card(bot, 555, listing, long_caption))
    sent = bot.send_photo.await_args.kwargs["caption"]
    assert sent == long_caption
    assert "למפרסם" not in sent  # the banner text itself never made it in


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

from todira_common.cards import _build_collage_sync  # noqa: E402


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


# --- get_listing_photo_jpeg_bytes (2026-09-27) — the public, always-returns-bytes wrapper
# scraper/notifier.py's WhatsApp rich match-template send uses to get ONE image to upload, same
# collage/first-photo/mascot fallback chain send_listing_card already inlines for Telegram. ---

from todira_common.cards import get_listing_photo_jpeg_bytes  # noqa: E402


def test_get_listing_photo_prefers_a_collage_when_2plus_photos(monkeypatch):
    called = []
    monkeypatch.setattr(cards_module, "_build_collage_sync", lambda urls: called.append(urls) or b"collage-bytes")
    assert get_listing_photo_jpeg_bytes(["u1", "u2"]) == b"collage-bytes"
    assert called == [["u1", "u2"]]


def test_get_listing_photo_falls_back_to_first_photo_when_collage_fails(monkeypatch):
    monkeypatch.setattr(cards_module, "_build_collage_sync", lambda urls: None)
    monkeypatch.setattr(cards_module, "_first_downloadable_photo_jpeg_bytes", lambda urls: b"single-photo-bytes")
    assert get_listing_photo_jpeg_bytes(["u1", "u2"]) == b"single-photo-bytes"


def test_get_listing_photo_never_attempts_a_collage_for_a_single_url(monkeypatch):
    called = []
    monkeypatch.setattr(cards_module, "_build_collage_sync", lambda urls: called.append(urls) or None)
    monkeypatch.setattr(cards_module, "_first_downloadable_photo_jpeg_bytes", lambda urls: b"single-photo-bytes")
    assert get_listing_photo_jpeg_bytes(["u1"]) == b"single-photo-bytes"
    assert called == []


def test_get_listing_photo_falls_back_to_mascot_when_every_url_fails():
    assert get_listing_photo_jpeg_bytes([]) == cards_module._MASCOT_PATH.read_bytes()


def test_get_listing_photo_never_returns_none(monkeypatch):
    # Real callers (scraper/notifier.py) rely on this always being real bytes, never None — no
    # no-photo branch of their own to maintain.
    monkeypatch.setattr(cards_module, "_build_collage_sync", lambda urls: None)
    monkeypatch.setattr(cards_module, "_first_downloadable_photo_jpeg_bytes", lambda urls: None)
    result = get_listing_photo_jpeg_bytes(["u1", "u2"])
    assert result is not None
    assert result == cards_module._MASCOT_PATH.read_bytes()
