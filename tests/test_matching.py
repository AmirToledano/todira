"""Unit tests for common/dorin_common/matching.py - the core listing/filter matching logic.

Pure I/O-free logic, so plain SimpleNamespace stand-ins are enough (no DB, no SQLAlchemy needed)
- matching.evaluate() only ever accesses attributes, exactly as the module's own docstring says
it's designed for.
"""
import datetime as dt
from types import SimpleNamespace

import pytest

from dorin_common.matching import evaluate


def make_filter(**overrides):
    defaults = dict(
        deal_type="rent",
        property_types=[],
        cities=[],
        neighborhoods_include=[],
        neighborhoods_exclude=[],
        streets_include=[],
        streets_exclude=[],
        require_price=False,
        price_min=None,
        price_max=None,
        rooms_min=None,
        rooms_max=None,
        ground_floor_only=False,
        floor_min=None,
        floor_max=None,
        min_area_sqm=None,
        keywords=[],
        move_in_earliest=None,
        move_in_latest=None,
        require_parking=False,
        require_elevator=False,
        require_balcony=False,
        require_pets_allowed=False,
        require_renovated=False,
        require_roommate_friendly=False,
        require_has_photos=False,
        safe_room_pref="any",
        furniture_pref="any",
        no_brokers=False,
        flexible_match=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_listing(**overrides):
    defaults = dict(
        deal_type="rent",
        property_type="apartment",
        city="תל אביב",
        neighborhood="לב העיר",
        street="דיזנגוף",
        price=5000,
        rooms=3,
        floor=2,
        size_sqm=70,
        description="דירה משופצת עם מרפסת גדולה",
        move_in_date=None,
        has_parking=True,
        has_elevator=True,
        has_balcony=True,
        pets_allowed=True,
        is_renovated=True,
        is_roommate_friendly=False,
        image_urls=["https://example.com/1.jpg"],
        safe_room_type="safe_room",
        furniture="furnished",
        is_broker_listing=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---- baseline: an unconstrained filter against a "normal" listing always matches ----


def test_empty_filter_matches_any_listing():
    result = evaluate(make_filter(), make_listing())
    assert result.matched is True
    assert result.failed_hard_filters == []
    assert result.failed_mandatory_criteria == []


# ---- hard filters ----


def test_deal_type_mismatch_fails():
    result = evaluate(make_filter(deal_type="rent"), make_listing(deal_type="sale"))
    assert result.matched is False
    assert "deal_type" in result.failed_hard_filters


def test_property_type_not_in_allowed_list_fails():
    f = make_filter(property_types=["studio", "duplex"])
    result = evaluate(f, make_listing(property_type="apartment"))
    assert "property_type" in result.failed_hard_filters


def test_property_type_in_allowed_list_passes():
    f = make_filter(property_types=["apartment", "duplex"])
    result = evaluate(f, make_listing(property_type="apartment"))
    assert result.matched is True


def test_unknown_property_type_gets_benefit_of_the_doubt():
    # Regression test for a real production bug (2026-09-02): scraper/normalize.py never
    # actually populates NormalizedListing.property_type, so every real listing has
    # property_type=None. A filter with any property_types checked (even, as in the real report,
    # all seven - not an unusual "select everything" UI action) used to fail EVERY listing
    # outright, since `None not in [...]` is always true - city/price/rooms notwithstanding.
    f = make_filter(property_types=["apartment", "studio"])
    result = evaluate(f, make_listing(property_type=None))
    assert "property_type" not in result.failed_hard_filters
    assert result.matched is True


def test_city_not_in_filter_fails():
    f = make_filter(cities=["חיפה", "ירושלים"])
    result = evaluate(f, make_listing(city="תל אביב"))
    assert "city" in result.failed_hard_filters


def test_city_in_filter_passes():
    f = make_filter(cities=["תל אביב"])
    result = evaluate(f, make_listing(city="תל אביב"))
    assert result.matched is True


def test_neighborhood_include_requires_city_neighborhood_pair():
    f = make_filter(neighborhoods_include=["תל אביב:פלורנטין"])
    result = evaluate(f, make_listing(city="תל אביב", neighborhood="לב העיר"))
    assert "neighborhood_include" in result.failed_hard_filters

    result = evaluate(f, make_listing(city="תל אביב", neighborhood="פלורנטין"))
    assert result.matched is True


def test_neighborhood_exclude_rejects_matching_pair():
    f = make_filter(neighborhoods_exclude=["תל אביב:פלורנטין"])
    result = evaluate(f, make_listing(city="תל אביב", neighborhood="פלורנטין"))
    assert "neighborhood_exclude" in result.failed_hard_filters

    result = evaluate(f, make_listing(city="תל אביב", neighborhood="לב העיר"))
    assert result.matched is True


def test_street_include_is_case_and_whitespace_insensitive():
    f = make_filter(streets_include=[" Dizengoff "])
    result = evaluate(f, make_listing(street="dizengoff"))
    assert result.matched is True

    result = evaluate(f, make_listing(street="Allenby"))
    assert "street_include" in result.failed_hard_filters


def test_street_exclude_rejects_matching_street():
    f = make_filter(streets_exclude=["דיזנגוף"])
    result = evaluate(f, make_listing(street="דיזנגוף"))
    assert "street_exclude" in result.failed_hard_filters


def test_missing_price_passes_when_price_not_required():
    f = make_filter(require_price=False, price_min=1000, price_max=2000)
    result = evaluate(f, make_listing(price=None))
    assert result.matched is True


def test_missing_price_fails_when_price_required():
    f = make_filter(require_price=True)
    result = evaluate(f, make_listing(price=None))
    assert "price_required_but_missing" in result.failed_hard_filters


def test_price_outside_range_fails():
    f = make_filter(price_min=4000, price_max=6000)
    result = evaluate(f, make_listing(price=7000))
    assert "price_range" in result.failed_hard_filters


def test_price_inside_range_passes():
    f = make_filter(price_min=4000, price_max=6000)
    result = evaluate(f, make_listing(price=5000))
    assert result.matched is True


def test_rooms_missing_fails_when_range_set():
    f = make_filter(rooms_min=2, rooms_max=4)
    result = evaluate(f, make_listing(rooms=None))
    assert "rooms_range" in result.failed_hard_filters


def test_rooms_outside_range_fails():
    f = make_filter(rooms_min=4, rooms_max=5)
    result = evaluate(f, make_listing(rooms=2))
    assert "rooms_range" in result.failed_hard_filters


def test_ground_floor_only_rejects_nonzero_floor():
    f = make_filter(ground_floor_only=True)
    result = evaluate(f, make_listing(floor=1))
    assert "ground_floor_only" in result.failed_hard_filters


def test_ground_floor_only_accepts_floor_zero_ignoring_floor_range():
    # ground_floor_only takes precedence over floor_min/floor_max (elif branch)
    f = make_filter(ground_floor_only=True, floor_min=5, floor_max=10)
    result = evaluate(f, make_listing(floor=0))
    assert result.matched is True


def test_floor_range_missing_floor_fails():
    f = make_filter(floor_min=1, floor_max=3)
    result = evaluate(f, make_listing(floor=None))
    assert "floor_range" in result.failed_hard_filters


def test_floor_range_outside_fails():
    f = make_filter(floor_min=1, floor_max=3)
    result = evaluate(f, make_listing(floor=10))
    assert "floor_range" in result.failed_hard_filters


def test_min_area_missing_size_fails():
    f = make_filter(min_area_sqm=50)
    result = evaluate(f, make_listing(size_sqm=None))
    assert "min_area_sqm" in result.failed_hard_filters


def test_min_area_below_minimum_fails():
    f = make_filter(min_area_sqm=100)
    result = evaluate(f, make_listing(size_sqm=70))
    assert "min_area_sqm" in result.failed_hard_filters


def test_keywords_match_any_not_all():
    f = make_filter(keywords=["מרפסת", "חניה פרטית"])
    # description only contains one of the two keywords - "match any" should still pass
    result = evaluate(f, make_listing(description="דירה עם מרפסת יפה"))
    assert result.matched is True


def test_keywords_none_present_fails():
    f = make_filter(keywords=["ממ״ד", "חניה"])
    result = evaluate(f, make_listing(description="דירה משופצת ושקטה"))
    assert "keywords" in result.failed_hard_filters


def test_listing_with_no_move_in_date_always_passes_date_filter():
    f = make_filter(
        move_in_earliest=dt.date(2026, 1, 1), move_in_latest=dt.date(2026, 3, 1)
    )
    result = evaluate(f, make_listing(move_in_date=None))
    assert result.matched is True


def test_move_in_date_too_early_fails():
    f = make_filter(move_in_earliest=dt.date(2026, 6, 1))
    result = evaluate(f, make_listing(move_in_date=dt.date(2026, 1, 1)))
    assert "move_in_too_early" in result.failed_hard_filters


def test_move_in_date_too_late_fails():
    f = make_filter(move_in_latest=dt.date(2026, 3, 1))
    result = evaluate(f, make_listing(move_in_date=dt.date(2026, 6, 1)))
    assert "move_in_too_late" in result.failed_hard_filters


def test_move_in_date_within_range_passes():
    f = make_filter(
        move_in_earliest=dt.date(2026, 1, 1), move_in_latest=dt.date(2026, 12, 31)
    )
    result = evaluate(f, make_listing(move_in_date=dt.date(2026, 6, 1)))
    assert result.matched is True


def test_multiple_hard_filter_failures_all_reported():
    f = make_filter(deal_type="rent", cities=["חיפה"], price_min=10000)
    result = evaluate(f, make_listing(deal_type="sale", city="תל אביב", price=5000))
    assert result.matched is False
    assert set(result.failed_hard_filters) == {"deal_type", "city", "price_range"}


def test_hard_filter_failure_short_circuits_mandatory_criteria_check():
    # even though this listing would also fail a mandatory criterion (no parking), a hard filter
    # failure means mandatory criteria are never evaluated at all
    f = make_filter(cities=["חיפה"], require_parking=True)
    result = evaluate(f, make_listing(city="תל אביב", has_parking=False))
    assert result.matched is False
    assert result.failed_hard_filters == ["city"]
    assert result.failed_mandatory_criteria == []


# ---- mandatory criteria (boolean amenity pairs) ----


@pytest.mark.parametrize(
    "filter_attr,listing_attr,label",
    [
        ("require_parking", "has_parking", "parking"),
        ("require_elevator", "has_elevator", "elevator"),
        ("require_balcony", "has_balcony", "balcony"),
        ("require_pets_allowed", "pets_allowed", "pets_allowed"),
        ("require_renovated", "is_renovated", "renovated"),
        ("require_roommate_friendly", "is_roommate_friendly", "roommate_friendly"),
    ],
)
def test_boolean_amenity_required_and_true_passes(filter_attr, listing_attr, label):
    f = make_filter(**{filter_attr: True})
    l = make_listing(**{listing_attr: True})
    result = evaluate(f, l)
    assert result.matched is True


@pytest.mark.parametrize(
    "filter_attr,listing_attr,label",
    [
        ("require_parking", "has_parking", "parking"),
        ("require_elevator", "has_elevator", "elevator"),
        ("require_balcony", "has_balcony", "balcony"),
        ("require_pets_allowed", "pets_allowed", "pets_allowed"),
        ("require_renovated", "is_renovated", "renovated"),
        ("require_roommate_friendly", "is_roommate_friendly", "roommate_friendly"),
    ],
)
def test_boolean_amenity_required_and_false_fails(filter_attr, listing_attr, label):
    f = make_filter(**{filter_attr: True})
    l = make_listing(**{listing_attr: False})
    result = evaluate(f, l)
    assert result.matched is False
    assert label in result.failed_mandatory_criteria


@pytest.mark.parametrize(
    "filter_attr,listing_attr,label",
    [
        ("require_parking", "has_parking", "parking"),
        ("require_elevator", "has_elevator", "elevator"),
        ("require_balcony", "has_balcony", "balcony"),
        ("require_pets_allowed", "pets_allowed", "pets_allowed"),
        ("require_renovated", "is_renovated", "renovated"),
        ("require_roommate_friendly", "is_roommate_friendly", "roommate_friendly"),
    ],
)
def test_boolean_amenity_required_and_unknown_gets_benefit_of_the_doubt(
    filter_attr, listing_attr, label
):
    # Regression test for a real production bug (2026-09-02, same shape as property_type):
    # scraper/yad2_client.py's card parser never extracts any amenity data at all (it only lives
    # on a listing's own detail page), so these fields are None for every real listing - a filter
    # with any of these require_* toggles on used to fail every single listing, always.
    f = make_filter(**{filter_attr: True})
    l = make_listing(**{listing_attr: None})
    result = evaluate(f, l)
    assert result.matched is True
    assert label not in result.failed_mandatory_criteria


def test_require_has_photos_never_enforced_since_photos_are_never_scraped():
    # image_urls is always [] for every real listing today (see matching.py's own comment) - an
    # empty list can't be told apart from "genuinely no photos", so this can't reject on it.
    f = make_filter(require_has_photos=True)
    result = evaluate(f, make_listing(image_urls=[]))
    assert result.matched is True
    assert "has_photos" not in result.failed_mandatory_criteria


def test_require_has_photos_passes_when_images_present():
    f = make_filter(require_has_photos=True)
    result = evaluate(f, make_listing(image_urls=["https://example.com/1.jpg"]))
    assert result.matched is True


def test_safe_room_only_rejects_non_safe_room():
    f = make_filter(safe_room_pref="safe_room_only")
    result = evaluate(f, make_listing(safe_room_type="building_shelter"))
    assert "safe_room_only" in result.failed_mandatory_criteria


def test_safe_room_only_accepts_safe_room():
    f = make_filter(safe_room_pref="safe_room_only")
    result = evaluate(f, make_listing(safe_room_type="safe_room"))
    assert result.matched is True


def test_safe_room_or_shelter_accepts_either():
    f = make_filter(safe_room_pref="safe_room_or_shelter")
    assert evaluate(f, make_listing(safe_room_type="safe_room")).matched is True
    assert evaluate(f, make_listing(safe_room_type="building_shelter")).matched is True


def test_safe_room_or_shelter_unknown_gets_benefit_of_the_doubt():
    # safe_room_type is never scraped today (same root cause as the amenity fields above) - an
    # unknown value must not zero out every listing for any filter that sets safe_room_pref.
    f = make_filter(safe_room_pref="safe_room_or_shelter")
    result = evaluate(f, make_listing(safe_room_type=None))
    assert result.matched is True
    assert "safe_room_or_shelter" not in result.failed_mandatory_criteria


def test_furniture_pref_mismatch_fails():
    f = make_filter(furniture_pref="furnished")
    result = evaluate(f, make_listing(furniture="unfurnished"))
    assert "furniture_pref" in result.failed_mandatory_criteria


def test_furniture_pref_match_passes():
    f = make_filter(furniture_pref="furnished")
    result = evaluate(f, make_listing(furniture="furnished"))
    assert result.matched is True


def test_furniture_pref_unknown_gets_benefit_of_the_doubt():
    # furniture is never scraped today (same root cause as the amenity fields above).
    f = make_filter(furniture_pref="furnished")
    result = evaluate(f, make_listing(furniture=None))
    assert result.matched is True
    assert "furniture_pref" not in result.failed_mandatory_criteria


def test_furniture_pref_any_ignores_listing_value():
    f = make_filter(furniture_pref="any")
    result = evaluate(f, make_listing(furniture=None))
    assert result.matched is True


def test_no_brokers_rejects_known_broker_listing():
    f = make_filter(no_brokers=True)
    result = evaluate(f, make_listing(is_broker_listing=True))
    assert "no_brokers" in result.failed_mandatory_criteria


def test_no_brokers_gives_benefit_of_doubt_to_unknown_status():
    # unlike the boolean amenity pairs above, an unknown (None) broker status is NOT treated as
    # a failure - only an explicit True fails, per the module's own comment
    f = make_filter(no_brokers=True)
    result = evaluate(f, make_listing(is_broker_listing=None))
    assert result.matched is True


def test_no_brokers_passes_known_non_broker_listing():
    f = make_filter(no_brokers=True)
    result = evaluate(f, make_listing(is_broker_listing=False))
    assert result.matched is True


# ---- flexible_match tolerance ----


def test_flexible_match_false_rejects_any_single_mandatory_failure():
    f = make_filter(flexible_match=False, require_parking=True, require_elevator=True)
    result = evaluate(f, make_listing(has_parking=True, has_elevator=False))
    assert result.matched is False
    assert result.failed_mandatory_criteria == ["elevator"]


def test_flexible_match_true_tolerates_exactly_one_mandatory_failure():
    f = make_filter(flexible_match=True, require_parking=True, require_elevator=True)
    result = evaluate(f, make_listing(has_parking=True, has_elevator=False))
    assert result.matched is True
    assert result.failed_mandatory_criteria == ["elevator"]


def test_flexible_match_true_still_rejects_two_mandatory_failures():
    f = make_filter(
        flexible_match=True,
        require_parking=True,
        require_elevator=True,
        require_balcony=True,
    )
    result = evaluate(
        f, make_listing(has_parking=True, has_elevator=False, has_balcony=False)
    )
    assert result.matched is False
    assert set(result.failed_mandatory_criteria) == {"elevator", "balcony"}
