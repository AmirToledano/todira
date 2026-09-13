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
    fetch_search_results,
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
    }


def test_parse_rows_multiple_real_rows_in_one_page():
    items = list(_parse_rows(_REAL_ROW_NO_NEIGHBORHOOD + _REAL_ROW_WITH_NEIGHBORHOOD))
    assert [item["id"] for item in items] == ["746758", "746729"]


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
