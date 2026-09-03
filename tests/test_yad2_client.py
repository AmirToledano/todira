"""Unit tests for scraper/yad2_client.py's city-ID mapping tables (CITY_SLUG_TO_ID /
CITY_SLUG_TO_HEBREW_NAME) — added 2026-08-31 alongside extending that table from 3 to 24 cities.
Doesn't test fetch_search_results/_parse_cards (those need real network access, out of scope for
this dependency-light suite, same reasoning as normalize.py/matching.py's tests). No longer needs
a patchright stub — yad2_client.py switched to ZenRows' Fetch API (plain httpx) 2026-09-02, see
its module docstring."""
import httpx
import pytest

from dorin_common.cities import CITIES
from yad2_client import (
    BLOCKED_RESOURCE_TYPES,
    CITY_SLUG_TO_HEBREW_NAME,
    CITY_SLUG_TO_ID,
    ZENROWS_API_KEY_ENV_VAR,
    Yad2FetchError,
    fetch_all_listings,
    fetch_listing_detail,
    fetch_search_results,
)
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


# --- fetch_all_listings (2026-09-03, EXPERIMENTAL — see its module-level comment in
# yad2_client.py) — nationwide, unfiltered, paginated sweep instead of the per-city loop above.
# These tests only pin down this function's own request-building/pagination-stopping behavior
# against mocked HTTP responses; they say nothing about whether Yad2's real pagination works the
# way this function assumes (unconfirmed, see that comment).


def test_fetch_all_listings_first_request_has_no_city_or_page_param(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured_urls = []

    def fake_get(url, params, timeout):
        captured_urls.append(params["url"])
        return httpx.Response(200, text="<html></html>", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    list(fetch_all_listings(max_pages=3))

    assert captured_urls == ["https://www.yad2.co.il/realestate/rent"]


def test_fetch_all_listings_stops_as_soon_as_a_page_has_zero_cards(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured_urls = []

    def fake_get(url, params, timeout):
        captured_urls.append(params["url"])
        # Page 1 has one real card, page 2 has none — pagination must stop there, never reaching 3.
        html = _CARD_HTML if len(captured_urls) == 1 else "<html>no more listings</html>"
        return httpx.Response(200, text=html, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    items = list(fetch_all_listings(max_pages=5))

    assert len(items) == 1
    assert captured_urls == [
        "https://www.yad2.co.il/realestate/rent",
        "https://www.yad2.co.il/realestate/rent?page=2",
    ]


def test_fetch_all_listings_advances_the_page_param_up_to_max_pages(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured_urls = []

    def fake_get(url, params, timeout):
        captured_urls.append(params["url"])
        # Every page returns a card, so pagination only stops because max_pages was reached.
        return httpx.Response(200, text=_CARD_HTML, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    items = list(fetch_all_listings(max_pages=3))

    assert len(items) == 3
    assert captured_urls == [
        "https://www.yad2.co.il/realestate/rent",
        "https://www.yad2.co.il/realestate/rent?page=2",
        "https://www.yad2.co.il/realestate/rent?page=3",
    ]


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
