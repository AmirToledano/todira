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
