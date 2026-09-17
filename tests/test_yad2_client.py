"""Unit tests for scraper/yad2_client.py's city-ID mapping tables (CITY_SLUG_TO_ID /
CITY_SLUG_TO_HEBREW_NAME) — added 2026-08-31 alongside extending that table from 3 to 24 cities.
Doesn't test fetch_search_results/_parse_cards (those need real network access, out of scope for
this dependency-light suite, same reasoning as normalize.py/matching.py's tests). No longer needs
a patchright stub — yad2_client.py switched to ZenRows' Fetch API (plain httpx) 2026-09-02, see
its module docstring."""
import json

import httpx
import pytest

import yad2_client
from dorin_common.cities import CITIES
from yad2_client import (
    BLOCKED_RESOURCE_TYPES,
    CITY_SLUG_TO_HEBREW_NAME,
    CITY_SLUG_TO_ID,
    MAP_API_URL,
    REGION_SLUGS,
    REGIONS_ON_MAP_API,
    ZENROWS_API_KEY_ENV_VAR,
    Yad2FetchError,
    Yad2MapFetchError,
    fetch_all_listings,
    fetch_listing_detail,
    fetch_listing_detail_via_web_unlocker,
    fetch_map_markers,
    fetch_region_pages,
    fetch_region_via_map_api,
    fetch_search_results,
)
from yad2_client import _marker_to_raw_item
from yad2_client import _extract_feed_records as extract_feed_records


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


# --- fetch_search_results (attempt 10: ZenRows Fetch API via httpx, not a real browser) ---
# Mocks httpx.get directly rather than hitting the network — no real ZenRows credits spent by
# running this suite, unlike an actual scraper run.

_CARD_HTML = (
    '<a class="itemLink" data-nagish="feed-item-layout-link" href="/item/abcd1234">'
    '<span data-testid="price">8,500 ₪</span>'
    '<span data-testid="street-name">ביאליק 10</span>'
    '<span data-testid="item-info-line-1st">דירה, מרכז העיר, רמת גן</span>'
    '<span data-testid="item-info-line-2nd">3 חדרים • קומה 2 • 75 מ"ר</span>'
    "</a>"
)


def test_missing_api_key_raises_without_any_http_call(monkeypatch):
    monkeypatch.delenv(ZENROWS_API_KEY_ENV_VAR, raising=False)
    with pytest.raises(Yad2FetchError, match=ZENROWS_API_KEY_ENV_VAR):
        list(fetch_search_results("tel-aviv"))


def test_unknown_city_slug_raises_without_any_http_call(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    with pytest.raises(Yad2FetchError, match="No Yad2 numeric city ID"):
        list(fetch_search_results("nonexistent-city"))


def test_successful_fetch_sends_the_right_params_and_parses_cards(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured = {}

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return httpx.Response(200, text=_CARD_HTML, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    items = list(fetch_search_results("tel-aviv"))

    assert len(items) == 1
    assert items[0]["id"] == "abcd1234"
    assert captured["url"] == "https://api.zenrows.com/v1/"
    assert captured["params"]["apikey"] == "fake-key"
    assert captured["params"]["url"] == "https://www.yad2.co.il/realestate/rent?city=5000"
    assert captured["params"]["js_render"] == "true"
    assert captured["params"]["premium_proxy"] == "true"
    assert captured["params"]["block_resources"] == BLOCKED_RESOURCE_TYPES


def test_zenrows_auth_error_body_raises_with_code_and_title(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    error_body = (
        '{"code":"AUTH004","detail":"This account has reached its usage limit.",'
        '"title":"Usage exceeded (AUTH004)"}'
    )

    def fake_get(url, params, timeout):
        return httpx.Response(200, text=error_body, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(Yad2FetchError, match="AUTH004"):
        list(fetch_search_results("tel-aviv"))


def test_non_200_status_raises_yad2_fetch_error(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        return httpx.Response(500, text="internal error", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(Yad2FetchError, match="http_status=500"):
        list(fetch_search_results("tel-aviv"))


def test_network_failure_fails_soft_as_yad2_fetch_error(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(Yad2FetchError):
        list(fetch_search_results("tel-aviv"))


def test_yad2_own_antibot_page_raises_a_clear_error_not_silent_zero_cards(monkeypatch):
    # A 200 response with none of ZenRows' own error JSON shape, but Yad2's actual bot-challenge
    # text — must NOT be mistaken for "genuinely 0 listings this city" (see _YAD2_ANTIBOT_MARKER's
    # module comment in yad2_client.py).
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    challenge_html = "<html><body>Are you for real, or a bot? Please verify.</body></html>"

    def fake_get(url, params, timeout):
        return httpx.Response(200, text=challenge_html, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(Yad2FetchError, match="bot-challenge"):
        list(fetch_search_results("tel-aviv"))


# --- fetch_all_listings (2026-09-03 — see its module-level comment in yad2_client.py) — 7
# broad-region requests (REGION_SLUGS, confirmed live against real Yad2 traffic) instead of the
# 42-city loop above. These tests pin down this function's own request-building behavior against
# mocked HTTP responses.


def test_region_slugs_has_seven_real_regions_no_duplicates():
    assert len(REGION_SLUGS) == 7
    assert len(set(REGION_SLUGS)) == 7


def test_fetch_all_listings_hits_every_region_url_once(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured_urls = []

    def fake_get(url, params, timeout):
        captured_urls.append(params["url"])
        return httpx.Response(200, text=_CARD_HTML, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    items = list(fetch_all_listings())

    assert len(items) == len(REGION_SLUGS)  # one card per region in this mocked HTML
    assert captured_urls == [
        f"https://www.yad2.co.il/realestate/rent/{region}" for region in REGION_SLUGS
    ]


def test_fetch_all_listings_accepts_a_custom_region_subset(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured_urls = []

    def fake_get(url, params, timeout):
        captured_urls.append(params["url"])
        return httpx.Response(200, text=_CARD_HTML, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    items = list(fetch_all_listings(regions=("tel-aviv-area",)))

    assert len(items) == 1
    assert captured_urls == ["https://www.yad2.co.il/realestate/rent/tel-aviv-area"]


# --- fetch_region_pages (2026-09-12 — see its module comment in yad2_client.py) — pages a
# region's feed past page 1 until caught up to already-known listings, instead of assuming one
# page always holds everything new. Real page=2 URL shape (`?page=2`, no other params) confirmed
# live by the owner clicking Yad2's own page-2 control.


def _card_html_for_id(item_id: str) -> str:
    return (
        f'<a class="itemLink" data-nagish="feed-item-layout-link" href="/item/{item_id}">'
        '<span data-testid="price">5,000 ₪</span>'
        '<span data-testid="street-name">רחוב כלשהו</span>'
        '<span data-testid="item-info-line-1st">דירה, תל אביב יפו</span>'
        '<span data-testid="item-info-line-2nd">2 חדרים</span>'
        "</a>"
    )


def test_fetch_region_pages_quiet_run_stops_after_one_page(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured_urls = []
    page1_html = _card_html_for_id("a") + _card_html_for_id("b")

    def fake_get(url, params, timeout):
        captured_urls.append(params["url"])
        return httpx.Response(200, text=page1_html, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    items = list(fetch_region_pages("tel-aviv-area", known_ids={"a", "b"}))

    # Every card on page 1 was already known -> stop immediately, exactly one request, matching
    # fetch_all_listings' own cost for a quiet run.
    assert captured_urls == ["https://www.yad2.co.il/realestate/rent/tel-aviv-area"]
    assert [item["id"] for item in items] == ["a", "b"]


def test_fetch_region_pages_pages_forward_past_new_listings(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured_urls = []
    pages = {
        "https://www.yad2.co.il/realestate/rent/tel-aviv-area": (
            _card_html_for_id("new-1") + _card_html_for_id("new-2")
        ),
        "https://www.yad2.co.il/realestate/rent/tel-aviv-area?page=2": (
            _card_html_for_id("known-1") + _card_html_for_id("known-2")
        ),
    }

    def fake_get(url, params, timeout):
        captured_urls.append(params["url"])
        return httpx.Response(200, text=pages[params["url"]], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    items = list(fetch_region_pages("tel-aviv-area", known_ids={"known-1", "known-2"}))

    # Page 1 has genuinely new ids -> must keep going; page 2 is all-known -> stop there.
    assert captured_urls == [
        "https://www.yad2.co.il/realestate/rent/tel-aviv-area",
        "https://www.yad2.co.il/realestate/rent/tel-aviv-area?page=2",
    ]
    assert [item["id"] for item in items] == ["new-1", "new-2", "known-1", "known-2"]


def test_fetch_region_pages_stops_when_a_page_runs_out_of_cards(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured_urls = []
    page1_html = _card_html_for_id("new-1")

    def fake_get(url, params, timeout):
        captured_urls.append(params["url"])
        # Real end of the feed reached on page 2 — an empty page, never all-known.
        text = page1_html if params["url"].endswith("tel-aviv-area") else ""
        return httpx.Response(200, text=text, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    items = list(fetch_region_pages("tel-aviv-area", known_ids=set()))

    assert len(captured_urls) == 2  # page 1 (new card), page 2 (empty -> stop, no page 3)
    assert [item["id"] for item in items] == ["new-1"]


def test_fetch_region_pages_hits_max_pages_and_logs_a_warning(monkeypatch, caplog):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    call_count = {"n": 0}

    def fake_get(url, params, timeout):
        call_count["n"] += 1
        # Every page has a genuinely new, never-known id — never catches up, never runs empty.
        return httpx.Response(
            200,
            text=_card_html_for_id(f"never-known-{call_count['n']}"),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    with caplog.at_level("WARNING"):
        items = list(fetch_region_pages("tel-aviv-area", known_ids=set(), max_pages=3))

    assert call_count["n"] == 3  # capped, not infinite
    assert len(items) == 3
    assert "hit max_pages=3" in caplog.text


def test_fetch_region_pages_page_urls_use_page_query_param_from_page_2_onward(monkeypatch):
    # Real shape confirmed live 2026-09-12 by the owner clicking Yad2's own page-2 control.
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured_urls = []

    def fake_get(url, params, timeout):
        captured_urls.append(params["url"])
        if len(captured_urls) >= 3:
            return httpx.Response(200, text="", request=httpx.Request("GET", url))
        return httpx.Response(
            200, text=_card_html_for_id(f"x{len(captured_urls)}"), request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    list(fetch_region_pages("jerusalem-area", known_ids=set()))

    assert captured_urls[0] == "https://www.yad2.co.il/realestate/rent/jerusalem-area"
    assert captured_urls[1] == "https://www.yad2.co.il/realestate/rent/jerusalem-area?page=2"


# --- fetch_listing_detail (2026-09-02) — reads the __NEXT_DATA__ blob embedded in a listing's
# own detail page. Shape below is trimmed from a real fetched listing (see
# .github/workflows/diagnose-listing-detail-page.yaml's confirmed output), not invented.

_NEXT_DATA_HTML = """<html><body><script id="__NEXT_DATA__" type="application/json">{
"props": {"pageProps": {"dehydratedState": {"queries": [{"state": {"data": {
  "token": "i8mec1k9",
  "price": 16000,
  "adType": "commercial",
  "additionalDetails": {
    "entranceDate": "2026-08-11T00:00:00",
    "roomsCount": 4,
    "property": {"id": 6, "text": "גג/ פנטהאוז", "textEng": "penthouse"},
    "propertyCondition": {"id": 3, "text": "במצב שמור"},
    "buildingTopFloor": 3
  },
  "inProperty": {
    "includeAirconditioner": true, "includeBalcony": true, "includeBoiler": true,
    "includeElevator": true, "includeParking": true, "includeSecurityRoom": false,
    "isHandicapped": true
  },
  "customer": {"name": "רונן אלדר", "agencyName": "promise"},
  "metaData": {
    "coverImage": "https://img.yad2.co.il/Pic/1.jpeg",
    "images": ["https://img.yad2.co.il/Pic/1.jpeg", "https://img.yad2.co.il/Pic/2.jpeg"],
    "description": "פנטהאוז ייחודי להשכרה בניות נווה המוזיאון 160 מ\\"ר"
  }
}}}]}}}}
</script></body></html>"""


def test_fetch_listing_detail_missing_api_key_returns_none_without_http_call(monkeypatch):
    monkeypatch.delenv(ZENROWS_API_KEY_ENV_VAR, raising=False)

    def fake_get(*args, **kwargs):
        raise AssertionError("should not make an HTTP call without an API key")

    monkeypatch.setattr(httpx, "get", fake_get)
    assert fetch_listing_detail("https://www.yad2.co.il/realestate/item/abc123") is None


def test_fetch_listing_detail_parses_the_real_confirmed_shape(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured = {}

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        return httpx.Response(200, text=_NEXT_DATA_HTML, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    data = fetch_listing_detail("https://www.yad2.co.il/realestate/item/i8mec1k9")

    assert data is not None
    assert data["token"] == "i8mec1k9"
    assert data["price"] == 16000
    assert data["inProperty"]["includeElevator"] is True
    assert data["metaData"]["images"] == [
        "https://img.yad2.co.il/Pic/1.jpeg",
        "https://img.yad2.co.il/Pic/2.jpeg",
    ]
    assert captured["params"]["apikey"] == "fake-key"
    assert captured["params"]["url"] == "https://www.yad2.co.il/realestate/item/i8mec1k9"


def test_fetch_listing_detail_non_200_returns_none(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        return httpx.Response(500, text="internal error", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert fetch_listing_detail("https://www.yad2.co.il/realestate/item/abc123") is None


def test_fetch_listing_detail_network_failure_returns_none_not_raise(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)
    assert fetch_listing_detail("https://www.yad2.co.il/realestate/item/abc123") is None


def test_fetch_listing_detail_missing_next_data_returns_none(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        return httpx.Response(
            200, text="<html><body>no next data here</body></html>",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    assert fetch_listing_detail("https://www.yad2.co.il/realestate/item/abc123") is None


def test_fetch_listing_detail_malformed_json_returns_none_not_raise(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    bad_html = '<html><body><script id="__NEXT_DATA__" type="application/json">{not valid json</script></body></html>'

    def fake_get(url, params, timeout):
        return httpx.Response(200, text=bad_html, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert fetch_listing_detail("https://www.yad2.co.il/realestate/item/abc123") is None


def test_fetch_listing_detail_no_query_carries_a_token_returns_none(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    html = (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        '{"props": {"pageProps": {"dehydratedState": {"queries": [{"state": {"data": {"no_token_here": true}}}]}}}}'
        "</script></body></html>"
    )

    def fake_get(url, params, timeout):
        return httpx.Response(200, text=html, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert fetch_listing_detail("https://www.yad2.co.il/realestate/item/abc123") is None


# --- fetch_listing_detail_via_web_unlocker (2026-09-17) — the real, working replacement for the
# Bright Data DCA collector, routed through Web Unlocker (see module docstring's 2026-09-17 entry
# and _fetch_direct's own docstring). Same __NEXT_DATA__ shape/parsing as fetch_listing_detail
# above (shares _parse_next_data_ad_record), just a different transport — _NEXT_DATA_HTML is reused
# for that reason.


def test_fetch_listing_detail_via_web_unlocker_parses_the_real_confirmed_shape(monkeypatch):
    captured = {}

    def fake_fetch_direct(url):
        captured["url"] = url
        return _NEXT_DATA_HTML

    monkeypatch.setattr(yad2_client, "_fetch_direct", fake_fetch_direct)

    data = fetch_listing_detail_via_web_unlocker("https://www.yad2.co.il/realestate/item/i8mec1k9")

    assert data is not None
    assert data["token"] == "i8mec1k9"
    assert data["price"] == 16000
    assert data["metaData"]["description"].startswith("פנטהאוז")
    assert captured["url"] == "https://www.yad2.co.il/realestate/item/i8mec1k9"


def test_fetch_listing_detail_via_web_unlocker_fetch_failure_returns_none(monkeypatch):
    monkeypatch.setattr(yad2_client, "_fetch_direct", lambda url: None)
    assert fetch_listing_detail_via_web_unlocker(
        "https://www.yad2.co.il/realestate/item/abc123"
    ) is None


def test_fetch_listing_detail_via_web_unlocker_missing_next_data_returns_none(monkeypatch):
    monkeypatch.setattr(
        yad2_client, "_fetch_direct", lambda url: "<html><body>no next data here</body></html>"
    )
    assert fetch_listing_detail_via_web_unlocker(
        "https://www.yad2.co.il/realestate/item/abc123"
    ) is None


def test_fetch_listing_detail_via_web_unlocker_malformed_json_returns_none_not_raise(monkeypatch):
    bad_html = (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        "{not valid json</script></body></html>"
    )
    monkeypatch.setattr(yad2_client, "_fetch_direct", lambda url: bad_html)
    assert fetch_listing_detail_via_web_unlocker(
        "https://www.yad2.co.il/realestate/item/abc123"
    ) is None


# --- _extract_feed_records / _parse_cards feed-record merge (2026-09-02) ---
# The search-results page turns out to ALSO embed a __NEXT_DATA__ blob covering every listing on
# the page (not just one, as the detail page does) - real photos, tags, and broker category, for
# free, in the same request already being paid for. Shape below is trimmed from a real fetched
# Jerusalem search page (see .github/workflows/diagnose-search-page-feed-shape.yaml's confirmed
# output), not invented.

_FEED_NEXT_DATA_JSON = """{
"props": {"pageProps": {"dehydratedState": {"queries": [
  {"queryKey": ["realestate-rent-feed", {}], "state": {"data": {
    "private": [{
      "token": "abcd1234",
      "adType": "private",
      "price": 7800,
      "additionalDetails": {"property": {"text": "דירה"}, "roomsCount": 4},
      "metaData": {
        "coverImage": "https://img.yad2.co.il/Pic/1.jpeg",
        "images": ["https://img.yad2.co.il/Pic/1.jpeg", "https://img.yad2.co.il/Pic/2.jpeg"]
      },
      "tags": [{"name": "חניה", "id": 1003}, {"name": "ממ\\"ד", "id": 1009}]
    }],
    "agency": [{
      "token": "xyz789",
      "adType": "commercial",
      "price": 8000,
      "additionalDetails": {"property": {"text": "דירת גן"}, "roomsCount": 3},
      "metaData": {"images": ["https://img.yad2.co.il/Pic/3.jpeg"]},
      "customer": {"agencyName": "רחלי נכסים"},
      "tags": [{"name": "2 מרפסות", "id": 1212}]
    }]
  }}}
]}}}}"""

_CARD_HTML_WITH_FEED = (
    f'<script id="__NEXT_DATA__" type="application/json">{_FEED_NEXT_DATA_JSON}</script>'
    '<a class="itemLink" data-nagish="feed-item-layout-link" href="/item/abcd1234">'
    '<span data-testid="price">7,800 ₪</span>'
    '<span data-testid="street-name">רחוב כלשהו</span>'
    '<span data-testid="item-info-line-1st">דירה, שכונה, ירושלים</span>'
    '<span data-testid="item-info-line-2nd">4 חדרים • קומה 3 • 102 מ"ר</span>'
    "</a>"
    '<a class="itemLink" data-nagish="feed-item-layout-link" href="/item/xyz789">'
    '<span data-testid="price">8,000 ₪</span>'
    '<span data-testid="street-name">רחוב אחר</span>'
    '<span data-testid="item-info-line-1st">דירת גן, שכונה, ירושלים</span>'
    '<span data-testid="item-info-line-2nd">3 חדרים • קומה 0 • 90 מ"ר</span>'
    "</a>"
    '<a class="itemLink" data-nagish="feed-item-layout-link" href="/item/no-feed-match">'
    '<span data-testid="price">5,000 ₪</span>'
    '<span data-testid="street-name">עוד רחוב</span>'
    '<span data-testid="item-info-line-1st">דירה, שכונה, ירושלים</span>'
    '<span data-testid="item-info-line-2nd">2 חדרים • קומה 1 • 60 מ"ר</span>'
    "</a>"
)


def test_extract_feed_records_maps_token_to_record_with_broker_flag():
    records = extract_feed_records(_CARD_HTML_WITH_FEED)
    assert set(records) == {"abcd1234", "xyz789"}
    assert records["abcd1234"]["_is_broker_listing"] is False
    assert records["xyz789"]["_is_broker_listing"] is True


def test_extract_feed_records_returns_empty_dict_when_no_next_data():
    assert extract_feed_records(_CARD_HTML) == {}


def test_parse_cards_attaches_feed_record_only_when_a_match_exists(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured_items = {}

    def fake_get(url, params, timeout):
        return httpx.Response(200, text=_CARD_HTML_WITH_FEED, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    items = list(fetch_search_results("tel-aviv"))
    for item in items:
        captured_items[item["id"]] = item

    assert set(captured_items) == {"abcd1234", "xyz789", "no-feed-match"}
    assert "_feed_record" in captured_items["abcd1234"]
    assert "_feed_record" in captured_items["xyz789"]
    assert "_feed_record" not in captured_items["no-feed-match"]


# --- fetch_map_markers / _marker_to_raw_item (2026-09-13 — see module docstring in
# yad2_client.py) — Yad2's own map-markers API, reached via Bright Data's Web Unlocker instead of
# ZenRows (which refuses this endpoint outright). Marker shape below is the REAL confirmed record
# (see .github/workflows/diagnose-yad2-bright-data-cost.yaml's actual output), not invented.

_REAL_MARKER = {
    "address": {
        "region": {"text": "תל אביב והסביבה", "id": 3},
        "city": {"text": "חולון"},
        "area": {"text": "אזור חולון ובת ים"},
        "neighborhood": {"text": "ג'סי כהן"},
        "street": {"text": "הערבה"},
        "house": {"number": 14, "floor": 4},
        "coords": {"lon": 34.763276, "lat": 32.012712},
    },
    "subcategoryId": 2,
    "categoryId": 2,
    "adType": "private",
    "price": 3800,
    "token": "3zsxuu6d",
    "additionalDetails": {
        "property": {"text": "דירה"},
        "roomsCount": 2.5,
        "squareMeter": 65,
        "propertyCondition": {"id": 2},
    },
    "metaData": {
        "coverImage": "https://img.yad2.co.il/1.jpeg",
        "images": ["https://img.yad2.co.il/1.jpeg", "https://img.yad2.co.il/2.jpeg"],
    },
    "tags": [],
    "orderId": 57321396,
    "priority": 1,
}


def test_marker_to_raw_item_extracts_the_real_confirmed_shape():
    item = _marker_to_raw_item(_REAL_MARKER)
    assert item == {
        "id": "3zsxuu6d",
        "url": "https://www.yad2.co.il/item/3zsxuu6d",
        "price": 3800,
        "rooms": 2.5,
        "floor": 4,
        "square_meters": 65,
        "street": "הערבה 14",
        "neighborhood": "ג'סי כהן",
        "city": "חולון",
        "images": ["https://img.yad2.co.il/1.jpeg", "https://img.yad2.co.il/2.jpeg"],
    }


def test_marker_to_raw_item_missing_token_returns_none():
    marker = {k: v for k, v in _REAL_MARKER.items() if k != "token"}
    assert _marker_to_raw_item(marker) is None


def test_marker_to_raw_item_missing_house_number_keeps_street_name_only():
    marker = {**_REAL_MARKER, "address": {**_REAL_MARKER["address"], "house": {"floor": 4}}}
    item = _marker_to_raw_item(marker)
    assert item["street"] == "הערבה"
    assert item["floor"] == 4


def test_marker_to_raw_item_no_images_omits_the_key():
    marker = {**_REAL_MARKER, "metaData": {}}
    item = _marker_to_raw_item(marker)
    assert "images" not in item


def test_fetch_map_markers_direct_request_failure_raises(monkeypatch):
    # _fetch_direct itself has no config to be "missing" (it's a plain, un-proxied GET — see its
    # own docstring for why, 2026-09-15) — its only failure modes are network errors/non-200,
    # both collapsed to a None return, exercised here directly rather than hitting a real network.
    monkeypatch.setattr(yad2_client, "_fetch_direct", lambda url: None)
    with pytest.raises(Yad2MapFetchError, match="Direct .un-proxied. request failed"):
        list(fetch_map_markers("31.9,34.7,32.1,34.8", area=1, region=3))


def test_fetch_map_markers_builds_the_real_confirmed_url_and_parses_markers(monkeypatch):
    captured = {}

    def fake_fetch(url):
        captured["url"] = url
        return json.dumps({"status": "OK", "data": {"markers": [_REAL_MARKER]}})

    monkeypatch.setattr(yad2_client, "_fetch_direct", fake_fetch)

    items = list(
        fetch_map_markers("31.987679,34.732856,32.146966,34.857736", area=1, region=3, zoom=11)
    )

    assert captured["url"] == (
        f"{MAP_API_URL}?area=1&region=3&bBox=31.987679,34.732856,32.146966,34.857736&zoom=11"
    )
    assert len(items) == 1
    assert items[0]["id"] == "3zsxuu6d"


def test_fetch_map_markers_invalid_json_raises(monkeypatch):
    monkeypatch.setattr(yad2_client, "_fetch_direct", lambda url: "not json")

    with pytest.raises(Yad2MapFetchError, match="wasn't valid JSON"):
        list(fetch_map_markers("bbox", area=1, region=3))


def test_fetch_map_markers_missing_markers_list_raises(monkeypatch):
    monkeypatch.setattr(yad2_client, "_fetch_direct", lambda url: '{"data": {}}')

    with pytest.raises(Yad2MapFetchError, match="no usable 'data.markers' list"):
        list(fetch_map_markers("bbox", area=1, region=3))


def test_fetch_map_markers_skips_non_dict_and_tokenless_entries(monkeypatch):
    body = '{"data": {"markers": [123, {"no": "token"}]}}'
    monkeypatch.setattr(yad2_client, "_fetch_direct", lambda url: body)

    assert list(fetch_map_markers("bbox", area=1, region=3)) == []


# --- fetch_map_markers: optional area / alternate host (2026-09-14 — see _build_map_url's own
# docstring for the two real findings this covers: a district-level request can omit `area`
# entirely, and Yad2 routes at least one region through a different domain entirely) -----------


def test_fetch_map_markers_omits_area_param_entirely_when_area_is_none(monkeypatch):
    captured = {}

    def fake_fetch(url):
        captured["url"] = url
        return json.dumps({"status": "OK", "data": {"markers": [_REAL_MARKER]}})

    monkeypatch.setattr(yad2_client, "_fetch_direct", fake_fetch)

    list(fetch_map_markers("29.7,33.1,33.7,37.9", region=4, zoom=7))

    assert captured["url"] == f"{MAP_API_URL}?region=4&bBox=29.7,33.1,33.7,37.9&zoom=7"
    assert "area=" not in captured["url"]


def test_fetch_map_markers_uses_the_given_host_instead_of_the_default(monkeypatch):
    captured = {}

    def fake_fetch(url):
        captured["url"] = url
        return json.dumps({"status": "OK", "data": {"markers": [_REAL_MARKER]}})

    monkeypatch.setattr(yad2_client, "_fetch_direct", fake_fetch)

    list(fetch_map_markers("29.7,33.1,33.7,37.9", region=4, zoom=7, host="gw.yad-il.co.il"))

    assert captured["url"] == (
        "https://gw.yad-il.co.il/realestate-feed/rent/map?region=4&bBox=29.7,33.1,33.7,37.9&zoom=7"
    )


# --- REGIONS_ON_MAP_API / fetch_region_via_map_api (2026-09-15 — ALL 7 REGION_SLUGS now covered;
# see fetch_region_via_map_api's own module comment in yad2_client.py for the full reasoning,
# including why every fetch below goes through _fetch_direct, not a proxy) ----------------------


def test_regions_on_map_api_is_a_subset_of_region_slugs():
    # Every region routed to the map API must still be one of the real REGION_SLUGS scraper/main.py
    # iterates over — a typo'd key here would silently mean that region is never scraped at all.
    assert set(REGIONS_ON_MAP_API) <= set(REGION_SLUGS)


def test_all_seven_regions_are_on_the_map_api():
    # 2026-09-15: the migration off ZenRows/fetch_region_pages for Yad2 is now COMPLETE — every
    # REGION_SLUGS entry has its own confirmed-real, live-captured district-level bbox/region.
    assert set(REGIONS_ON_MAP_API) == set(REGION_SLUGS)


# (region_slug, expected_url) — one entry per REGIONS_ON_MAP_API config, each the owner's own real,
# live-captured request (never guessed/interpolated — see REGIONS_ON_MAP_API's own comment).
_EXPECTED_REGION_URLS = [
    (
        "tel-aviv-area",
        f"{MAP_API_URL}?area=1&region=3&bBox=31.987679,34.732856,32.146966,34.857736&zoom=11",
    ),
    (
        "partnership/east",
        "https://gw.yad-il.co.il/realestate-feed/rent/map?region=4&"
        "bBox=29.778653,33.142100,33.787281,37.954214&zoom=7",
    ),
    (
        "center-and-sharon",
        f"{MAP_API_URL}?region=1&bBox=31.808989,34.507037,32.418309,35.222485&zoom=10",
    ),
    (
        "jerusalem-area",
        f"{MAP_API_URL}?region=6&bBox=31.549448,34.818058,31.938335,35.272844&zoom=10",
    ),
    (
        "south",
        f"{MAP_API_URL}?region=2&bBox=29.490631,33.476480,31.904124,36.268220&zoom=8",
    ),
    (
        "coastal-north",
        f"{MAP_API_URL}?region=5&bBox=32.342601,34.560052,33.137625,35.500061&zoom=9",
    ),
    (
        "north-and-valleys",
        f"{MAP_API_URL}?region=7&bBox=32.387068,34.885247,33.335914,36.008669&zoom=9",
    ),
]


@pytest.mark.parametrize("region_slug,expected_url", _EXPECTED_REGION_URLS)
def test_fetch_region_via_map_api_uses_each_regions_confirmed_real_params(
    monkeypatch, region_slug, expected_url
):
    captured = {}

    def fake_fetch(url):
        captured["url"] = url
        return json.dumps({"status": "OK", "data": {"markers": [_REAL_MARKER]}})

    monkeypatch.setattr(yad2_client, "_fetch_direct", fake_fetch)

    items = list(fetch_region_via_map_api(region_slug))

    assert captured["url"] == expected_url
    assert len(items) == 1


def test_expected_region_urls_covers_every_real_region_slug():
    # A region added to REGIONS_ON_MAP_API without a matching entry in _EXPECTED_REGION_URLS above
    # would silently skip the per-region param check above — this catches that gap.
    assert {slug for slug, _ in _EXPECTED_REGION_URLS} == set(REGIONS_ON_MAP_API)


def test_fetch_region_via_map_api_unknown_region_raises_key_error():
    with pytest.raises(KeyError):
        list(fetch_region_via_map_api("nonexistent-region"))


def test_fetch_region_via_map_api_propagates_yad2_map_fetch_error(monkeypatch):
    monkeypatch.setattr(yad2_client, "_fetch_direct", lambda url: "not json")

    with pytest.raises(Yad2MapFetchError, match="wasn't valid JSON"):
        list(fetch_region_via_map_api("tel-aviv-area"))


def test_every_region_maps_to_a_non_empty_list_of_configs():
    # REGIONS_ON_MAP_API values are lists (kept that way for a future region that might genuinely
    # need multiple sub-requests — see the module comment) — a bare dict here would be a real bug.
    for region, configs in REGIONS_ON_MAP_API.items():
        assert isinstance(configs, list), f"{region!r}'s value must be a list, not {type(configs)}"
        assert configs, f"{region!r} has an empty config list — nothing would ever be fetched"


def test_fetch_region_via_map_api_unions_multiple_sub_areas_for_one_region(monkeypatch):
    # No REGIONS_ON_MAP_API entry currently needs more than one sub-request (see the module
    # comment), but fetch_region_via_map_api's own union-over-the-list behavior is still real
    # behavior worth covering directly, with a fake multi-entry region.
    fake_configs = {
        "south": [
            {"bbox": "bbox-beer-sheva", "area": 10, "region": 2, "zoom": 12},
            {"bbox": "bbox-ashdod", "area": 20, "region": 2, "zoom": 12},
        ],
    }
    monkeypatch.setattr(yad2_client, "REGIONS_ON_MAP_API", fake_configs)

    requested_urls = []

    def fake_fetch(url):
        requested_urls.append(url)
        token = "beer-sheva" if "beer-sheva" in url else "ashdod"
        marker = {**_REAL_MARKER, "token": token}
        return json.dumps({"status": "OK", "data": {"markers": [marker]}})

    monkeypatch.setattr(yad2_client, "_fetch_direct", fake_fetch)

    items = list(fetch_region_via_map_api("south"))

    assert len(requested_urls) == 2  # both sub-areas were actually fetched, not just the first
    assert {item["id"] for item in items} == {"beer-sheva", "ashdod"}  # union of both
