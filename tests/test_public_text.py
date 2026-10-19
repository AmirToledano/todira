"""2026-10-19 (owner screenshots): a group post from someone LOOKING for a flat went out as a listing, and cards showed
the poster's name and phone numbers. Reaching a poster goes through Todira only, so the text shown never carries them."""
from __future__ import annotations

import facebook_groups_text_parser as parser
from todira_common.public_text import is_room_in_shared_flat, public_description


def test_phone_lines_and_the_poster_name_are_removed():
    text = (
        "מתפנה חדר בדירת 4 חדרים\nשכר דירה: 1,470 ש\"ח\n\nלפרטים נוספים:\nנגה-0547341019\n\n(מפרסם/ת: Irit Carmel)"
    )
    shown = public_description(text)
    assert "0547341019" not in shown and "נגה" not in shown and "Irit" not in shown
    assert "לפרטים נוספים" not in shown
    assert shown.startswith("מתפנה חדר") and "1,470" in shown


def test_a_number_inside_a_long_sentence_goes_and_the_sentence_stays():
    text = "דירה יפה ומרווחת עם מרפסת גדולה ונוף לים, אפשר להתקשר אליי 050-1234567 בכל שעה ולתאם צפייה בדירה"
    shown = public_description(text)
    assert "050-1234567" not in shown and "נוף לים" in shown


def test_links_emails_and_whatsapp_are_removed():
    shown = public_description("3 חדרים ברמת גן\nwa.me/972541234567\nכתבו לי: dana@example.com\nhttps://example.com/x")
    assert shown == "3 חדרים ברמת גן"


def test_prices_floors_and_dates_are_not_mistaken_for_phones():
    text = 'קומה 3 מתוך 4, 85 מ"ר, מחיר 5,400 ש"ח, כניסה 1.11.2026'
    assert public_description(text) == text


def test_a_room_in_a_shared_flat_is_recognised():
    assert is_room_in_shared_flat("חדר בדירת שותפות בכרמל")
    assert is_room_in_shared_flat("מחפשים שותפה לדירת 3 חדרים")
    assert not is_room_in_shared_flat("דירת 3 חדרים להשכרה ברמת גן")


def test_someone_looking_for_a_flat_is_never_a_listing():
    assert parser.looks_like_seeker("מחפשת להשכרה דירה ללא צקים, קומה קרקע עדיף כניסה נפרדת\nחדר גג 2 חדרים")
    assert parser.looks_like_seeker("מחפש סאבלט בתל אביב לחודש")
    assert not parser.looks_like_seeker("מחפשים שותפה לדירת 3 חדרים בפלורנטין, 2,500 ש\"ח")
    assert not parser.looks_like_seeker("מפנה דירה, מחפשים מחליף! 3 חדרים 5,000")


def test_a_post_naming_only_a_neighbourhood_gets_its_city():
    fields = parser.parse_place_and_deal("חדר בדירת שותפות בכרמל, על ציר מוריה")
    assert fields["city"] == "חיפה"
