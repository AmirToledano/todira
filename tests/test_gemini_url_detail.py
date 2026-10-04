"""todira_common.gemini_url_detail (2026-10-04): Yad2 listing details through Gemini's url_context tool."""
import datetime as dt
import json
import types

import httpx
import pytest

from todira_common import gemini_url_detail as g

_TODAY = dt.date(2026, 10, 4)
_URL = "https://www.yad2.co.il/item/abc"


def _payload(data, status="URL_RETRIEVAL_STATUS_SUCCESS"):
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": "```json\n" + json.dumps(data) + "\n```"}]},
                "urlContextMetadata": {"urlMetadata": [{"urlRetrievalStatus": status}]},
            }
        ]
    }


def test_parse_maps_page_fields_to_listing_columns():
    updates = g._parse_updates(
        _payload(
            {"ok": True, "description": "  דירה יפה  ", "building_top_floor": 6, "entrance_date": "2026-12-31",
             "parking": True, "elevator": False, "balcony": None, "safe_room": True}
        ),
        _TODAY,
    )
    assert updates == {
        "description": "דירה יפה", "floor_total": 6, "has_parking": True, "has_elevator": False,
        "safe_room_type": "safe_room", "move_in_date": dt.date(2026, 12, 31),
    }


def test_past_or_missing_entrance_date_is_not_stored_and_false_safe_room_is_none():
    updates = g._parse_updates(
        _payload({"ok": True, "description": "x", "entrance_date": "2026-06-01", "safe_room": False}), _TODAY
    )
    assert "move_in_date" not in updates
    assert updates["safe_room_type"] == "none"


@pytest.mark.parametrize(
    "payload",
    [
        _payload({"ok": True, "description": "x"}, status="URL_RETRIEVAL_STATUS_ERROR"),
        _payload({"ok": False}),
        _payload({"ok": True}),  # nothing usable
        {"candidates": []},
        {"candidates": [{"content": {"parts": [{"text": "not json"}]},
                         "urlContextMetadata": {"urlMetadata": [{"urlRetrievalStatus": "URL_RETRIEVAL_STATUS_SUCCESS"}]}}]},
    ],
)
def test_parse_rejects_unretrieved_or_unusable_responses(payload):
    assert g._parse_updates(payload, _TODAY) is None


def test_disabled_by_default_and_never_calls_the_network(monkeypatch):
    monkeypatch.delenv(g.ENABLED_ENV_VAR, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(g.httpx, "post", lambda *a, **k: pytest.fail("network call while disabled"))
    assert g.fetch_yad2_detail_updates(_URL) is None


def _enable(monkeypatch):
    monkeypatch.setenv(g.ENABLED_ENV_VAR, "true")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(g, "_paused_until", {})


def test_success_path_sends_url_context_tool_and_returns_updates(monkeypatch):
    _enable(monkeypatch)
    seen = {}

    def _post(url, **kwargs):
        seen["url"], seen["json"], seen["headers"] = url, kwargs["json"], kwargs["headers"]
        return types.SimpleNamespace(status_code=200, json=lambda: _payload({"ok": True, "description": "תיאור"}))

    monkeypatch.setattr(g.httpx, "post", _post)
    assert g.fetch_yad2_detail_updates(_URL) == {"description": "תיאור"}
    assert seen["json"]["tools"] == [{"url_context": {}}]
    assert seen["headers"]["x-goog-api-key"] == "k"
    assert _URL in seen["json"]["contents"][0]["parts"][0]["text"]


def test_429_opens_the_circuit_breaker_so_the_next_call_skips_gemini(monkeypatch):
    _enable(monkeypatch)
    calls = []
    monkeypatch.setattr(
        g.httpx, "post", lambda *a, **k: calls.append(1) or types.SimpleNamespace(status_code=429, json=lambda: {})
    )
    monkeypatch.setenv(g.MODEL_ENV_VAR, "only-model")
    assert g.fetch_yad2_detail_updates(_URL) is None
    assert g.fetch_yad2_detail_updates(_URL) is None
    assert len(calls) == 1


def test_network_error_and_server_error_return_none(monkeypatch):
    _enable(monkeypatch)

    def _boom(*a, **k):
        raise httpx.ConnectError("x")

    monkeypatch.setattr(g.httpx, "post", _boom)
    assert g.fetch_yad2_detail_updates(_URL) is None
    monkeypatch.setattr(g.httpx, "post", lambda *a, **k: types.SimpleNamespace(status_code=500, json=lambda: {}))
    assert g.fetch_yad2_detail_updates(_URL) is None


def test_a_limited_model_falls_through_to_the_next_one_and_daily_quota_pauses_it_for_hours(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv(g.MODEL_ENV_VAR, "model-a,model-b")
    seen = []

    def _post(url, **kwargs):
        seen.append(url)
        if "model-a" in url:
            return types.SimpleNamespace(
                status_code=429, text="GenerateRequestsPerDayPerProjectPerModel-FreeTier", json=lambda: {}
            )
        return types.SimpleNamespace(status_code=200, json=lambda: _payload({"ok": True, "description": "x"}))

    monkeypatch.setattr(g.httpx, "post", _post)
    assert g.fetch_yad2_detail_updates(_URL) == {"description": "x"}
    assert g.fetch_yad2_detail_updates(_URL) == {"description": "x"}
    assert [u.split("/models/")[1].split(":")[0] for u in seen] == ["model-a", "model-b", "model-b"]
    assert g._paused_until["model-a"] - g.time.monotonic() > 2 * 3600


def test_overloaded_503_tries_the_next_model_and_all_limited_returns_none(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv(g.MODEL_ENV_VAR, "model-a,model-b")
    codes = {"model-a": 503, "model-b": 429}

    def _post(url, **kwargs):
        model = url.split("/models/")[1].split(":")[0]
        return types.SimpleNamespace(status_code=codes[model], json=lambda: {})

    monkeypatch.setattr(g.httpx, "post", _post)
    assert g.fetch_yad2_detail_updates(_URL) is None


def test_default_chain_tries_flash_lite_first(monkeypatch):
    monkeypatch.delenv(g.MODEL_ENV_VAR, raising=False)
    assert g._models() == ["gemini-3.5-flash-lite", "gemini-3.6-flash"]
