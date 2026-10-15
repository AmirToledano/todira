"""Tests for facebook_groups_text_parser.py — built against the two real, live-confirmed post texts
from diagnose-facebook-group-post-detail.yaml/diagnose-facebook-home-feed-story-extraction.yaml (see
that module's own docstring)."""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from facebook_groups_text_parser import parse_listing_fields, rooms_and_size

REAL_POST_1 = (
    '*יחידת הורים אחרונה ברחוב ששת הימים 7*\n'
    'יחידת הורים מוארת בדירת שותפים.🍒\n'
    'משופץ מהיסוד וברמה גבוהה. 👌\n'
    'הכל ממוזג, מרוהט ומאובזר באהבה. ❤️\n'
    '15 דקות הליכה מהאוניברסיטה. 🚶🏽‍♂️\n'
    'דופלקס כדירת חמישה שותפים. \n'
    'חניה ציבורית בשפע ובחינם .🚘\n'
    '1,350ש"ח + חשבונות נמוכים. ללא דמי תיווך.\n'
    'לפרטים ותמונות נוספות: בעל הדירה 050-0000000.🙏*עדכון מחיר*'
)

REAL_POST_2 = (
    'יחידת דיור משופצת חדשה מוארת מאוד בקומה 9, חדר שינה, מטבח, מבואה וגג ענק מרוהטת, '
    'כולל מערכת מיזוג אויר\nהמחיר כולל: ארנונה וועד בית \nכניסה: 1/11\nמיקום '
)


def test_parses_price_rooms_amenities_from_real_post_1():
    fields = parse_listing_fields(REAL_POST_1)
    assert fields["price"] == 1350
    assert fields["parking"] is True
    assert fields["renovated"] is True
    assert fields["roommates"] is True
    assert "rooms" not in fields  # no numeric room count anywhere in this real text
    assert "floor" not in fields


def test_parses_floor_and_renovated_from_real_post_2_despite_sofit_letter():
    fields = parse_listing_fields(REAL_POST_2)
    assert fields["floor"] == 9
    assert fields["renovated"] is True  # "משופצת" — regular צ form, distinct from post 1's ץ form


def test_price_handles_prefix_and_suffix_currency_marks():
    assert parse_listing_fields("המחיר ₪4,500 לחודש")["price"] == 4500
    assert parse_listing_fields("4500 ש\"ח בחודש")["price"] == 4500
    assert parse_listing_fields("עלות: 3000₪")["price"] == 3000


def test_rooms_and_square_meters():
    fields = parse_listing_fields("דירת 3.5 חדרים, 80 מ\"ר, קומה 2")
    assert fields["rooms"] == 3.5
    assert fields["square_meters"] == 80
    assert fields["floor"] == 2


def test_ground_floor_maps_to_zero():
    assert parse_listing_fields("דירה יפה בקומת קרקע עם גינה")["floor"] == 0


def test_pets_allowed_positive():
    assert parse_listing_fields("מתאים לזוג עם חיות מחמד")["petsAllowed"] is True


def test_pets_negation_does_not_set_true():
    fields = parse_listing_fields("אסור חיות מחמד בבניין")
    assert "petsAllowed" not in fields


def test_empty_text_returns_empty_dict():
    assert parse_listing_fields("") == {}
    assert parse_listing_fields(None) == {}  # type: ignore[arg-type]


def test_text_with_no_matches_returns_empty_dict():
    assert parse_listing_fields("שלום, מה שלומכם היום?") == {}


# --- 2026-10-15: rooms_and_size, also used for Marketplace ads -------------------------------------


def test_rooms_and_size_read_the_common_ways_of_writing_them():
    assert rooms_and_size('דירת 3 חדרים ברמת גן, 75 מ"ר') == {"rooms": 3.0, "square_meters": 75}
    assert rooms_and_size("להשכרה 3.5 חד' משופצת 90 מטר") == {"rooms": 3.5, "square_meters": 90}
    assert rooms_and_size("דירת 2.5חד 55מ״ר") == {"rooms": 2.5, "square_meters": 55}


def test_a_distance_is_never_a_size():
    assert rooms_and_size("דירה 4 חדרים, 200 מטר מהים") == {"rooms": 4.0}
    assert rooms_and_size("80 מטרים לתחנה, 3 חד") == {"rooms": 3.0}


def test_a_room_in_a_shared_flat_gets_no_room_count():
    assert "rooms" not in rooms_and_size("חדר להשכרה בדירת 4 חדרים בפלורנטין")
    assert "rooms" not in rooms_and_size("מחפשים שותף לדירת 3 חדרים")


def test_bedrooms_and_unbelievable_numbers_are_ignored():
    assert rooms_and_size("2 חדרי שינה וסלון") == {}
    assert rooms_and_size("דירה 100 חדרים") == {}
    assert rooms_and_size('דירת 3 חדרים 1000 מ"ר') == {"rooms": 3.0}
    assert rooms_and_size("") == {} and rooms_and_size(None) == {}
