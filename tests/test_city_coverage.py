"""2026-10-19 (owner: "go over every town, city and moshav in the country and make sure it is all there"): every place
in the official list is findable, and a city typed freely in an ad (a neighbourhood, a typo, English or Russian, a place
word in front, a whole address) is stored under the place's own name - cities.resolve_messy_city."""
from __future__ import annotations

import pytest

from todira_common.cities import (
    BEDOUIN_TRIBES,
    LOCALITY_SET,
    SECOND_NAMES,
    canonicalize_city,
    find_matches,
    resolve_locality,
)


def test_every_bedouin_tribe_of_the_official_list_is_a_locality():
    assert len(BEDOUIN_TRIBES) == 25
    assert all(name in LOCALITY_SET for name in BEDOUIN_TRIBES)


def test_a_second_name_finds_the_place():
    assert all(name in LOCALITY_SET for name in SECOND_NAMES.values())
    assert resolve_locality("זרעית") == "כפר רוזנואלד"
    assert resolve_locality("גוש חלב") == "ג'ש"
    assert find_matches("זרעית")[0] == "כפר רוזנואלד"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("קרית חיים", "חיפה"),
        ("גילה", "ירושלים"),
        ("יפו", "תל אביב יפו"),
        ("עיר ימים", "נתניה"),
        ("Хайфа", "חיפה"),
        ("tel aviv", "תל אביב יפו"),
        ("Karne Shomron", "קרני שומרון"),
        ("קיבוץ מצובה", "מצובה"),
        ("מושב צופר בערבה", "צופר"),
        ("נתניה ישראל בורגנסקי 4", "נתניה"),
        ("רחוב אחוזה, רעננה", "רעננה"),
        ("בניברק", "בני ברק"),
        ("קרית אונוון", "קריית אונו"),
        ("תל אביבב", "תל אביב יפו"),
        ("מודעין", "מודיעין מכבים רעות"),
        ("כוכב יאיר", "כוכב יאיר / צור יגאל"),
        ("פקיעין החדשה", "פקיעין חדשה"),
        ("ירוחם8888", "ירוחם"),
        ("קרית אונו .מ14 לא בשבת   0524476825", "קריית אונו"),
    ],
)
def test_a_messy_city_is_stored_under_the_place_it_means(raw, expected):
    assert canonicalize_city(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "חכמת רחוב",  # an agent's name, not the village רחוב
        "שני ליבנה",  # a person, not the moshav שני
        "שכונת רמות ים",  # not Jerusalem's רמות
        "אזור תעשייה אכזיב מילואות",  # not the town אזור
        "רמלה לוד",  # two cities: never a guess
        "דירת גן",
        "Big Land Realestate",
    ],
)
def test_text_that_is_no_clear_place_is_left_as_it_was(raw):
    assert canonicalize_city(raw) == raw
