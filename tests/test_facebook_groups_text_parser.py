"""Tests for facebook_groups_text_parser.py — built against the two real, live-confirmed post texts
from diagnose-facebook-group-post-detail.yaml/diagnose-facebook-home-feed-story-extraction.yaml (see
that module's own docstring)."""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from facebook_groups_text_parser import parse_listing_fields

REAL_POST_1 = (
    '*יחידת הורים אחרונה ברחוב ששת הימים 7*\n'
    'יחידת הורים מוארת בדירת שותפים.🍒\n'
    'משופץ מהיסוד וברמה גבוהה. 👌\n'
    'הכל ממוזג, מרוהט ומאובזר באהבה. ❤️\n'
    '15 דקות הליכה מהאוניברסיטה. 🚶🏽‍♂️\n'
    'דופלקס כדירת חמישה שותפים. \n'
    'חניה ציבורית בשפע ובחינם .🚘\n'
    '1,350ש"ח + חשבונות נמוכים. ללא דמי תיווך.\n'
    'לפרטים ותמונות נוספות: דרור בעלי 050-9516572.🙏*עדכון מחיר*'
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
