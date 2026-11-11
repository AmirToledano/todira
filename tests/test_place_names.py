"""2026-11-11 (owner: "people type a thousand variations, קרית יובל is really קריית היובל")."""
from types import SimpleNamespace

from todira_common import matching, place_names
from todira_common.place_names import name_key, neighbourhood_keys, street_key, suggest


def test_spellings_of_one_neighbourhood_compare_equal():
    assert name_key("קרית יובל") == name_key("קריית היובל")
    assert name_key("שכונת נווה שאנן") == name_key("נוה שאנן")
    assert name_key("ג'סי כהן") == name_key("גסי כהן")
    assert name_key("רחביה") != name_key("רמות")


def test_spellings_of_one_street_compare_equal():
    assert street_key("רח' הרצל 12") == street_key("הרצל")
    assert street_key("שד' רוטשילד") == street_key("שדרות רוטשילד")
    assert street_key("רחוב 12") == "12"  # a number alone stays a name


def test_a_combined_neighbourhood_gives_each_name_in_it():
    keys = neighbourhood_keys("חומת שמואל, הר חומה")
    assert name_key("הר חומה") in keys and name_key("חומת שמואל") in keys
    assert name_key("לב העיר") in neighbourhood_keys("מחנה יהודה - לב העיר")
    assert neighbourhood_keys(None) == frozenset({""})


def test_suggestions_put_the_same_name_first_then_names_that_start_with_it_then_close_spellings():
    names = ["קריית היובל", "קריית מנחם", "בקעה", "רחביה"]
    assert suggest("קרית יובל", names)[0] == "קריית היובל"
    assert suggest("רחבי", names) == ["רחביה"]
    assert suggest("בקאה", names) == ["בקעה"]
    assert suggest("", names) == []
    assert suggest("הרצל", ["הרצל", "הרצליה", "הרב קוק"], key=street_key)[:2] == ["הרצל", "הרצליה"]


def test_the_official_streets_list_is_bundled():
    streets = place_names.official_streets("תל אביב יפו")
    assert len(streets) > 1000 and "דיזנגוף" in streets


def _listing(**kw):
    values = {
        "id": 1, "deal_type": "rent", "property_type": "apartment", "city": "ירושלים", "neighborhood": None,
        "street": None, "latitude": None, "longitude": None, "price": 5000, "rooms": 3, "floor": 1, "size_sqm": 70,
        "move_in_date": None, "safe_room_type": None, "furniture": None, "is_broker_listing": False,
        "description": "", "has_parking": None, "has_elevator": None, "has_balcony": None, "pets_allowed": None,
        "is_renovated": None, "is_roommate_friendly": None, "first_seen_at": None,
    }
    values.update(kw)
    return SimpleNamespace(**values)


def _filter(**kw):
    from todira_common.schemas import FilterData

    values = FilterData().model_dump()
    values.update(cities=["ירושלים"], require_price=False, map_region_kind=None)
    values.update(kw)
    return SimpleNamespace(**values)


def test_matching_finds_a_neighbourhood_in_any_spelling_and_inside_a_combined_name():
    f = _filter(neighborhoods_include=["ירושלים:קריית היובל", "ירושלים:הר חומה"])
    assert matching.evaluate(f, _listing(neighborhood="קרית יובל")).matched
    assert matching.evaluate(f, _listing(neighborhood="חומת שמואל, הר חומה")).matched
    assert not matching.evaluate(f, _listing(neighborhood="רחביה")).matched
    assert not matching.evaluate(f, _listing(neighborhood=None)).matched
    f.include_missing_details = True
    assert matching.evaluate(f, _listing(neighborhood=None)).matched


def test_matching_finds_a_street_written_with_a_house_number():
    f = _filter(streets_include=["ירושלים:שד הרצל"])
    assert matching.evaluate(f, _listing(street="שדרות הרצל 104")).matched
    assert not matching.evaluate(f, _listing(street="יפו 10")).matched
