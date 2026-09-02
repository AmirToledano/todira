"""Unit tests for scraper/normalize.py - maps a raw Yad2 item dict into a NormalizedListing.

The module's own docstring promises it "never raises" - a malformed/missing field should always
degrade to None rather than aborting a scrape run over one bad item. That defensive contract is
exactly what's worth locking down with tests, since scraper/main.py relies on it silently.
"""
from dorin_common.enums import DealType

from normalize import normalize


def test_missing_id_returns_none():
    assert normalize({"price": 5000}) is None


def test_minimal_item_with_only_id_still_normalizes():
    result = normalize({"id": "123"})
    assert result is not None
    assert result.source == "yad2"
    assert result.external_id == "123"
    assert result.deal_type == DealType.RENT
    # no explicit url - falls back to a constructed one
    assert result.url == "https://www.yad2.co.il/item/123"


def test_id_can_come_from_alternate_key_names():
    assert normalize({"adNumber": 456}).external_id == "456"
    assert normalize({"order_id": 789}).external_id == "789"


def test_explicit_url_is_used_over_fallback():
    result = normalize({"id": "1", "url": "https://example.com/real-listing"})
    assert result.url == "https://example.com/real-listing"


def test_url_alternate_key_name():
    result = normalize({"id": "1", "link": "https://example.com/via-link-key"})
    assert result.url == "https://example.com/via-link-key"


def test_deal_type_param_overrides_default():
    result = normalize({"id": "1"}, deal_type=DealType.SALE)
    assert result.deal_type == DealType.SALE


def test_numeric_fields_parsed_including_alternate_keys():
    result = normalize(
        {
            "id": "1",
            "price": "5000",
            "roomsCount": "3.5",
            "floor": "2",
            "buildingFloors": "8",
            "squareMeter": "70",
        }
    )
    assert result.price == 5000
    assert result.rooms == 3.5
    assert result.floor == 2
    assert result.floor_total == 8
    assert result.size_sqm == 70


def test_primary_key_name_preferred_over_alternate():
    result = normalize({"id": "1", "rooms": 2, "roomsCount": 99})
    assert result.rooms == 2


def test_malformed_numeric_value_degrades_to_none_not_exception():
    result = normalize({"id": "1", "price": "not-a-number", "rooms": {"weird": "shape"}})
    assert result is not None
    assert result.price is None
    assert result.rooms is None


def test_location_fields_and_alternate_keys():
    result = normalize({"id": "1", "cityText": "תל אביב", "neighborhoodText": "פלורנטין", "streetText": "הרכבת"})
    assert result.city == "תל אביב"
    assert result.neighborhood == "פלורנטין"
    assert result.street == "הרכבת"


def test_city_spelling_is_canonicalized():
    # confirmed live 2026-09-02: Yad2's own page text for Kiryat Motzkin is "קרית מוצקין" (1 yud),
    # not cities.py's bundled "קריית מוצקין" (2 yuds) - normalize() must fix this up so a saved
    # filter (which only ever stores the bundled spelling) can actually match the listing.
    result = normalize({"id": "1", "city": "קרית מוצקין"})
    assert result.city == "קריית מוצקין"


def test_boolean_fields_pass_through_real_booleans():
    result = normalize({"id": "1", "parking": True, "elevator": False})
    assert result.has_parking is True
    assert result.has_elevator is False


def test_boolean_fields_do_not_guess_cast_non_bool_values():
    # explicitly documented behavior: a truthy string/int is left as unknown (None), never
    # coerced, since we can't be sure what a source's non-bool value actually means
    result = normalize({"id": "1", "parking": "yes", "elevator": 1})
    assert result.has_parking is None
    assert result.has_elevator is None


def test_description_alternate_key():
    result = normalize({"id": "1", "text": "דירה מהממת עם נוף לים"})
    assert result.description == "דירה מהממת עם נוף לים"


def test_image_urls_default_to_empty_list():
    result = normalize({"id": "1"})
    assert result.image_urls == []


def test_image_urls_passed_through():
    urls = ["https://example.com/a.jpg", "https://example.com/b.jpg"]
    result = normalize({"id": "1", "images": urls})
    assert result.image_urls == urls


def test_valid_posted_at_is_parsed():
    result = normalize({"id": "1", "dateAdded": "2026-08-30T12:00:00Z"})
    assert result.posted_at is not None
    assert result.posted_at.year == 2026
    assert result.posted_at.month == 8
    assert result.posted_at.day == 30


def test_invalid_posted_at_degrades_to_none_not_exception():
    result = normalize({"id": "1", "dateAdded": "not-a-real-date"})
    assert result is not None
    assert result.posted_at is None


def test_raw_payload_preserves_original_dict():
    raw = {"id": "1", "price": 5000, "some_unmapped_field": "kept anyway"}
    result = normalize(raw)
    assert result.raw_payload == raw


def test_invalid_deal_type_fails_validation_and_returns_none_not_exception():
    # NormalizedListing's deal_type is a Literal["sublet","sale","rent"] - an out-of-set value
    # should hit normalize()'s own try/except around construction and degrade to None, exactly
    # like every other malformed-field case, rather than propagating a pydantic ValidationError
    # up into the scraper's main loop and aborting the whole run.
    result = normalize({"id": "1"}, deal_type="not_a_real_deal_type")
    assert result is None


# --- enrich_from_detail (2026-09-02) — fills fields only a listing's own detail page carries.
# Shape below is trimmed from a real fetched listing (see
# .github/workflows/diagnose-listing-detail-page.yaml's confirmed output), not invented.
from normalize import enrich_from_detail  # noqa: E402

_REAL_DETAIL = {
    "token": "i8mec1k9",
    "price": 16000,
    "adType": "commercial",
    "additionalDetails": {
        "entranceDate": "2026-08-11T00:00:00",
        "roomsCount": 4,
        "property": {"id": 6, "text": "גג/ פנטהאוז", "textEng": "penthouse"},
        "propertyCondition": {"id": 3, "text": "במצב שמור"},
        "buildingTopFloor": 3,
    },
    "inProperty": {
        "includeAirconditioner": True,
        "includeBalcony": True,
        "includeBoiler": True,
        "includeElevator": True,
        "includeParking": True,
        "includeSecurityRoom": False,
        "isHandicapped": True,
    },
    "customer": {"name": "רונן אלדר", "agencyName": "promise"},
    "metaData": {
        "coverImage": "https://img.yad2.co.il/Pic/1.jpeg",
        "images": ["https://img.yad2.co.il/Pic/1.jpeg", "https://img.yad2.co.il/Pic/2.jpeg"],
        "description": 'פנטהאוז ייחודי להשכרה בניות נווה המוזיאון 160 מ"ר',
    },
}


def _base_item():
    return normalize({"id": "1", "price": 16000})


def test_enrich_fills_property_type_from_confirmed_mapping():
    result = enrich_from_detail(_base_item(), _REAL_DETAIL)
    assert result.property_type == "penthouse"


def test_enrich_fills_amenity_booleans():
    result = enrich_from_detail(_base_item(), _REAL_DETAIL)
    assert result.has_parking is True
    assert result.has_elevator is True
    assert result.has_balcony is True


def test_enrich_maps_security_room_to_safe_room_type():
    result = enrich_from_detail(_base_item(), _REAL_DETAIL)
    assert result.safe_room_type == "none"  # includeSecurityRoom was False in this sample

    with_shelter = dict(_REAL_DETAIL)
    with_shelter["inProperty"] = {**_REAL_DETAIL["inProperty"], "includeSecurityRoom": True}
    result2 = enrich_from_detail(_base_item(), with_shelter)
    assert result2.safe_room_type == "safe_room"


def test_enrich_fills_floor_total_and_move_in_date():
    result = enrich_from_detail(_base_item(), _REAL_DETAIL)
    assert result.floor_total == 3
    assert result.move_in_date is not None
    assert result.move_in_date.isoformat() == "2026-08-11"


def test_enrich_fills_description_and_real_images():
    result = enrich_from_detail(_base_item(), _REAL_DETAIL)
    assert result.description.startswith("פנטהאוז ייחודי")
    assert result.image_urls == [
        "https://img.yad2.co.il/Pic/1.jpeg",
        "https://img.yad2.co.il/Pic/2.jpeg",
    ]


def test_enrich_marks_broker_listing_when_agency_name_present():
    result = enrich_from_detail(_base_item(), _REAL_DETAIL)
    assert result.is_broker_listing is True


def test_enrich_does_not_guess_broker_status_when_agency_name_absent():
    # absence of an agency name is NOT confident evidence of "private listing" - must stay
    # untouched (None), same benefit-of-the-doubt policy as everywhere else
    no_agency = dict(_REAL_DETAIL)
    no_agency["customer"] = {"name": "פרטי כלשהו"}
    result = enrich_from_detail(_base_item(), no_agency)
    assert result.is_broker_listing is None


def test_enrich_unmapped_property_type_stays_none_not_guessed():
    unmapped = dict(_REAL_DETAIL)
    unmapped["additionalDetails"] = {
        **_REAL_DETAIL["additionalDetails"],
        "property": {"id": 99, "text": "משהו חדש", "textEng": "some_never_seen_value"},
    }
    result = enrich_from_detail(_base_item(), unmapped)
    assert result.property_type is None


def test_enrich_does_not_touch_fields_already_set_from_the_search_card():
    item = normalize({"id": "1", "price": 5000, "rooms": 2, "city": "תל אביב"})
    result = enrich_from_detail(item, _REAL_DETAIL)
    # price/rooms/city come from the search card and are left alone by enrichment
    assert result.price == 5000
    assert result.rooms == 2
    assert result.city == "תל אביב"


def test_enrich_missing_or_malformed_sections_degrade_gracefully_not_raise():
    result = enrich_from_detail(_base_item(), {})
    assert result.property_type is None
    assert result.has_parking is None
    assert result.image_urls == []

    weird = {"additionalDetails": "not a dict", "inProperty": None, "metaData": [1, 2], "customer": 5}
    result2 = enrich_from_detail(_base_item(), weird)
    assert result2.property_type is None
    assert result2.image_urls == []
