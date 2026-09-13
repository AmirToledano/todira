"""Tests for common/dorin_common/bright_data_client.py — the Bright Data Data Collector API
(`/dca/...`) trigger/poll flow (confirmed real 2026-09-12, see that module's own docstring for the
earlier wrong-API-guess this replaced), and fetch_listing_description()'s tolerant field-name
parsing / failure modes.
"""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from dorin_common import bright_data_client


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        bright_data_client.API_KEY_ENV_VAR,
        bright_data_client.COLLECTOR_ID_ENV_VAR,
        bright_data_client.DESCRIPTION_FIELD_ENV_VAR,
        bright_data_client.WEB_UNLOCKER_ZONE_ENV_VAR,
        bright_data_client.ISP_PROXY_HOST_ENV_VAR,
        bright_data_client.ISP_PROXY_USER_ENV_VAR,
        bright_data_client.ISP_PROXY_PASS_ENV_VAR,
    ):
        monkeypatch.delenv(var, raising=False)


def _configure(monkeypatch):
    monkeypatch.setenv(bright_data_client.API_KEY_ENV_VAR, "key123")
    monkeypatch.setenv(bright_data_client.COLLECTOR_ID_ENV_VAR, "c_abc123")


def _resp(url, json_body, status=200, text=None):
    kwargs = {"json": json_body} if text is None else {"content": text}
    return httpx.Response(status, request=httpx.Request("GET", url), **kwargs)


# --- is_configured ---


def test_not_configured_when_unset():
    assert bright_data_client.is_configured() is False


def test_not_configured_with_only_api_key(monkeypatch):
    monkeypatch.setenv(bright_data_client.API_KEY_ENV_VAR, "key123")
    assert bright_data_client.is_configured() is False


def test_configured_with_both(monkeypatch):
    _configure(monkeypatch)
    assert bright_data_client.is_configured() is True


# --- fetch_listing_description ---


def test_returns_none_when_not_configured():
    assert bright_data_client.fetch_listing_description("https://yad2.co.il/item/1") is None


def test_full_happy_path_ready_on_first_poll(monkeypatch):
    _configure(monkeypatch)
    calls = {"post": [], "get": []}

    def fake_post(url, **kw):
        calls["post"].append((url, kw))
        return _resp(url, {"collection_id": "job_1"})

    def fake_get(url, **kw):
        calls["get"].append(url)
        return _resp(url, [{"description": "דירה מדהימה עם נוף"}])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result == "דירה מדהימה עם נוף"
    post_url, post_kwargs = calls["post"][0]
    assert post_url == bright_data_client._TRIGGER_URL
    assert post_kwargs["params"] == {"collector": "c_abc123", "queue_next": "1"}
    assert post_kwargs["json"] == [{"url": "https://yad2.co.il/item/1"}]
    assert post_kwargs["headers"]["Authorization"] == "Bearer key123"


def test_polls_until_result_is_ready(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(bright_data_client, "_POLL_INTERVAL_SECONDS", 0)
    responses = iter([[], [], [{"description": "טקסט"}]])  # empty = still running

    def fake_post(url, **kw):
        return _resp(url, {"collection_id": "job_1"})

    def fake_get(url, **kw):
        return _resp(url, next(responses))

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result == "טקסט"


def test_returns_none_on_poll_timeout(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(bright_data_client, "_POLL_TIMEOUT_SECONDS", 0)

    def fake_post(url, **kw):
        return _resp(url, {"collection_id": "job_1"})

    def fake_get(url, **kw):
        return _resp(url, [])  # never becomes non-empty

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result is None


def test_returns_none_when_trigger_call_fails(monkeypatch):
    _configure(monkeypatch)

    def fake_post(url, **kw):
        raise httpx.ConnectError("boom", request=httpx.Request("POST", url))

    with patch.object(httpx, "post", fake_post):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result is None


def test_returns_none_when_trigger_response_has_no_recognizable_job_id(monkeypatch):
    _configure(monkeypatch)

    def fake_post(url, **kw):
        return _resp(url, {"unrelated": "x"})

    with patch.object(httpx, "post", fake_post):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result is None


def test_trigger_job_id_tries_fallback_key_names(monkeypatch):
    _configure(monkeypatch)

    def fake_post(url, **kw):
        return _resp(url, {"job_id": "job_2"})  # not collection_id/response_id, still recognized

    def fake_get(url, **kw):
        assert kw["params"] == {"id": "job_2"}
        return _resp(url, [{"description": "טקסט"}])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result == "טקסט"


def test_returns_none_for_empty_result(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(bright_data_client, "_POLL_TIMEOUT_SECONDS", 0)

    def fake_post(url, **kw):
        return _resp(url, {"collection_id": "job_1"})

    def fake_get(url, **kw):
        return _resp(url, [])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result is None


def test_uses_configured_field_name_first(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv(bright_data_client.DESCRIPTION_FIELD_ENV_VAR, "listing_text")

    def fake_post(url, **kw):
        return _resp(url, {"collection_id": "job_1"})

    def fake_get(url, **kw):
        return _resp(url, [{"listing_text": "התיאור הנכון", "description": "לא זה"}])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result == "התיאור הנכון"


def test_falls_back_to_common_field_names(monkeypatch):
    _configure(monkeypatch)

    def fake_post(url, **kw):
        return _resp(url, {"collection_id": "job_1"})

    def fake_get(url, **kw):
        return _resp(url, [{"text": "טקסט חלופי"}])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result == "טקסט חלופי"


def test_falls_back_to_searchtext_when_description_missing(monkeypatch):
    # 2026-09-12: searchText confirmed live as a second, real free-text field on a Yad2 listing
    # detail page, distinct from metaData.description (see PROJECT_STATE.md) — a defensive
    # fallback, tried after the other common keys since description is the cleaner field when
    # both are present (test_full_happy_path_ready_on_first_poll already covers that case).
    _configure(monkeypatch)

    def fake_post(url, **kw):
        return _resp(url, {"collection_id": "job_1"})

    def fake_get(url, **kw):
        return _resp(url, [{"searchText": "טקסט חיפוש עם פרטי הנכס"}])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result == "טקסט חיפוש עם פרטי הנכס"


def test_returns_none_when_no_recognizable_field(monkeypatch):
    _configure(monkeypatch)

    def fake_post(url, **kw):
        return _resp(url, {"collection_id": "job_1"})

    def fake_get(url, **kw):
        return _resp(url, [{"unrelated_field": "x"}])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result is None


# --- fetch_listing_detail_via_bright_data (2026-09-12) ---


def test_detail_returns_none_when_not_configured():
    assert bright_data_client.fetch_listing_detail_via_bright_data("https://yad2.co.il/item/1") is None


def test_detail_returns_full_row_not_just_description(monkeypatch):
    _configure(monkeypatch)
    real_row = {
        "token": "rccfe1nk",
        "price": 7500,
        "additionalDetails": {"roomsCount": 2.5, "buildingTopFloor": 4},
        "inProperty": {"includeElevator": True},
        "metaData": {"description": "דירה יפה", "images": ["https://img.yad2.co.il/1.jpeg"]},
        "customer": {"agencyName": "דאון גרוף"},
        "searchText": "טקסט חיפוש ארוך יותר",
    }

    def fake_post(url, **kw):
        return _resp(url, {"collection_id": "job_1"})

    def fake_get(url, **kw):
        return _resp(url, [real_row])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_detail_via_bright_data("https://yad2.co.il/item/1")

    assert result == real_row  # the WHOLE record, not narrowed down to one field


def test_detail_returns_none_on_failure_same_as_description_fetch(monkeypatch):
    _configure(monkeypatch)

    def fake_post(url, **kw):
        raise httpx.ConnectError("boom", request=httpx.Request("POST", url))

    with patch.object(httpx, "post", fake_post):
        result = bright_data_client.fetch_listing_detail_via_bright_data("https://yad2.co.il/item/1")

    assert result is None


def test_detail_returns_none_for_non_dict_row(monkeypatch):
    _configure(monkeypatch)

    def fake_post(url, **kw):
        return _resp(url, {"collection_id": "job_1"})

    def fake_get(url, **kw):
        return _resp(url, ["not a dict"])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_detail_via_bright_data("https://yad2.co.il/item/1")

    assert result is None


# --- fetch_via_web_unlocker (2026-09-13) — a different Bright Data product (Web Unlocker API,
# single POST) from the DCA trigger/poll flow above. Confirmed live against real Yad2 URLs that
# ZenRows itself rejected at every tier — see this function's own module docstring.


def test_web_unlocker_returns_none_when_api_key_not_set():
    assert bright_data_client.fetch_via_web_unlocker("https://example.com") is None


def test_web_unlocker_happy_path_uses_default_zone_and_raw_format(monkeypatch):
    monkeypatch.setenv(bright_data_client.API_KEY_ENV_VAR, "key123")
    monkeypatch.delenv(bright_data_client.WEB_UNLOCKER_ZONE_ENV_VAR, raising=False)
    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["kw"] = kw
        return httpx.Response(200, text="<html>real page</html>", request=httpx.Request("POST", url))

    with patch.object(httpx, "post", fake_post):
        result = bright_data_client.fetch_via_web_unlocker("https://www.yad2.co.il/realestate/rent/x")

    assert result == "<html>real page</html>"
    assert captured["url"] == bright_data_client._WEB_UNLOCKER_URL
    assert captured["kw"]["json"] == {
        "zone": "web_unlocker1",
        "url": "https://www.yad2.co.il/realestate/rent/x",
        "format": "raw",
    }
    assert captured["kw"]["headers"]["Authorization"] == "Bearer key123"


def test_web_unlocker_uses_configured_zone_override(monkeypatch):
    monkeypatch.setenv(bright_data_client.API_KEY_ENV_VAR, "key123")
    monkeypatch.setenv(bright_data_client.WEB_UNLOCKER_ZONE_ENV_VAR, "my_custom_zone")
    captured = {}

    def fake_post(url, **kw):
        captured["zone"] = kw["json"]["zone"]
        return httpx.Response(200, text="ok", request=httpx.Request("POST", url))

    with patch.object(httpx, "post", fake_post):
        bright_data_client.fetch_via_web_unlocker("https://example.com")

    assert captured["zone"] == "my_custom_zone"


def test_web_unlocker_explicit_zone_argument_wins_over_env(monkeypatch):
    monkeypatch.setenv(bright_data_client.API_KEY_ENV_VAR, "key123")
    monkeypatch.setenv(bright_data_client.WEB_UNLOCKER_ZONE_ENV_VAR, "env_zone")
    captured = {}

    def fake_post(url, **kw):
        captured["zone"] = kw["json"]["zone"]
        return httpx.Response(200, text="ok", request=httpx.Request("POST", url))

    with patch.object(httpx, "post", fake_post):
        bright_data_client.fetch_via_web_unlocker("https://example.com", zone="explicit_zone")

    assert captured["zone"] == "explicit_zone"


def test_web_unlocker_non_200_returns_none(monkeypatch):
    monkeypatch.setenv(bright_data_client.API_KEY_ENV_VAR, "key123")

    def fake_post(url, **kw):
        return httpx.Response(400, text='{"code":"zone not found"}', request=httpx.Request("POST", url))

    with patch.object(httpx, "post", fake_post):
        result = bright_data_client.fetch_via_web_unlocker("https://example.com")

    assert result is None


def test_web_unlocker_network_failure_returns_none_not_raise(monkeypatch):
    monkeypatch.setenv(bright_data_client.API_KEY_ENV_VAR, "key123")

    def fake_post(url, **kw):
        raise httpx.ConnectError("boom", request=httpx.Request("POST", url))

    with patch.object(httpx, "post", fake_post):
        result = bright_data_client.fetch_via_web_unlocker("https://example.com")

    assert result is None


# --- fetch_via_isp_proxy (2026-09-13) — a plain authenticated HTTP proxy (Bright Data ISP
# proxies), the working alternative found the same day Web Unlocker hit a real KYC wall. Confirmed
# live against a real Yad2 endpoint — see this function's own module docstring.


def _isp_configure(monkeypatch):
    monkeypatch.setenv(bright_data_client.ISP_PROXY_HOST_ENV_VAR, "brd.superproxy.io:44445")
    monkeypatch.setenv(bright_data_client.ISP_PROXY_USER_ENV_VAR, "brd-customer-x-zone-isp_proxy1")
    monkeypatch.setenv(bright_data_client.ISP_PROXY_PASS_ENV_VAR, "secret123")


def test_isp_proxy_returns_none_when_any_of_the_three_env_vars_missing(monkeypatch):
    # Host set, user/pass missing - still unconfigured.
    monkeypatch.setenv(bright_data_client.ISP_PROXY_HOST_ENV_VAR, "brd.superproxy.io:44445")
    assert bright_data_client.fetch_via_isp_proxy("https://example.com") is None


def test_isp_proxy_happy_path_builds_the_right_proxy_url(monkeypatch):
    _isp_configure(monkeypatch)
    captured = {}

    def fake_get(url, *, proxy, timeout):
        captured["url"] = url
        captured["proxy"] = proxy
        return httpx.Response(200, text='{"data":{"markers":[]}}', request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    result = bright_data_client.fetch_via_isp_proxy("https://gw.yad2.co.il/x")

    assert result == '{"data":{"markers":[]}}'
    assert captured["url"] == "https://gw.yad2.co.il/x"
    assert captured["proxy"] == "http://brd-customer-x-zone-isp_proxy1:secret123@brd.superproxy.io:44445"


def test_isp_proxy_non_200_returns_none(monkeypatch):
    _isp_configure(monkeypatch)

    def fake_get(url, *, proxy, timeout):
        return httpx.Response(403, text="forbidden", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert bright_data_client.fetch_via_isp_proxy("https://example.com") is None


def test_isp_proxy_network_failure_returns_none_not_raise(monkeypatch):
    _isp_configure(monkeypatch)

    def fake_get(url, *, proxy, timeout):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert bright_data_client.fetch_via_isp_proxy("https://example.com") is None
