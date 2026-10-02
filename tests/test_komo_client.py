"""Unit tests for scraper/komo_client.py. Sample HTML/JSON fragments mirror the exact real markup
confirmed live against modaaNum=4471462 and Komo's own adscoordinates endpoint (see
.github/workflows/diagnose-komo-homeless-reachability.yaml, runs #9-#13, and komo_client.py's own
module docstring) — not invented shapes. Mocks komo_client's own _isp_proxy_get/_isp_proxy_post
(a plain direct httpx GET/POST since the 2026-09-15 migration — name kept from the 2026-09-14
Bright Data ISP proxy era, only the body changed, see komo_client.py's own STATUS entry) rather
than hitting the network — no real HTTP traffic spent by running this suite, same reasoning as
test_yad2_client.py's own map-API tests, mocking at the same _fetch_direct-equivalent boundary."""
import pytest

import komo_client
from komo_client import (
    ADSCOORDINATES_URL,
    DETAILS_PAGE_URL,
    SEARCH_PAGE_URL,
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
    # the exact character (via \xa0) rather than a plain space, since that's genuinely what
    # unescape returns; a literal non-breaking space in source is visually indistinguishable from
    # a normal one and easy to silently flatten when this file is retyped/copied.
    assert item["description"] == "דירה & מרפסת \xa0גדולה"


def test_parse_details_html_street_html_entities_unescaped():
    # Real bug, found 2026-09-30 via an owner screenshot: og:title's own content="..." attribute
    # is real HTML source text, and Komo's real data for this listing contains a literal `"`
    # inside a street name (Hebrew gershayim, e.g. "הפלמ"ח") — which the source page itself
    # HTML-encodes as `&quot;` inside the attribute. This file used to hand-replace only &nbsp;
    # and skip a real html.unescape() entirely, so &quot; (and any other entity) leaked straight
    # into `street`/`city` as literal, un-decoded text instead of a plain `"`.
    html = (
        '<div class="price modaaWPrice"><span>3,000</span></div>'
        '<meta property="og:title" content="להשכרה&nbsp;דירות&nbsp;2 חדרים '
        '&nbsp;בבן עמי, הפלמ&quot;ח 1" />'
    )
    item = _parse_details_html(html, modaa_num="4471462")
    assert item["street"] == 'הפלמ"ח 1'
    assert item["city"] == "בן עמי"


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


def test_fetch_coordinate_ids_unknown_city_slug_raises_without_any_http_call(monkeypatch):
    def fail_get(url, *, context_label):
        raise AssertionError("should not make a request for an unknown city slug")

    monkeypatch.setattr(komo_client, "_isp_proxy_get", fail_get)
    with pytest.raises(KomoFetchError, match="No Hebrew city name mapped"):
        fetch_coordinate_ids("nonexistent-city")


def test_fetch_coordinate_ids_full_pipeline_real_confirmed_shape(monkeypatch):
    captured = {}

    def fake_get(url, *, context_label):
        captured["get_url"] = url
        return _REAL_SESSION_TOKEN_LINE

    def fake_post(url, data, *, context_label):
        captured["post_url"] = url
        captured["post_data"] = data
        return _REAL_COORDS_JSON

    monkeypatch.setattr(komo_client, "_isp_proxy_get", fake_get)
    monkeypatch.setattr(komo_client, "_isp_proxy_post", fake_post)

    result = fetch_coordinate_ids("jerusalem")

    assert result == [
        {"id": "4471462", "uid": "01xMnyW-jCSW", "lng": "35.2027025", "lat": "31.810889"}
    ]
    assert captured["get_url"] == f"{SEARCH_PAGE_URL}?nehes=1&cityName=ירושלים"
    assert captured["post_url"] == ADSCOORDINATES_URL
    assert captured["post_data"] == {"iska": "1", "sessionToken": "E327BE43D5B24F55A3AD23AA35FF5F2D"}


def test_fetch_coordinate_ids_isp_proxy_get_failure_raises(monkeypatch):
    def fail_get(url, *, context_label):
        raise KomoFetchError(f"Direct (un-proxied) request failed for {context_label}: {url}")

    monkeypatch.setattr(komo_client, "_isp_proxy_get", fail_get)
    with pytest.raises(KomoFetchError, match="Direct .un-proxied. request failed"):
        fetch_coordinate_ids("jerusalem")


def test_fetch_coordinate_ids_no_token_in_search_page_raises(monkeypatch):
    monkeypatch.setattr(
        komo_client, "_isp_proxy_get", lambda url, *, context_label: "<html>no token</html>"
    )
    with pytest.raises(KomoFetchError, match="No sessionToken found"):
        fetch_coordinate_ids("jerusalem")


def test_fetch_coordinate_ids_isp_proxy_post_failure_raises(monkeypatch):
    def fail_post(url, data, *, context_label):
        raise KomoFetchError(f"Direct (un-proxied) POST failed for {context_label}: {url}")

    monkeypatch.setattr(
        komo_client, "_isp_proxy_get", lambda url, *, context_label: _REAL_SESSION_TOKEN_LINE
    )
    monkeypatch.setattr(komo_client, "_isp_proxy_post", fail_post)
    with pytest.raises(KomoFetchError, match="Direct .un-proxied. POST failed"):
        fetch_coordinate_ids("jerusalem")


def test_fetch_coordinate_ids_non_ok_status_raises(monkeypatch):
    monkeypatch.setattr(
        komo_client, "_isp_proxy_get", lambda url, *, context_label: _REAL_SESSION_TOKEN_LINE
    )
    monkeypatch.setattr(
        komo_client, "_isp_proxy_post",
        lambda url, data, *, context_label: '{"status":"Error: iska is empty"}',
    )
    with pytest.raises(KomoFetchError, match="non-OK status"):
        fetch_coordinate_ids("jerusalem")


def test_fetch_coordinate_ids_not_json_raises(monkeypatch):
    monkeypatch.setattr(
        komo_client, "_isp_proxy_get", lambda url, *, context_label: _REAL_SESSION_TOKEN_LINE
    )
    monkeypatch.setattr(
        komo_client, "_isp_proxy_post", lambda url, data, *, context_label: "not json"
    )
    with pytest.raises(KomoFetchError, match="wasn't valid JSON"):
        fetch_coordinate_ids("jerusalem")


# --- fetch_all_coordinate_ids (2026-09-13: the correct way to call the above now — see its own
# docstring for the confirmed live finding that cityName doesn't filter this endpoint at all) ---


def test_fetch_all_coordinate_ids_delegates_to_a_fixed_valid_city_slug(monkeypatch):
    captured = {}

    def fake_fetch_coordinate_ids(city, *, iska="1", search_page_url=None):
        captured["city"] = city
        captured["iska"] = iska
        captured["search_page_url"] = search_page_url
        return [{"id": "123"}]

    monkeypatch.setattr(komo_client, "fetch_coordinate_ids", fake_fetch_coordinate_ids)

    result = fetch_all_coordinate_ids()

    assert captured["city"] == komo_client._NATIONWIDE_COVERAGE_CITY_SLUG
    assert result == [{"id": "123"}]


def test_fetch_all_coordinate_ids_passes_through_iska_and_search_page_url(monkeypatch):
    """2026-09-22: sale support — fetch_all_coordinate_ids(iska="2", search_page_url=...) must
    reach fetch_coordinate_ids unchanged, not silently fall back to the rent defaults."""
    captured = {}

    def fake_fetch_coordinate_ids(city, *, iska="1", search_page_url=None):
        captured["iska"] = iska
        captured["search_page_url"] = search_page_url
        return [{"id": "sale-1"}]

    monkeypatch.setattr(komo_client, "fetch_coordinate_ids", fake_fetch_coordinate_ids)

    result = fetch_all_coordinate_ids(iska="2", search_page_url=komo_client.SALE_SEARCH_PAGE_URL)

    assert captured["iska"] == "2"
    assert captured["search_page_url"] == komo_client.SALE_SEARCH_PAGE_URL
    assert result == [{"id": "sale-1"}]


# --- fetch_listing_detail (stage 3) ---


def test_fetch_listing_detail_isp_proxy_failure_returns_none_not_raise(monkeypatch):
    def fail_get(url, *, context_label):
        raise KomoFetchError(f"Direct (un-proxied) request failed for {context_label}: {url}")

    monkeypatch.setattr(komo_client, "_isp_proxy_get", fail_get)
    assert fetch_listing_detail("4471462") is None


def test_fetch_listing_detail_parses_the_real_confirmed_shape(monkeypatch):
    captured = {}

    def fake_get(url, *, context_label):
        captured["url"] = url
        return _REAL_DETAILS_HTML

    monkeypatch.setattr(komo_client, "_isp_proxy_get", fake_get)

    item = fetch_listing_detail("4471462")

    assert item["price"] == 7000
    assert item["rooms"] == 2.0
    assert captured["url"] == f"{DETAILS_PAGE_URL}?modaaNum=4471462"


# --- fetch_search_results (convenience wrapper) ---


def test_fetch_search_results_yields_one_priced_item_per_coordinate_id(monkeypatch):
    def fake_get(url, *, context_label):
        if url.startswith(SEARCH_PAGE_URL):
            return _REAL_SESSION_TOKEN_LINE
        return _REAL_DETAILS_HTML

    monkeypatch.setattr(komo_client, "_isp_proxy_get", fake_get)
    monkeypatch.setattr(
        komo_client, "_isp_proxy_post", lambda url, data, *, context_label: _REAL_COORDS_JSON
    )

    items = list(fetch_search_results("jerusalem"))

    assert len(items) == 1
    assert items[0]["id"] == "4471462"
    assert items[0]["price"] == 7000


def test_fetch_search_results_skips_items_with_no_id(monkeypatch):
    monkeypatch.setattr(
        komo_client, "_isp_proxy_get", lambda url, *, context_label: _REAL_SESSION_TOKEN_LINE
    )
    monkeypatch.setattr(
        komo_client, "_isp_proxy_post",
        lambda url, data, *, context_label: '{"status":"OK","list":[{"uid":"no-id-here"}]}',
    )

    assert list(fetch_search_results("jerusalem")) == []


# --- 2026-10-02: move-in text, ticked amenities, ground floor, 3-box layout (all confirmed live on
# 25 real pages via .github/workflows/diagnose-komo-detail-amenities.yaml) ---

_REAL_AMENITY_UL_ONE_TICKED = (
    "<ul class=\"modaaWNewUl md_c_183 \" style=\"list-style-type: none;\" >"
    "<li class='mamad '><span class='faspan nocolor'><i class='fa-light'></i></span>ממד</li>"
    "<li class='maalit add'><span class='faspan nocolor'><i class='fa-light'></i></span>מעלית</li>"
    "<li class='soragim '>סורגים</li><li class='pets add'>חיות מחמד</li>"
    "<li class='renovated add'>משופצת</li><li class='longRent '>לטווח ארוך</li></ul>"
)


def _page_with(extra_html: str, *, floor_box: str | None = None, size_box: str | None = None) -> str:
    base = (
        '<div class="price modaaWPrice" ><span class="ModaaWDetailsValue" >5,000</span></div>'
        '<meta property="og:title" content="להשכרה&nbsp;דירות&nbsp;3 חדרים  &nbsp;בחיפה, הנשיא 5" />'
    )
    floor_box = floor_box or (
        '<div class="floor firstInfoBlockWrap" style="width:25%;" >'
        '<div class="firstInfo" > 2 </div><div class="firstInfoTitle" > קומה</div></div>'
    )
    size_box = size_box or (
        '<div class="mr firstInfoBlockWrap" style="width:25%;" >'
        '<div class="firstInfo" > 80 </div><div class="firstInfoTitle" > מ"ר</div></div>'
    )
    return base + floor_box + size_box + extra_html


def test_parse_details_reads_immediate_move_in_text():
    enter = (
        '<div class="enter " style="width:25%;" > <div class="firstInfo" > מיידית </div> '
        '<div class="firstInfoTitle" > תאריך כניסה</div></div>'
    )
    item = _parse_details_html(_page_with(enter), modaa_num="1")
    assert item["move_in_text"] == "מיידית"


def test_parse_details_reads_flexible_move_in_text():
    enter = '<div class="enter " style="width:25%;"><div class="firstInfo" >גמיש</div></div>'
    assert _parse_details_html(_page_with(enter), modaa_num="1")["move_in_text"] == "גמיש"


def test_parse_details_has_no_move_in_key_when_the_page_has_no_entry_box():
    item = _parse_details_html(_page_with(""), modaa_num="1")
    assert "move_in_text" not in item


def test_parse_details_only_ticked_amenities_count_and_unticked_are_ignored():
    item = _parse_details_html(_page_with(_REAL_AMENITY_UL_ONE_TICKED), modaa_num="1")
    assert item["elevator"] is True
    assert item["petsAllowed"] is True
    assert item["renovated"] is True
    assert "safeRoom" not in item  # <li class='mamad '> is NOT ticked
    assert "roommates" not in item


def test_parse_details_no_amenity_keys_when_nothing_is_ticked():
    unticked = "<ul><li class='mamad '>ממד</li><li class='maalit '>מעלית</li></ul>"
    item = _parse_details_html(_page_with(unticked), modaa_num="1")
    assert not ({"elevator", "petsAllowed", "renovated", "roommates", "safeRoom", "furnished"} & set(item))


def test_parse_details_ground_floor_is_floor_zero():
    ground = (
        '<div class="floor firstInfoBlockWrap" style="width:33%;" >'
        '<div class="firstInfo" > קרקע </div><div class="firstInfoTitle" > קומה</div></div>'
    )
    assert _parse_details_html(_page_with("", floor_box=ground), modaa_num="1")["floor"] == 0


def test_parse_details_reads_size_from_the_3_box_layout_without_firstinfoblockwrap():
    """Live page 30327: `<div class="mr " style="width:33%;">` - the size used to be missed."""
    size = (
        '<div class="mr " style="width:33%;" > <div class="firstInfo" > 35 </div> '
        '<div class="firstInfoTitle" > מ"ר</div></div>'
    )
    assert _parse_details_html(_page_with("", size_box=size), modaa_num="1")["square_meters"] == 35


def test_normalize_carries_komo_move_in_text_and_ticked_amenities_into_the_listing():
    from normalize import normalize

    item = normalize(
        {
            "id": "55", "url": "https://www.komo.co.il/x", "price": 5000, "rooms": 3.0,
            "floor": 0, "move_in_text": "מיידית", "elevator": True, "petsAllowed": True,
            "safeRoom": True, "furnished": True,
        },
        source="komo",
    )
    assert item.floor == 0
    assert item.move_in_note == "מיידית"
    assert item.has_elevator is True and item.pets_allowed is True
    assert item.safe_room_type == "safe_room" and item.furniture == "furnished"


def test_normalize_leaves_amenities_unknown_when_komo_ticked_nothing():
    from normalize import normalize

    item = normalize({"id": "56", "url": "https://www.komo.co.il/y", "price": 5000}, source="komo")
    assert item.has_elevator is None and item.safe_room_type is None
    assert item.furniture is None and item.move_in_note is None
