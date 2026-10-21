"""2026-10-21 (owner: "add a huge list of words a person might use"): the bot understands the many ways people write
what they want, not only the kind of deal (see test_deal_words.py)."""
from __future__ import annotations

import pytest

from todira_common import search_text

FIELDS = {
    ("require_balcony", True): ["עם מרפסת", "מרפסת שמש", "with a balcony", "с балконом", "مع شرفة"],
    ("require_parking", True): ["חנייה בבניין", "מקום חניה", "חניון", "parking", "garage", "парковка", "موقف سيارات"],
    ("require_elevator", True): ["מעלית", "with elevator", "lift", "лифт", "مصعد"],
    ("safe_room_pref", "safe_room_only"): ['ממ"ד', "ממד", "חדר מוגן", "מרחב מוגן", "safe room", "мамад"],
    ("require_renovated", True): ["משופצת", "לאחר שיפוץ", "שופצה לגמרי", "renovated", "с ремонтом", "евроремонт"],
    ("furniture_pref", "furnished"): ["מרוהטת", "כולל ריהוט", "עם רהיטים", "furnished", "с мебелью", "مفروشة"],
    ("furniture_pref", "unfurnished"): ["לא מרוהטת", "בלי רהיטים", "דירה ריקה", "unfurnished", "без мебели"],
    ("require_pets_allowed", True): ["יש לי כלבה", "עם חיות", 'בע"ח', "חתולים", "pets", "a dog", "с собакой", "حيوانات"],
    ("no_brokers", True): ["ללא תיווך", "בלי עמלה", "מהבעלים", "מיד ראשונה", "no broker", "by owner",
                           "без посредников", "от собственника"],
    ("ground_floor_only", True): ["קומת קרקע", "ground floor"],
    ("require_roommate_friendly", True): ["לשותפים", "שותפה", "roommates", "flatmates"],
}
PROPERTY_TYPES = {
    "garden_apartment": ["דירת גן", "garden apartment"],
    "penthouse": ["פנטהאוס", "דירת גג", "penthouse", "пентхаус"],
    "housing_unit": ["יחידת דיור", "יחידה נפרדת", "יח\"ד"],
    "private_house": ["בית פרטי", "קוטג'", "צמוד קרקע", "דו משפחתי", "house", "villa", "частный дом", "коттедж"],
}
KEYWORDS = {
    "מחסן": ["עם מחסן", "storage"],
    "גינה": ["חצר", "דשא", "garden", "yard"],
    "מיזוג": ["מזגנים", "מיזוג מרכזי", "air conditioning", "кондиционер"],
    "נגישה": ["נגישה לנכים", "wheelchair", "accessible"],
}


@pytest.mark.parametrize("field, value, text", [(f, v, t) for (f, v), texts in FIELDS.items() for t in texts])
def test_feature_words(field, value, text):
    assert search_text.parse(text)["fields"].get(field) == value


@pytest.mark.parametrize("kind, text", [(k, t) for k, texts in PROPERTY_TYPES.items() for t in texts])
def test_property_type_words(kind, text):
    assert kind in search_text.parse(text)["fields"].get("property_types", [])


@pytest.mark.parametrize("label, text", [(k, t) for k, texts in KEYWORDS.items() for t in texts])
def test_keyword_words(label, text):
    assert search_text.parse(text)["keywords"] == [label]


@pytest.mark.parametrize("text", ["לא צריך מעלית", "לא חשוב לי מעלית", "without elevator", "не нужен лифт"])
def test_negated_feature_is_not_required(text):
    assert "require_elevator" not in search_text.parse(text)["fields"]


@pytest.mark.parametrize("text", ["רוצה לחיות בחיפה", "חדר כביסה משותף", "location in the center", "גג משותף"])
def test_everyday_words_are_not_features(text):
    found = search_text.parse(text)
    assert not found["fields"] and not found["keywords"]


@pytest.mark.parametrize("text, rooms", [
    ("שבעה חדרים", (7, 7.5)), ("3 חד", (3, 3.5)), ("4 комнаты", (4, 4.5)), ("3 غرف", (3, 3.5)),
    ("חדר אחד", (1, 1.5)), ("студия", (1, 1.5)),
])
def test_room_words(text, rooms):
    assert search_text._rooms(text) == rooms


@pytest.mark.parametrize("text, price_max", [
    ("גג 6500", 6500), ("מקס 7000", 7000), ("לכל היותר 5,500", 5500), ("לא מעל 8000", 8000),
    ("до 6000", 6000), ("5000 שקלים", 5000), ("4500 shekels", 4500),
])
def test_price_words(text, price_max):
    assert search_text._prices(text) == (None, price_max)


@pytest.mark.parametrize("text, deal", [
    ("לכמה חודשים בתל אביב", "sublet"), ("short term", "sublet"), ("краткосрочная", "sublet"),
    ("מחיר למשתכן", "sale"),
])
def test_more_deal_words(text, deal):
    assert search_text._deal_type(text) == deal
