"""todira_common.text_features (2026-10-09): card fields read out of an ad's own free text (Komo / Facebook / Homeless / Yad2).

The rule these tests pin: a field comes back ONLY when the text states it. A feature is False only on an explicit negation right
before the word, and anything that is not a statement about this flat ("חניה ברחוב", "אפשרות לחניה", "מטבח מרוהט") is left out."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from todira_common.text_features import apply_missing, features_from_text, missing_updates

TODAY = dt.date(2026, 10, 9)


def f(text):
    return features_from_text(text, today=TODAY)


# --- floors ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("דירה בקומה 3", {"floor": 3}),
        ("קומה 3 מתוך 5", {"floor": 3, "floor_total": 5}),
        ("קומה 3 מ-5", {"floor": 3, "floor_total": 5}),
        ("קומה 3/5", {"floor": 3, "floor_total": 5}),
        ("קומת קרקע", {"floor": 0}),
        ("קומה 0", {"floor": 0}),
        ("בקומה השלישית", {"floor": 3}),
        ("קומה שניה", {"floor": 2}),
        ("קומה ראשונה", {"floor": 1}),
        ("קומה ג' בבניין", {"floor": 3}),
        ("בניין בן 6 קומות", {"floor_total": 6}),
        ("קומה 2 בבניין בן 4 קומות", {"floor": 2, "floor_total": 4}),
        ("קומה 2 מתוך 4 קומות", {"floor": 2, "floor_total": 4}),
        ("קומה אחרונה", {}),
        ("קומה 90", {}),
        ("קומה 7 מתוך 4", {"floor": 7}),  # a floor above the stated total: the total is dropped as a typo, the floor kept
    ],
)
def test_floors(text, expected):
    assert f(text) == expected


def test_the_plural_word_is_not_a_floor():
    assert f("קומות 3") == {}


# --- features ---------------------------------------------------------------------------------------------------------


def test_plain_mentions_are_true():
    got = f("דירה מקסימה עם חניה, מעלית, מרפסת וממ\"ד")
    assert got["has_parking"] is True and got["has_elevator"] is True and got["has_balcony"] is True
    assert got["safe_room_type"] == "safe_room"


@pytest.mark.parametrize(
    "text, column",
    [
        ("ללא חניה", "has_parking"),
        ("אין מעלית בבניין", "has_elevator"),
        ("בלי מרפסת", "has_balcony"),
    ],
)
def test_explicit_negation_right_before_the_word_is_false(text, column):
    assert f(text)[column] is False


def test_a_negation_does_not_leak_across_a_comma_or_a_positive_connector():
    assert f("ללא חניה, עם מעלית")["has_elevator"] is True
    assert f("ללא חניה ועם מעלית")["has_elevator"] is True
    assert f("ללא מעלית אבל עם חניה")["has_parking"] is True
    assert f("אין מעלית. יש חניה")["has_parking"] is True


def test_contradiction_leaves_the_field_out():
    assert "has_parking" not in f("יש חניה בבניין. ללא חניה")


@pytest.mark.parametrize(
    "text",
    [
        "חניה ברחוב",
        "חניה בתשלום באזור",
        "חניה קלה באזור",
        "אפשרות לחניה",
        "בעיית חניה באזור",
        "חניה ציבורית",
    ],
)
def test_parking_that_is_not_a_statement_about_this_flat_is_left_out(text):
    assert "has_parking" not in f(text)


def test_pets():
    assert f("מותר בעלי חיים")["pets_allowed"] is True
    assert f("מתאים לבעלי חיים")["pets_allowed"] is True
    assert f("בעלי חיים - מותר")["pets_allowed"] is True
    assert f("בע\"ח אסור")["pets_allowed"] is False
    assert f("ללא בעלי חיים")["pets_allowed"] is False
    assert f("לא מתאים לבעלי חיים")["pets_allowed"] is False
    assert "pets_allowed" not in f("דירה ליד גן כלבים")


def test_renovated():
    assert f("דירה משופצת")["is_renovated"] is True
    assert f("שופצה לאחרונה")["is_renovated"] is True
    assert f("דורשת שיפוץ")["is_renovated"] is False
    assert "is_renovated" not in f("משופצת אבל דורשת שיפוץ קל")


def test_furniture():
    assert f("דירה מרוהטת")["furniture"] == "furnished"
    assert f("כולל ריהוט")["furniture"] == "furnished"
    assert f("לא מרוהטת")["furniture"] == "unfurnished"
    assert f("ללא ריהוט")["furniture"] == "unfurnished"
    assert "furniture" not in f("מרוהטת חלקית")
    assert "furniture" not in f("מטבח מרוהט ומאובזר")


def test_roommates():
    assert f("מתאים לשותפים")["is_roommate_friendly"] is True
    assert f("לא מתאים לשותפים")["is_roommate_friendly"] is False


def test_safe_room_and_shelter():
    assert f("יש ממד")["safe_room_type"] == "safe_room"
    assert f("מרחב מוגן דירתי")["safe_room_type"] == "safe_room"
    assert f("ללא ממ\"ד")["safe_room_type"] == "none"
    assert f("מקלט בבניין")["safe_room_type"] == "building_shelter"
    assert f("ללא ממד, מקלט בבניין")["safe_room_type"] == "building_shelter"
    assert f("ממד ומקלט בבניין")["safe_room_type"] == "safe_room"


def test_niqqud_and_quote_variants_are_normalized():
    assert f("ממ״ד")["safe_room_type"] == "safe_room"
    assert f("מְעֵלִית")["has_elevator"] is True


# --- property type ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("דירת גן 4 חדרים", "garden_apartment"),
        ("פנטהאוז מדהים", "penthouse"),
        ("דירת גג", "penthouse"),
        ("בית פרטי להשכרה", "private_house"),
        ("וילה מרווחת", "private_house"),
        ("בית דו משפחתי", "private_house"),
        ("סטודיו מעוצב", "studio"),
        ("יחידת דיור בגינה", "housing_unit"),
    ],
)
def test_property_type(text, expected):
    assert f(text)["property_type"] == expected


def test_property_type_is_left_out_when_ambiguous_or_just_a_landmark():
    assert "property_type" not in f("דירת גן ופנטהאוז")
    assert "property_type" not in f("דירה ליד וילה")
    assert "property_type" not in f("ברחוב הוילה 5")


# --- entry date ------------------------------------------------------------------------------------------------------


def test_entry_dates():
    assert f("כניסה 15/11/2026")["move_in_date"] == dt.date(2026, 11, 15)
    assert f("כניסה ב-1.12")["move_in_date"] == dt.date(2026, 12, 1)
    assert f("כניסה ל-15 בנובמבר")["move_in_date"] == dt.date(2026, 11, 15)
    assert f("תאריך כניסה 1.2.27")["move_in_date"] == dt.date(2027, 2, 1)


def test_an_entry_date_without_a_year_rolls_to_the_next_occurrence():
    assert f("כניסה 1.2")["move_in_date"] == dt.date(2027, 2, 1)


def test_entry_words():
    assert f("כניסה מיידית")["move_in_note"] == "מיידית"
    assert f("פנויה מיד")["move_in_note"] == "מיידית"
    assert f("כניסה גמישה")["move_in_note"] == "גמיש"


def test_a_date_that_has_passed_is_immediate_and_a_rooms_number_is_not_a_date():
    assert f("כניסה 1.9.2026") == {"move_in_note": "מיידית"}
    got = f("כניסה מיידית 3.5 חדרים")
    assert got == {"move_in_note": "מיידית"}
    assert "move_in_date" not in f("כניסה נפרדת 3.5 חדרים")
    assert "move_in_date" not in f("כניסה 31/2/2026")  # not a real date


# --- robustness ---------------------------------------------------------------------------------------------------------


def test_empty_and_garbage_never_raise():
    assert f("") == {} and f(None) == {} and f("   ") == {}
    assert f("!@#$ 12345 ???") == {}
    assert f("א" * 50000) == {}


# --- applying to a listing ------------------------------------------------------------------------------------------------


def _listing(**cols):
    base = dict(description=None, floor=None, floor_total=None, has_parking=None, has_elevator=None, has_balcony=None,
                pets_allowed=None, is_renovated=None, is_roommate_friendly=None, safe_room_type=None, furniture=None,
                property_type=None, move_in_date=None, move_in_note=None)
    base.update(cols)
    return SimpleNamespace(**base)


def test_only_missing_columns_are_filled_structured_values_win():
    listing = _listing(description="קומה 3 מתוך 5, ללא חניה, מעלית", floor=2, has_parking=True)
    updates = missing_updates(listing, today=TODAY)
    assert "floor" not in updates and "has_parking" not in updates  # the structured values stay
    assert updates["floor_total"] == 5 and updates["has_elevator"] is True


def test_apply_missing_sets_the_attributes_and_returns_what_it_set():
    listing = _listing(description="קומה 1 מתוך 3, מרפסת")
    set_now = apply_missing(listing, today=TODAY)
    assert set_now == {"floor": 1, "floor_total": 3, "has_balcony": True}
    assert listing.floor == 1 and listing.has_balcony is True
    assert apply_missing(listing, today=TODAY) == {}  # nothing left to fill


def test_a_move_in_note_is_not_offered_when_the_listing_has_a_date_or_a_note():
    assert "move_in_note" not in missing_updates(_listing(description="כניסה מיידית", move_in_date=dt.date(2026, 12, 1)), today=TODAY)
    assert "move_in_note" not in missing_updates(_listing(description="כניסה מיידית", move_in_note="גמיש"), today=TODAY)
    assert missing_updates(_listing(description="כניסה מיידית"), today=TODAY)["move_in_note"] == "מיידית"


def test_a_floor_from_the_text_never_contradicts_a_total_the_listing_has():
    listing = _listing(description="קומה 8", floor_total=4)
    assert "floor" not in missing_updates(listing, today=TODAY)


def test_several_different_floors_mean_no_floor_is_read():
    """Measured: one clear mention agrees with the structured floor ~90% of the time; two different floors do not."""
    assert "floor" not in f("קומה 2 וקומה 3 בבניין")
    assert f("קומה 2, בקומה 2")["floor"] == 2  # the same floor twice is one floor
    assert f("קומה 3 מתוך 5, קומה 4")["floor_total"] == 5  # the stated total survives, the ambiguous floor does not
    assert "floor" not in f("קומה 3 מתוך 5, קומה 4")
