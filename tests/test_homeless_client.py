"""Unit tests for scraper/homeless_client.py. Sample HTML fragments are the exact real rows
confirmed live against homeless.co.il/rent/ (see
.github/workflows/diagnose-komo-homeless-reachability.yaml's actual output and
homeless_client.py's own module docstring) — not invented shapes. Mocks httpx.get directly rather
than hitting the network, no real ZenRows credits spent by running this suite, same reasoning as
test_yad2_client.py/test_komo_client.py."""
import httpx
import pytest

from homeless_client import (
    SEARCH_PAGE_URL,
    ZENROWS_API_KEY_ENV_VAR,
    HomelessFetchError,
    _parse_rows,
    fetch_listing_description,
    fetch_search_results,
)

# Confirmed live 2026-09-13 (diagnose-komo-gallery-and-homeless-description.yaml) against a real
# listing's own detail page (id=746758) — not invented.
_REAL_DETAIL_PAGE_HTML = (
    '<meta name="Description" content="דירה להשכרה בתל אביב, דרך השלום מודעה 746758 -  '
    'הכניסה מרחוב הורודצקי. זו הכניסה השקטה של הבניין.">'
    '<meta property="og:description" content="דירה להשכרה בתל אביב, דרך השלום מודעה 746758 -  '
    'הכניסה מרחוב הורודצקי. זו הכניסה השקטה של הבניין.">'
)

# --- real confirmed rows (see module docstring) ---

_REAL_ROW_NO_NEIGHBORHOOD = (
    '<tr onclick="openPopup(\'/rent/ViewDetails,746758.aspx\');" id="ad_746758" type="ad" '
    'class="light" rel="boldad">'
    '<td class="selectionarea"><input type="checkbox" id="chk_746758" name="chk_746758" '
    'class="markmessage" /></td>'
    '<td style="width:150px" ><div><img class="PictureDisplayOnBoard" '
    'src="https://uploads.homeless.co.il/rent/202609/300/nvFile5386664.jpg" '
    'alt="דירה להשכרה 4 חדרים בתל אביב דרך השלום " /></div></td>'
    '<td style="width:100px" >דירה</td>'
    '<td style="width:100px" >תל אביב</td>'
    '<td style="width:100px" ></td>'
    '<td style="width:100px" >דרך השלום</td>'
    '<td style="width:80px" >4</td>'
    '<td style="width:80px" >2</td>'
    '<td style="width:100px" >2,130 ₪</td>'
    '<td style="width:100px" >מיידי</td>'
    '<td style="width:100px" ><span class="newmessage">13/09/2026</span></td>'
    '<td style="width:100px" ><a href="/rent/viewad,746758.aspx">לפרטים</a></td>'
    '</tr>'
)

_REAL_ROW_WITH_NEIGHBORHOOD = (
    '<tr onclick="openPopup(\'/rent/ViewDetails,746729.aspx\');" id="ad_746729" type="ad" '
    'class="light" rel="boldad">'
    '<td class="selectionarea"><input type="checkbox" id="chk_746729" name="chk_746729" '
    'class="markmessage" /></td>'
    '<td style="width:150px" ><div><img class="PictureDisplayOnBoard" src="x.jpg" alt="y" />'
    '</div></td>'
    '<td style="width:100px" >דירה</td>'
    '<td style="width:100px" >פתח תקווה</td>'
    '<td style="width:100px" >כפר גנים</td>'
    '<td style="width:100px" >האלונים 4</td>'
    '<td style="width:80px" >5</td>'
    '<td style="width:80px" >7</td>'
    '<td style="width:100px" >8,600 ₪</td>'
    '<td style="width:100px" >מיידי</td>'
    '<td style="width:100px" ><span class="newmessage">13/09/2026</span></td>'
    '<td style="width:100px" ><a href="/rent/viewad,746729.aspx">לפרטים</a></td>'
    '</tr>'
)

# Real Tivuch (brokered) row — confirmed live 2026-09-14 (diagnose-homeless-tivuch-column-
# layout.yaml, id=83476): NO floor column at all between rooms and price, unlike the plain rows
# above. See homeless_client.py's own module docstring (TIVUCH COLUMN LAYOUT) for the full finding.
_REAL_TIVUCH_ROW = (
    '<tr onclick="openPopup(\'/RentTivuch/ViewDetails,83476.aspx\');" id="ad_83476" type="ad" '
    'class="light" rel="boldad">'
    '<td class="selectionarea"><input type="checkbox" id="chk_83476" name="chk_83476" '
    'class="markmessage" /></td>'
    '<td style="width:150px" ><div><img class="PictureDisplayOnBoard" '
    'src="https://uploads.homeless.co.il/renttivuch/202607/300/nvFile5335372.jpeg" '
    'alt="דירה להשכרה 2 חדרים בתל אביב יפו הקונגרס " /></div></td>'
    '<td style="width:100px" >דירה</td>'
    '<td style="width:100px" >תל אביב יפו</td>'
    '<td style="width:100px" >תל אביב דק</td>'
    '<td style="width:100px" >הקונגרס</td>'
    '<td style="width:80px" >2</td>'
    '<td style="width:100px" >5,600 ₪</td>'
    '<td style="width:100px" >22/8/2026</td>'
    '<td style="width:100px" ><span class="newmessage">14/09/2026</span></td>'
    '<td style="width:100px" ><a href="/RentTivuch/viewad,83476.aspx">לפרטים</a></td>'
    '</tr>'
)


# --- _parse_rows (the real integration point) ---


def test_parse_rows_extracts_the_real_confirmed_row_without_neighborhood():
    items = list(_parse_rows(_REAL_ROW_NO_NEIGHBORHOOD))
    assert len(items) == 1
    assert items[0] == {
        "id": "746758",
        "url": "https://www.homeless.co.il/rent/viewad,746758.aspx",
        "price": 2130,
        "rooms": 4.0,
        "floor": 2,
        "square_meters": None,
        "street": "דרך השלום",
        "neighborhood": None,
        "city": "תל אביב",
        "images": ["https://uploads.homeless.co.il/rent/202609/300/nvFile5386664.jpg"],
    }


def test_parse_rows_extracts_the_real_confirmed_row_with_neighborhood():
    items = list(_parse_rows(_REAL_ROW_WITH_NEIGHBORHOOD))
    assert len(items) == 1
    assert items[0] == {
        "id": "746729",
        "url": "https://www.homeless.co.il/rent/viewad,746729.aspx",
        "price": 8600,
        "rooms": 5.0,
        "floor": 7,
        "square_meters": None,
        "street": "האלונים 4",
        "neighborhood": "כפר גנים",
        "city": "פתח תקווה",
        "images": ["x.jpg"],
    }


def test_parse_rows_tivuch_row_has_no_floor_and_the_right_price_not_shifted():
    # 2026-09-14: the real, confirmed fix — before this, a Tivuch row's floor field silently
    # captured its own price string, and its price field captured the entry-date string that came
    # after (both wrong, not just missing). See homeless_client.py's own module docstring.
    items = list(_parse_rows(_REAL_TIVUCH_ROW))
    assert len(items) == 1
    assert items[0] == {
        "id": "83476",
        "url": "https://www.homeless.co.il/RentTivuch/viewad,83476.aspx",
        "price": 5600,
        "rooms": 2.0,
        "floor": None,
        "square_meters": None,
        "street": "הקונגרס",
        "neighborhood": "תל אביב דק",
        "city": "תל אביב יפו",
        "images": ["https://uploads.homeless.co.il/renttivuch/202607/300/nvFile5335372.jpeg"],
    }


def test_parse_rows_empty_src_yields_no_images_not_a_placeholder():
    # A blank src="" (a real possible shape — e.g. a listing with no uploaded photo yet) must
    # degrade to an empty list, not a list containing an empty string.
    row = (
        '<tr onclick="openPopup(\'/rent/ViewDetails,1.aspx\');" id="ad_1" type="ad" '
        'class="light" rel="boldad">'
        '<td class="selectionarea"><input type="checkbox" /></td>'
        '<td style="width:150px" ><div><img class="PictureDisplayOnBoard" src="" alt="" />'
        '</div></td>'
        '<td style="width:100px" >דירה</td>'
        '<td style="width:100px" >חיפה</td>'
        '<td style="width:100px" ></td>'
        '<td style="width:100px" >הרצל</td>'
        '<td style="width:80px" >3</td>'
        '<td style="width:80px" >1</td>'
        '<td style="width:100px" >4,000 ₪</td>'
        '<td style="width:100px" >מיידי</td>'
        '<td style="width:100px" ><span class="newmessage">14/09/2026</span></td>'
        '<td style="width:100px" ><a href="/rent/viewad,1.aspx">לפרטים</a></td>'
        '</tr>'
    )
    items = list(_parse_rows(row))
    assert items[0]["images"] == []


def test_parse_rows_multiple_real_rows_in_one_page():
    items = list(_parse_rows(_REAL_ROW_NO_NEIGHBORHOOD + _REAL_ROW_WITH_NEIGHBORHOOD))
    assert [item["id"] for item in items] == ["746758", "746729"]


def test_parse_rows_skips_a_malformed_row_instead_of_crashing(caplog):
    # Fewer <td> cells than even the shortest real shape (Tivuch, 11) — the table's own markup
    # changed again in some way this project hasn't seen yet. Must be skipped with a clear warning,
    # never raise and never yield a bogus/partial item.
    malformed_row = (
        '<tr id="ad_999" type="ad" class="light">'
        '<td class="selectionarea"><input type="checkbox" /></td>'
        '<td style="width:100px" >דירה</td>'
        '<td style="width:100px" >חיפה</td>'
        '</tr>'
    )
    good_row = _REAL_ROW_NO_NEIGHBORHOOD
    items = list(_parse_rows(malformed_row + good_row))
    assert [item["id"] for item in items] == ["746758"]
    assert "Skipping Homeless row id=999" in caplog.text


def test_parse_rows_empty_html_yields_nothing():
    assert list(_parse_rows("<html><body>no rows here</body></html>")) == []


# --- fetch_search_results ---


def test_missing_api_key_raises_without_any_http_call(monkeypatch):
    monkeypatch.delenv(ZENROWS_API_KEY_ENV_VAR, raising=False)
    with pytest.raises(HomelessFetchError, match=ZENROWS_API_KEY_ENV_VAR):
        list(fetch_search_results())


def test_successful_fetch_sends_the_right_params_and_parses_rows(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured = {}

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        return httpx.Response(
            200, text=_REAL_ROW_NO_NEIGHBORHOOD, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    items = list(fetch_search_results())

    assert len(items) == 1
    assert items[0]["id"] == "746758"
    assert captured["url"] == "https://api.zenrows.com/v1/"
    assert captured["params"]["apikey"] == "fake-key"
    assert captured["params"]["url"] == SEARCH_PAGE_URL
    # Plain fetch only — no js_render/premium_proxy, confirmed 1-credit tier.
    assert "js_render" not in captured["params"]
    assert "premium_proxy" not in captured["params"]


def test_zenrows_error_body_raises_with_code_and_title(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    error_body = '{"code":"AUTH004","title":"Usage exceeded (AUTH004)"}'

    def fake_get(url, params, timeout):
        return httpx.Response(200, text=error_body, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(HomelessFetchError, match="AUTH004"):
        list(fetch_search_results())


def test_non_200_status_raises_homeless_fetch_error(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        return httpx.Response(500, text="internal error", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(HomelessFetchError, match="http_status=500"):
        list(fetch_search_results())


def test_network_failure_fails_soft_as_homeless_fetch_error(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(HomelessFetchError):
        list(fetch_search_results())


# --- fetch_listing_description (2026-09-13) ---


def test_fetch_listing_description_extracts_the_real_confirmed_description(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured = {}

    def fake_get(url, params, timeout):
        captured["params"] = params
        return httpx.Response(
            200, text=_REAL_DETAIL_PAGE_HTML, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    # 2026-09-13: fetch_listing_description now takes the listing's own real URL (as returned by
    # fetch_search_results/_parse_rows), not a bare id — a bare id can no longer be reconstructed
    # into the right URL, since brokered ("Tivuch") listings use a different path prefix
    # (/RentTivuch/ vs /rent/) that isn't derivable from the id alone. See homeless_client.py's own
    # module docstring and _ROW_RE's comment for the real bug this fixed.
    real_url = "https://www.homeless.co.il/rent/viewad,746758.aspx"
    description = fetch_listing_description(real_url)

    assert description == (
        "דירה להשכרה בתל אביב, דרך השלום מודעה 746758 -  הכניסה מרחוב הורודצקי. "
        "זו הכניסה השקטה של הבניין."
    )
    assert captured["params"]["url"] == real_url


def test_fetch_listing_description_missing_meta_tags_returns_none(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        return httpx.Response(200, text="<html><body>no meta here</body></html>", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    assert fetch_listing_description("https://www.homeless.co.il/rent/viewad,746758.aspx") is None


def test_fetch_listing_description_missing_api_key_returns_none_not_raises(monkeypatch):
    # Unlike fetch_search_results (which raises), this is genuinely optional enrichment — never
    # raises, same defensive contract as komo_client.fetch_listing_detail.
    monkeypatch.delenv(ZENROWS_API_KEY_ENV_VAR, raising=False)
    assert fetch_listing_description("https://www.homeless.co.il/rent/viewad,746758.aspx") is None


def test_fetch_listing_description_network_failure_returns_none_not_raises(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, timeout):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)

    assert fetch_listing_description("https://www.homeless.co.il/rent/viewad,746758.aspx") is None
