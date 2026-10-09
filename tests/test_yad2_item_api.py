"""todira_common.yad2_item_api (2026-10-09): Yad2 listing details from Yad2's own item JSON, and todira_common.yad2_detail
(the item JSON first, Gemini as backup). The record shape below is the one the live probe printed (60 of 60 answered 200)."""
from __future__ import annotations

import datetime as dt
import sys
import types

import pytest

from todira_common import yad2_detail, yad2_item_api as api

_TOKEN = "abc123x"
_URL = f"https://www.yad2.co.il/item/{_TOKEN}"
_FUTURE = dt.date.today() + dt.timedelta(days=30)


def _record(**sections):
    base = {
        "token": _TOKEN,
        "additionalDetails": {
            "buildingTopFloor": 3,
            "entranceDate": _FUTURE.isoformat() + "T00:00:00",
            "property": {"id": 1, "text": "דירה", "textEng": "apartment"},
        },
        "inProperty": {
            "includeParking": True,
            "includeBalcony": True,
            "includeElevator": False,
            "includeSecurityRoom": False,
            "includeBuildingShelter": False,
        },
        "metaData": {"description": "דירה יפה ומוארת", "images": ["https://img.yad2.co.il/1.jpeg"]},
        "customer": {"name": "x"},
        "searchText": "טקסט חיפוש",
    }
    base.update(sections)
    return base


# --- the mapping -------------------------------------------------------------------------------------------------


def test_a_full_record_maps_to_every_card_field():
    updates = api.detail_updates_from_item(_record())
    assert updates["description"] == "דירה יפה ומוארת"
    assert updates["floor_total"] == 3
    assert updates["move_in_date"] == _FUTURE
    assert updates["has_parking"] is True and updates["has_balcony"] is True and updates["has_elevator"] is False
    assert updates["safe_room_type"] == "none"
    assert updates["property_type"] == "apartment"
    assert updates["image_urls"] == ["https://img.yad2.co.il/1.jpeg"]


def test_extra_amenities_pets_renovated_roommates_furniture():
    updates = api.detail_updates_from_item(
        _record(inProperty={"isPetsAllowed": True, "isRenovated": True, "isForPartners": True, "includeFurniture": True})
    )
    assert updates["pets_allowed"] is True
    assert updates["is_renovated"] is True
    assert updates["is_roommate_friendly"] is True
    assert updates["furniture"] == "furnished"
    assert api.detail_updates_from_item(_record(inProperty={"includeFurniture": False}))["furniture"] == "unfurnished"


def test_safe_room_building_shelter_and_none():
    assert api.detail_updates_from_item(_record(inProperty={"includeSecurityRoom": True}))["safe_room_type"] == "safe_room"
    shelter = api.detail_updates_from_item(
        _record(inProperty={"includeSecurityRoom": False, "includeBuildingShelter": True})
    )
    assert shelter["safe_room_type"] == "building_shelter"
    assert "safe_room_type" not in api.detail_updates_from_item(_record(inProperty={"includeParking": True}))


def test_a_flag_the_record_does_not_state_is_absent_never_false():
    updates = api.detail_updates_from_item(_record(inProperty={"includeParking": True}))
    assert "has_elevator" not in updates and "pets_allowed" not in updates and "furniture" not in updates


def test_entrance_date_future_is_a_date_past_is_the_immediate_note():
    past = api.detail_updates_from_item(_record(additionalDetails={"entranceDate": "2020-01-01T00:00:00"}))
    assert "move_in_date" not in past and past["move_in_note"] == "מיידית"
    today = api.detail_updates_from_item(
        _record(additionalDetails={"entranceDate": dt.date.today().isoformat() + "T00:00:00"})
    )
    assert "move_in_date" not in today and today["move_in_note"] == "מיידית"


def test_no_entrance_date_uses_the_immediate_and_flexible_flags():
    immediate = api.detail_updates_from_item(
        _record(additionalDetails={}, inProperty={"isImmediateEntrance": True})
    )
    assert immediate["move_in_note"] == "מיידית"
    flexible = api.detail_updates_from_item(_record(additionalDetails={"isEnterDateFlexible": True}, inProperty={}))
    assert flexible["move_in_note"] == "גמיש"
    nothing = api.detail_updates_from_item(_record(additionalDetails={}, inProperty={}))
    assert "move_in_note" not in nothing and "move_in_date" not in nothing


def test_description_falls_back_to_search_text_and_is_capped():
    only_search = api.detail_updates_from_item(_record(metaData={}))
    assert only_search["description"] == "טקסט חיפוש"
    long_text = api.detail_updates_from_item(_record(metaData={"description": "א" * 9000}))
    assert len(long_text["description"]) == 4000


def test_implausible_values_are_ignored_and_junk_never_raises():
    updates = api.detail_updates_from_item(
        _record(additionalDetails={"buildingTopFloor": 999, "entranceDate": "not a date"})
    )
    assert "floor_total" not in updates and "move_in_date" not in updates
    assert api.detail_updates_from_item({}) == {}
    assert api.detail_updates_from_item(
        {"additionalDetails": "x", "inProperty": None, "metaData": [1], "customer": 5}
    ) == {}


def test_an_agency_name_marks_the_listing_as_broker_but_its_absence_proves_nothing():
    assert api.detail_updates_from_item(_record(customer={"agencyName": "promise"}))["is_broker_listing"] is True
    assert "is_broker_listing" not in api.detail_updates_from_item(_record())


def test_token_from_url():
    assert api.token_from_url(_URL) == _TOKEN
    assert api.token_from_url("https://www.yad2.co.il/realestate/item/xyz9?x=1") == "xyz9"
    assert api.token_from_url("https://example.com/other") is None
    assert api.token_from_url("") is None


# --- the HTTP side (curl_cffi is faked: it is not installed in the test environment) ---------------------------------


class _Response:
    def __init__(self, status=200, payload=None, json_error=False):
        self.status_code = status
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._payload


@pytest.fixture
def fake_http(monkeypatch):
    calls = []
    responses = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        item = responses.pop(0) if responses else _Response(200, {"data": _record()})
        if isinstance(item, Exception):
            raise item
        return item

    module = types.ModuleType("curl_cffi")
    module.requests = types.SimpleNamespace(get=get)
    monkeypatch.setitem(sys.modules, "curl_cffi", module)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", module.requests)
    monkeypatch.setenv(api.ENABLED_ENV_VAR, "true")
    monkeypatch.setenv(api.MIN_SPACING_ENV_VAR, "0")
    monkeypatch.setattr(api, "_consecutive_failures", 0)
    monkeypatch.setattr(api, "_consecutive_events", 0)
    monkeypatch.setattr(api, "_blocked_until", 0.0)
    sleeps = []
    monkeypatch.setattr(api.time, "sleep", lambda seconds: sleeps.append(seconds))
    return types.SimpleNamespace(calls=calls, responses=responses, sleeps=sleeps)


def test_disabled_without_the_env_flag(monkeypatch):
    monkeypatch.delenv(api.ENABLED_ENV_VAR, raising=False)
    assert api.is_enabled() is False
    assert api.fetch_yad2_detail_updates(_URL) is None


def test_disabled_without_curl_cffi(monkeypatch):
    monkeypatch.setenv(api.ENABLED_ENV_VAR, "true")
    monkeypatch.setitem(sys.modules, "curl_cffi", None)  # makes `import curl_cffi` raise ImportError
    assert api.is_enabled() is False


def test_fetches_the_item_endpoint_with_a_browser_fingerprint(fake_http):
    updates = api.fetch_yad2_detail_updates(_URL)
    assert updates["description"] == "דירה יפה ומוארת"
    url, kwargs = fake_http.calls[0]
    assert url == f"https://gw.yad2.co.il/realestate-item/{_TOKEN}"
    assert kwargs["impersonate"] == "chrome"
    assert kwargs["allow_redirects"] is False


def test_a_url_without_a_token_makes_no_request(fake_http):
    assert api.fetch_yad2_detail_updates("https://example.com/x") is None
    assert fake_http.calls == []


def test_a_gone_ad_is_a_definitive_empty_answer(fake_http):
    fake_http.responses.extend([_Response(404), _Response(410)])
    assert api.fetch_yad2_detail_updates(_URL) == {}
    assert api.fetch_yad2_detail_updates(_URL) == {}


_WAF_EVENT = {"_event_clientip": "x", "_event_clientport": 1, "_event_transid": "y"}


def test_a_request_that_keeps_failing_is_retried_twice_then_returns_none(fake_http):
    fake_http.responses.extend([_Response(403)] * 3)
    assert api.fetch_yad2_detail_updates(_URL) is None
    assert len(fake_http.calls) == 3
    assert fake_http.sleeps == [8.0, 20.0]  # the back-off between attempts


def test_three_failed_requests_in_a_row_pause_the_fetcher(fake_http):
    fake_http.responses.extend([_Response(403)] * 9)
    for _ in range(3):
        assert api.fetch_yad2_detail_updates(_URL) is None
    assert len(fake_http.calls) == 9
    assert api.fetch_yad2_detail_updates(_URL) is None  # paused: no tenth request
    assert len(fake_http.calls) == 9


def test_a_not_the_ad_event_answer_is_a_definitive_empty_result_for_that_ad(fake_http):
    """Measured on the production IP: 4 of the 40 oldest active ads answer HTTP 200 with only _event_* keys, the SAME ad stays that
    way on retries and a fresh ad right after is read normally - so it is tied to the ad, never retried and never a failure."""
    fake_http.responses.append(_Response(200, _WAF_EVENT))
    assert api.fetch_yad2_detail_updates(_URL) == {}
    assert len(fake_http.calls) == 1 and fake_http.sleeps == []
    assert api._consecutive_failures == 0


def test_an_event_answer_does_not_stop_the_next_ads_from_being_read(fake_http):
    fake_http.responses.extend([_Response(200, _WAF_EVENT), _Response(200, {"data": _record()})])
    assert api.fetch_yad2_detail_updates(_URL) == {}
    assert api.fetch_yad2_detail_updates(_URL)["description"] == "דירה יפה ומוארת"


def test_five_event_answers_in_a_row_look_like_an_ip_block_and_pause_the_fetcher(fake_http):
    fake_http.responses.extend([_Response(200, _WAF_EVENT)] * 5)
    for _ in range(4):
        assert api.fetch_yad2_detail_updates(_URL) == {}
    assert api.fetch_yad2_detail_updates(_URL) is None  # the fifth: nothing is marked, the fetcher pauses
    assert len(fake_http.calls) == 5
    assert api.fetch_yad2_detail_updates(_URL) is None  # paused: no sixth request
    assert len(fake_http.calls) == 5


def test_a_good_answer_resets_the_event_streak(fake_http):
    fake_http.responses.extend(
        [_Response(200, _WAF_EVENT)] * 4 + [_Response(200, {"data": _record()})] + [_Response(200, _WAF_EVENT)] * 4
    )
    for _ in range(4):
        assert api.fetch_yad2_detail_updates(_URL) == {}
    assert api.fetch_yad2_detail_updates(_URL) is not None
    for _ in range(4):
        assert api.fetch_yad2_detail_updates(_URL) == {}  # streak restarted: still under five


def test_one_good_answer_after_retries_resets_the_failure_streak(fake_http):
    fake_http.responses.extend([_Response(403)] * 6 + [_Response(200, {"data": _record()})])
    assert api.fetch_yad2_detail_updates(_URL) is None
    assert api.fetch_yad2_detail_updates(_URL) is None
    assert api.fetch_yad2_detail_updates(_URL) is not None  # streak was 2 of 3: not paused, and now back to 0
    fake_http.responses.extend([_Response(403)] * 6)
    assert api.fetch_yad2_detail_updates(_URL) is None
    assert api.fetch_yad2_detail_updates(_URL) is None
    assert api._blocked_until == 0.0  # only two failures since the success: still not paused


def test_network_errors_and_bad_bodies_are_retried_too(fake_http):
    fake_http.responses.extend(
        [ConnectionError("boom"), _Response(200, json_error=True), _Response(200, {"message": "no data"})]
    )  # a JSON with neither a data record nor the _event_ keys is an unknown answer: retried like any failure
    assert api.fetch_yad2_detail_updates(_URL) is None
    assert len(fake_http.calls) == 3


def test_the_default_spacing_between_requests_is_one_second(monkeypatch):
    monkeypatch.delenv(api.MIN_SPACING_ENV_VAR, raising=False)
    assert api._min_spacing() == 1.0


# --- the combined entry point ------------------------------------------------------------------------------------


def test_combined_uses_the_item_json_and_skips_gemini_when_it_answers(monkeypatch):
    monkeypatch.setattr(yad2_detail.yad2_item_api, "is_enabled", lambda: True)
    monkeypatch.setattr(yad2_detail.yad2_item_api, "fetch_yad2_detail_updates", lambda url: {"description": "מיד2"})
    monkeypatch.setattr(yad2_detail.gemini_url_detail, "is_enabled", lambda: True)
    monkeypatch.setattr(
        yad2_detail.gemini_url_detail, "fetch_yad2_detail_updates", lambda url: pytest.fail("Gemini must not be asked")
    )
    assert yad2_detail.fetch_updates(_URL) == {"description": "מיד2"}


def test_combined_an_empty_answer_is_definitive_and_does_not_ask_gemini(monkeypatch):
    monkeypatch.setattr(yad2_detail.yad2_item_api, "is_enabled", lambda: True)
    monkeypatch.setattr(yad2_detail.yad2_item_api, "fetch_yad2_detail_updates", lambda url: {})
    monkeypatch.setattr(yad2_detail.gemini_url_detail, "is_enabled", lambda: True)
    monkeypatch.setattr(
        yad2_detail.gemini_url_detail, "fetch_yad2_detail_updates", lambda url: pytest.fail("Gemini must not be asked")
    )
    assert yad2_detail.fetch_updates(_URL) == {}


def test_combined_falls_back_to_gemini_only_when_the_item_json_gave_no_answer(monkeypatch):
    monkeypatch.setattr(yad2_detail.yad2_item_api, "is_enabled", lambda: True)
    monkeypatch.setattr(yad2_detail.yad2_item_api, "fetch_yad2_detail_updates", lambda url: None)
    monkeypatch.setattr(yad2_detail.gemini_url_detail, "is_enabled", lambda: True)
    monkeypatch.setattr(yad2_detail.gemini_url_detail, "fetch_yad2_detail_updates", lambda url: {"description": "גמיני"})
    assert yad2_detail.fetch_updates(_URL) == {"description": "גמיני"}
    monkeypatch.setattr(yad2_detail.gemini_url_detail, "is_enabled", lambda: False)
    assert yad2_detail.fetch_updates(_URL) is None


def test_combined_is_enabled_when_either_fetcher_is(monkeypatch):
    monkeypatch.setattr(yad2_detail.yad2_item_api, "is_enabled", lambda: False)
    monkeypatch.setattr(yad2_detail.gemini_url_detail, "is_enabled", lambda: False)
    assert yad2_detail.is_enabled() is False
    monkeypatch.setattr(yad2_detail.gemini_url_detail, "is_enabled", lambda: True)
    assert yad2_detail.is_enabled() is True
    monkeypatch.setattr(yad2_detail.gemini_url_detail, "is_enabled", lambda: False)
    monkeypatch.setattr(yad2_detail.yad2_item_api, "is_enabled", lambda: True)
    assert yad2_detail.is_enabled() is True
