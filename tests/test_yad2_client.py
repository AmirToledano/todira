"""Unit tests for scraper/yad2_client.py's city-ID mapping tables (CITY_SLUG_TO_ID /
CITY_SLUG_TO_HEBREW_NAME) — added 2026-08-31 alongside extending that table from 3 to 24 cities.
Doesn't test fetch_search_results/_parse_cards (those need patchright + real network access, out
of scope for this dependency-light suite, same reasoning as normalize.py/matching.py's tests)."""
import sys
import types

# yad2_client.py imports patchright at module level (a real browser-automation dependency,
# deliberately NOT in requirements-test.txt — see that file's comment). Stub it out so the
# module-level import succeeds; nothing in these tests touches the stubbed names.
if "patchright" not in sys.modules:
    patchright_stub = types.ModuleType("patchright")
    sync_api_stub = types.ModuleType("patchright.sync_api")
    sync_api_stub.TimeoutError = TimeoutError
    sync_api_stub.sync_playwright = None
    patchright_stub.sync_api = sync_api_stub
    sys.modules["patchright"] = patchright_stub
    sys.modules["patchright.sync_api"] = sync_api_stub

from dorin_common.cities import CITIES
from yad2_client import (
    _MAX_PROXIED_REQUESTS_PER_CITY,
    CITY_SLUG_TO_HEBREW_NAME,
    CITY_SLUG_TO_ID,
    _should_allow_proxied_request,
)


def test_every_slug_has_a_hebrew_name():
    assert set(CITY_SLUG_TO_ID) == set(CITY_SLUG_TO_HEBREW_NAME)


def test_every_mapped_hebrew_name_is_a_real_bot_city():
    # Catches a typo'd Hebrew name that would otherwise silently never match anything in
    # dorin_common/cities.py's CITIES list (the strings a user actually picks in /filter).
    for slug, hebrew_name in CITY_SLUG_TO_HEBREW_NAME.items():
        assert (
            hebrew_name in CITIES
        ), f"{slug!r} -> {hebrew_name!r} is not in dorin_common/cities.py CITIES"


def test_city_ids_are_unique():
    ids = list(CITY_SLUG_TO_ID.values())
    assert len(ids) == len(set(ids)), "duplicate Yad2 city ID — likely a copy-paste mistake"


def test_city_ids_are_numeric_strings():
    for slug, city_id in CITY_SLUG_TO_ID.items():
        assert city_id.isdigit(), f"{slug!r} has a non-numeric Yad2 city id: {city_id!r}"


def test_original_three_ids_unchanged():
    # These three predate this update and are already live in production (SCRAPE_CITIES) — guard
    # against accidentally changing a value that's already working in the deployed scraper.
    assert CITY_SLUG_TO_ID["tel-aviv"] == "5000"
    assert CITY_SLUG_TO_ID["ramat-gan"] == "8600"
    assert CITY_SLUG_TO_ID["givatayim"] == "6300"


def test_image_media_font_always_blocked_regardless_of_count():
    assert _should_allow_proxied_request("image", 0) is False
    assert _should_allow_proxied_request("media", 0) is False
    assert _should_allow_proxied_request("font", 0) is False


def test_other_resource_types_allowed_until_the_cap():
    for resource_type in ("document", "script", "stylesheet", "xhr", "fetch", "other"):
        assert _should_allow_proxied_request(resource_type, 0) is True
        assert _should_allow_proxied_request(resource_type, _MAX_PROXIED_REQUESTS_PER_CITY - 1) is True


def test_cap_is_a_hard_ceiling_not_just_a_default():
    assert _should_allow_proxied_request("script", _MAX_PROXIED_REQUESTS_PER_CITY) is False
    assert _should_allow_proxied_request("xhr", _MAX_PROXIED_REQUESTS_PER_CITY + 1000) is False


def test_worst_case_credits_per_city_is_bounded():
    # The whole point: a deterministic ceiling regardless of what a future Yad2 page redesign
    # throws at it, not a hope that today's known-safe resource types stay safe forever.
    max_billed_requests_per_city = _MAX_PROXIED_REQUESTS_PER_CITY
    assert max_billed_requests_per_city == 30
