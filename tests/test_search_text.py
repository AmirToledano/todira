"""todira_common/search_text.py: the free, offline reading of a free-text apartment search (2026-10-13)."""
from __future__ import annotations

import pytest

from todira_common.search_text import match_city_reply, parse, suggest_cities


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "היי, אני מחפש דירה בתל אביב עם 3+ חדרים. התקציב שלי עד 8,500₪ ואשמח שתהיה גם מרפסת.",
            {"deal_type": None, "cities": ["תל אביב יפו"], "rooms_min": 3, "rooms_max": None, "price_max": 8500,
             "fields": {"require_balcony": True}, "labels": ["מרפסת"]},
        ),
        ("אני רוצה דירת 5 חדרים בירושלים", {"cities": ["ירושלים"], "rooms_min": 5, "rooms_max": 5.5}),
        ("מחפש שכירות בחיפה, עד 4500", {"deal_type": "rent", "cities": ["חיפה"], "price_max": 4500}),
        (
            "רוצה לקנות דירה ברמת גן או גבעתיים עד 2.5 מיליון, 4-5 חדרים, חניה ומעלית",
            {"deal_type": "sale", "cities": ["רמת גן", "גבעתיים"], "rooms_min": 4, "rooms_max": 5,
             "price_max": 2_500_000, "fields": {"require_parking": True, "require_elevator": True}},
        ),
        ('סאבלט בת"א', {"deal_type": "sublet", "cities": ["תל אביב יפו"]}),
        ('שכירות בב"ש 3 חדרים בין 3000 ל-4000 ש"ח', {"cities": ["באר שבע"], "price_min": 3000, "price_max": 4000}),
        ('להשכרה בפתח תקוה, ממ"ד, כניסה ב-2026', {"cities": ["פתח תקווה"], "price_max": None,
                                                    "fields": {"safe_room_pref": "safe_room_only"}}),
        ("looking to rent in tel aviv 2 rooms up to 7000", {"deal_type": "rent", "cities": ["תל אביב יפו"], "price_max": 7000}),
        ("שלושה וחצי חדרים בראשון לציון לשכירות", {"rooms_min": 3.5, "rooms_max": 3.5, "cities": ["ראשון לציון"]}),
        ("סטודיו להשכרה ביפו", {"rooms_min": 1, "rooms_max": 1.5, "cities": ["תל אביב יפו"]}),
        ("מחפשת דירה בקרית מוצקין עד 4 אלף", {"cities": ["קריית מוצקין"], "price_max": 4000}),
        ("דירת 3 חדרים 80 מטר", {"rooms_min": 3, "price_max": None}),
    ],
)
def test_parse_reads_common_search_messages(text, expected):
    result = parse(text)
    for key, value in expected.items():
        assert result[key] == value, (key, result)


def test_city_names_that_are_everyday_words_are_not_picked_out_of_a_sentence():
    assert parse("דירה באזור המרכז במגדל עם נוף")["cities"] == []


def test_both_rent_and_buy_is_ambiguous_and_left_for_the_bot_to_ask():
    assert parse("לא יודע אם לשכור או לקנות בחיפה")["deal_type"] is None


def test_a_reply_to_which_city_accepts_a_bare_name_and_suggests_for_typos():
    assert match_city_reply("מגדל") == ["מגדל"]
    assert match_city_reply('ראשל"צ') == ["ראשון לציון"]
    assert suggest_cities("רמת גם")[0] == "רמת גן"


@pytest.mark.parametrize(
    "text,fields,keywords",
    [
        ("דירת גן בחיפה עם חניה ומחסן, בלי מעלית, ללא תיווך",
         {"require_parking": True, "no_brokers": True, "property_types": ["garden_apartment"]}, ["מחסן"]),
        ('פנטהאוז בהרצליה לקנות, לפחות 120 מ"ר, קומה 3 ומעלה',
         {"property_types": ["penthouse"], "min_area_sqm": 120, "floor_min": 3}, []),
        ("שכירות לשותפים בבאר שבע, מרוהטת, עם מזגן, כלב קטן",
         {"furniture_pref": "furnished", "require_pets_allowed": True, "require_roommate_friendly": True}, ["מיזוג"]),
        ('בית פרטי או קוטג\' במודיעין, לא מרוהט, ממ"ד חובה',
         {"safe_room_pref": "safe_room_only", "furniture_pref": "unfurnished", "property_types": ["private_house"]}, []),
    ],
)
def test_features_become_the_same_switches_the_filter_buttons_set(text, fields, keywords):
    result = parse(text)
    assert result["fields"] == fields and result["keywords"] == keywords


def test_a_feature_said_with_without_is_not_required():
    assert "require_elevator" not in parse("בלי מעלית ולא צריך חניה")["fields"]
    assert "require_parking" not in parse("בלי מעלית ולא צריך חניה")["fields"]
