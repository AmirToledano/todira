"""Unit tests for scraper/komo_client.py. Sample HTML/JSON fragments mirror the exact real markup
confirmed live against modaaNum=4471462 and Komo's own adscoordinates endpoint (see
.github/workflows/diagnose-komo-homeless-reachability.yaml, runs #9-#13, and komo_client.py's own
module docstring) — not invented shapes. Mocks httpx directly rather than hitting the network, no
real ZenRows credits spent by running this suite, same reasoning as test_yad2_client.py."""
import httpx
import pytest

import komo_client
from komo_client import (
    ADSCOORDINATES_URL,
    DETAILS_PAGE_URL,
    SEARCH_PAGE_URL,
    ZENROWS_API_KEY_ENV_VAR,
    KomoFetchError,
    _extract_session_token,
    _parse_details_html,
    fetch_all_coordinate_ids,
    fetch_coordinate_ids,
    fetch_listing_detail,
    fetch_search_results,
)

# --- real confirmed fragments (see module docstring) ---

_REAL_SESSION_TOKEN_LINE = 'window.sessionToken = "E327BE43D5B24F55A3AD23AA35FF5F2D";'

_REAL_DETAILS_HTML = (
    '<div class="priceWrap modaaWMoreDetails modaaWTitleArea" >'
    '<div class="price modaaWPrice" >'
    '<span class="ModaaWDetailsValue md_f_23" >7,000&nbsp;&#8362;</span></div></div>'
    '<meta property="og:title" content="להשכרה&nbsp;דירות&nbsp;2 חדרים  '
    '&nbsp;בירושלים, שערי ירושלים 5" />'
    # Confirmed live (diagnose-komo-homeless-reachability.yaml run #12, re-read 2026-09-13 while
    # investigating why Komo listings never carry a description) — same real listing's actual
    # <meta name="Description"> content, truncated here (the real page's text runs on longer).
    '<meta name="Description" content="דירה יוקרתית מושקעת ברמה גבוהה עם מיזוג '
    'מרכזי וחימום תת רצפתי">'
    # Confirmed live (diagnose-komo-detail-images.yaml, 2026-09-13) — this same real listing's
    # actual og:image tag, byte-for-byte (bare "&", not "&amp;" — Komo's own markup is sloppy
    # here; html.unescape is a safe no-op on an unrecognized "&picNum"/"&luachNum" sequence, so
    # this doesn't need to be HTML-escaped to round-trip correctly). A relative path, needing
    # urljoin against DETAILS_PAGE_URL.
    '<meta property="og:image" content="/api/modaot/tmunot/showPic/list/'
    '?picSize=b&picNum=25352812&luachNum=2">'
    '<div class="floor firstInfoBlockWrap" style="width:25%;" >'
    '<div class="firstInfo" > 1 </div><div class="firstInfoTitle" > קומה</div></div>'
    '<div class="mr firstInfoBlockWrap" style="width:25%;" >'
    '<div class="firstInfo" > 38 </div><div class="firstInfoTitle" > מ"ר</div></div>'
    # Confirmed live (diagnose-komo-gallery-and-homeless-description.yaml, 2026-09-13) — this same
    # real listing's actual gallery: 2 distinct real photos, the first one repeated (desktop +
    # mobile responsive layouts render the SAME photo twice) — must de-duplicate. Then a real
    # "sameads" (recommended listings) carousel showing a DIFFERENT listing's own photo, which
    # must NOT be included.
    '<div class="hideOnMobile desktopPics">'
    '<img alt="תמונה למודעה" src="/api/modaot/tmunot/showPic/list/'
    '?picSize=b&picNum=25352812&luachNum=2" /></div>'
    '<div class="tmunotDesktop">'
    '<img alt="תמונה למודעה" src="/api/modaot/tmunot/showPic/list/'
    '?picSize=b&picNum=25352812&luachNum=2" /></div>'
    '<div class="tmunotDesktop">'
    '<img alt="תמונה למודעה" src="/api/modaot/tmunot/showPic/list/'
    '?picSize=b&picNum=25352813&luachNum=2" /></div>'
    '<div class="sameads-swiper"><div class="cItemWrap">'
    '<img alt="תמונה למודעה" src="/api/modaot/tmunot/showPic/list/'
    '?picNum=99999999&luachNum=2" /></div></div>'
)

_REAL_COORDS_JSON = (
    '{"status":"OK","list":[{"id":"4471462","uid":"01xMnyW-jCSW",'
    '"lng":"35.2027025","lat":"31.810889"}]}'
)


# --- _extract_session_token ---


def test_extract_session_token_from_real_confirmed_line():
    assert _extract_session_token(_REAL_SESSION_TOKEN_LINE) == "E327BE43D5B24F55A3AD23AA35FF5F2D"


def test_extract_session_token_missing_returns_none():
    assert _extract_session_token("<html>no token here</html>") is None


# --- _parse_details_html (the real integration point for stage 3) ---


def test_parse_details_html_extracts_the_real_confirmed_listing():
    item = _parse_details_html(_REAL_DETAILS_HTML, modaa_num="4471462")
    assert item == {
        "id": "4471462",
        "url": "https://www.komo.co.il/code/nadlan/details/?modaaNum=4471462",
        "price": 7000,
        "rooms": 2.0,
        "floor": 1,
        "square_meters": 38,
        "description": "דירה יוקרתית מושקעת ברמה גבוהה עם מיזוג מרכזי וחימום תת רצפתי",
        "images": [
            "https://www.komo.co.il/api/modaot/tmunot/showPic/list/"
            "?picSize=b&picNum=25352812&luachNum=2",
            "https://www.komo.co.il/api/modaot/tmunot/showPic/list/"
            "?picSize=b&picNum=25352813&luachNum=2",
        ],
        "street": "שערי ירושלים 5",
        "neighborhood": None,
        "city": "ירושלים",
    }


def test_parse_details_html_missing_description_leaves_it_none():
    # No <meta name="Description"> at all — must degrade to None, not raise (same benefit-of-the-
    # doubt policy as every other optional field here).
    html = (
        '<div class="price modaaWPrice"><span>7,000</span></div>'
        '<meta property="og:title" content="להשכרה&nbsp;דירות&nbsp;2 חדרים '
        '&nbsp;בירושלים, שערי ירושלים 5" />'
    )
    item = _parse_details_html(html, modaa_num="4471462")
    assert item["description"] is None


def test_parse_details_html_description_html_entities_unescaped():
    html = (
        '<div class="price modaaWPrice"><span>7,000</span></div>'
        '<meta property="og:title" content="להשכרה&nbsp;דירות&nbsp;2 חדרים '
        '&nbsp;בירושלים, שערי ירושלים 5" />'
        '<meta name="Description" content="דירה &amp; מרפסת &nbsp;גדולה">'
    )
    item = _parse_details_html(html, modaa_num="4471462")
    # html.unescape("&nbsp;") is U+00A0 (a real non-breaking space), not a plain " " — asserting
    # the exact character rather than a plain space, since that's genuinely what unescape returns.
    assert item["description"] == "דירה & מרפסת  גדולה"


def test_parse_details_html_no_images_at_all_leaves_images_empty():
    # Neither a gallery nor an og:image — must degrade to an empty list, not raise (same
    # benefit-of-the-doubt policy as every other optional field here).
    html = (
        '<div class="price modaaWPrice"><span>7,000</span></div>'
        '<meta property="og:title" content="להשכרה&nbsp;דירות&nbsp;2 חדרים '
        '&nbsp;בירושלים, שערי ירושלים 5" />'
    )
    item = _parse_details_html(html, modaa_num="4471462")
    assert item["images"] == []


def test_parse_details_html_falls_back_to_og_image_when_no_gallery_markup_matches():
    # A page with a real og:image but no _GALLERY_IMG_RE-matching <img> tags (e.g. a future markup
    # change) still gets that one photo rather than nothing.
    html = (
        '<div class="price modaaWPrice"><span>7,000</span></div>'
        '<meta property="og:title" content="להשכרה&nbsp;דירות&nbsp;2 חדרים '
        '&nbsp;בירושלים, שערי ירושלים 5" />'
        '<meta property="og:image" content="/api/modaot/tmunot/showPic/list/'
        '?picSize=b&picNum=12345&luachNum=2">'
    )
    item = _parse_details_html(html, modaa_num="4471462")
    assert item["images"] == [
        "https://www.komo.co.il/api/modaot/tmunot/showPic/list/?picSize=b&picNum=12345&luachNum=2"
    ]


def test_parse_details_html_missing_price_returns_none():
    html = '<meta property="og:title" content="להשכרה&nbsp;דירות&nbsp;2 חדרים &nbsp;בירושלים, א 1" />'
    assert _parse_details_html(html, modaa_num="1") is None


def test_parse_details_html_missing_og_title_returns_none():
    html = '<div class="price modaaWPrice"><span>7,000</span></div>'
    assert _parse_details_html(html, modaa_num="1") is None


def test_parse_details_html_missing_stat_blocks_leaves_floor_and_size_none():
    # og:title + price are enough to build a usable (if partial) item — a missing floor/mr block
    # must degrade to None, not abort the whole parse (same benefit-of-the-doubt policy as
    # normalize.py elsewhere in this project).
    html = (
        '<div class="price modaaWPrice"><span>7,000</span></div>'
        '<meta property="og:title" content="להשכרה&nbsp;דירות&nbsp;2 חדרים '
        '&nbsp;בירושלים, שערי ירושלים 5" />'
    )
    item = _parse_details_html(html, modaa_num="4471462")
    assert item["price"] == 7000
    assert item["floor"] is None
    assert item["square_meters"] is None


# --- fetch_coordinate_ids (stages 1+2) ---


def test_fetch_coordinate_ids_missing_api_key_raises_without_any_http_call(monkeypatch):
    monkeypatch.delenv(ZENROWS_API_KEY_ENV_VAR, raising=False)
    with pytest.raises(KomoFetchError, match=ZENROWS_API_KEY_ENV_VAR):
        fetch_coordinate_ids("jerusalem")


def test_fetch_coordinate_ids_unknown_city_slug_raises_without_any_http_call(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    with pytest.raises(KomoFetchError, match="No Hebrew city name mapped"):
        fetch_coordinate_ids("nonexistent-city")


def test_fetch_coordinate_ids_full_pipeline_real_confirmed_shape(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured = {}

    def fake_get(url, params, timeout):
        captured["get_url"] = url
        captured["get_params"] = params
        return httpx.Response(
            200, text=_REAL_SESSION_TOKEN_LINE, request=httpx.Request("GET", url)
        )

    def fake_post(url, params, data, timeout):
        captured["post_url"] = url
        captured["post_params"] = params
        captured["post_data"] = data
        return httpx.Response(200, text=_REAL_COORDS_JSON, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)

    result = fetch_coordinate_ids("jerusalem")

    assert result == [
        {"id": "4471462", "uid": "01xMnyW-jCSW", "lng": "35.2027025", "lat": "31.810889"}
    ]
    assert captured["get_params"]["url"] == f"{SEARCH_PAGE_URL}?nehes=1&cityName=ירושלים"
    assert captured["post_params"]["url"] == ADSCOORDINATES_URL
    assert captured["post_data"] == {"iska": "1", "sessionToken": "E327BE43D5B24F55A3AD23AA35FF5F2D"}


def test_fetch_coordinate_ids_no_token_in_search_page_raises(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        return httpx.Response(200, text="<html>no token</html>", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(KomoFetchError, match="No sessionToken found"):
        fetch_coordinate_ids("jerusalem")


def test_fetch_coordinate_ids_non_ok_status_raises(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        return httpx.Response(
            200, text=_REAL_SESSION_TOKEN_LINE, request=httpx.Request("GET", url)
        )

    def fake_post(url, params, data, timeout):
        return httpx.Response(
            200, text='{"status":"Error: iska is empty"}', request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(KomoFetchError, match="non-OK status"):
        fetch_coordinate_ids("jerusalem")


def test_fetch_coordinate_ids_zenrows_error_body_raises_with_code(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    error_body = '{"code":"AUTH004","title":"Usage exceeded (AUTH004)"}'

    def fake_get(url, params, timeout):
        return httpx.Response(200, text=error_body, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(KomoFetchError, match="AUTH004"):
        fetch_coordinate_ids("jerusalem")


# --- fetch_all_coordinate_ids (2026-09-13: the correct way to call the above now — see its own
# docstring for the confirmed live finding that cityName doesn't filter this endpoint at all) ---


def test_fetch_all_coordinate_ids_delegates_to_a_fixed_valid_city_slug(monkeypatch):
    captured = {}

    def fake_fetch_coordinate_ids(city):
        captured["city"] = city
        return [{"id": "123"}]

    monkeypatch.setattr(komo_client, "fetch_coordinate_ids", fake_fetch_coordinate_ids)

    result = fetch_all_coordinate_ids()

    assert captured["city"] == komo_client._NATIONWIDE_COVERAGE_CITY_SLUG
    assert result == [{"id": "123"}]


# --- fetch_listing_detail (stage 3) ---


def test_fetch_listing_detail_missing_api_key_returns_none_without_http_call(monkeypatch):
    monkeypatch.delenv(ZENROWS_API_KEY_ENV_VAR, raising=False)

    def fake_get(*args, **kwargs):
        raise AssertionError("should not make an HTTP call without an API key")

    monkeypatch.setattr(httpx, "get", fake_get)
    assert fetch_listing_detail("4471462") is None


def test_fetch_listing_detail_parses_the_real_confirmed_shape(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured = {}

    def fake_get(url, params, timeout):
        captured["params"] = params
        return httpx.Response(200, text=_REAL_DETAILS_HTML, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    item = fetch_listing_detail("4471462")

    assert item["price"] == 7000
    assert item["rooms"] == 2.0
    assert captured["params"]["url"] == f"{DETAILS_PAGE_URL}?modaaNum=4471462"


def test_fetch_listing_detail_non_200_returns_none(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        return httpx.Response(500, text="internal error", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert fetch_listing_detail("4471462") is None


def test_fetch_listing_detail_network_failure_returns_none_not_raise(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)
    assert fetch_listing_detail("4471462") is None


# --- fetch_search_results (convenience wrapper) ---


def test_fetch_search_results_yields_one_priced_item_per_coordinate_id(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        if params["url"].startswith(SEARCH_PAGE_URL):
            return httpx.Response(
                200, text=_REAL_SESSION_TOKEN_LINE, request=httpx.Request("GET", url)
            )
        return httpx.Response(200, text=_REAL_DETAILS_HTML, request=httpx.Request("GET", url))

    def fake_post(url, params, data, timeout):
        return httpx.Response(200, text=_REAL_COORDS_JSON, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)

    items = list(fetch_search_results("jerusalem"))

    assert len(items) == 1
    assert items[0]["id"] == "4471462"
    assert items[0]["price"] == 7000


def test_fetch_search_results_skips_items_with_no_id(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        return httpx.Response(
            200, text=_REAL_SESSION_TOKEN_LINE, request=httpx.Request("GET", url)
        )

    def fake_post(url, params, data, timeout):
        return httpx.Response(
            200, text='{"status":"OK","list":[{"uid":"no-id-here"}]}',
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)

    assert list(fetch_search_results("jerusalem")) == []
