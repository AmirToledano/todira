"""Tests for scraper/bright_data_client.py — the (partially verified against Bright Data's public
GitHub reference, see that module's own docstring) trigger/poll/snapshot flow, and
fetch_listing_description()'s tolerant field-name parsing / failure modes.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"
if str(_SCRAPER_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRAPER_DIR))

import bright_data_client  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        bright_data_client.API_KEY_ENV_VAR,
        bright_data_client.DATASET_ID_ENV_VAR,
        bright_data_client.DESCRIPTION_FIELD_ENV_VAR,
    ):
        monkeypatch.delenv(var, raising=False)


def _configure(monkeypatch):
    monkeypatch.setenv(bright_data_client.API_KEY_ENV_VAR, "key123")
    monkeypatch.setenv(bright_data_client.DATASET_ID_ENV_VAR, "ds_abc")


def _resp(url, json_body, status=200):
    return httpx.Response(status, json=json_body, request=httpx.Request("GET", url))


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
        return _resp(url, {"snapshot_id": "snap_1"})

    def fake_get(url, **kw):
        calls["get"].append(url)
        if "progress" in url:
            return _resp(url, {"status": "ready"})
        return _resp(url, [{"description": "דירה מדהימה עם נוף"}])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result == "דירה מדהימה עם נוף"
    post_url, post_kwargs = calls["post"][0]
    assert post_url == bright_data_client._TRIGGER_URL
    assert post_kwargs["params"]["dataset_id"] == "ds_abc"
    assert post_kwargs["json"] == {"input": [{"url": "https://yad2.co.il/item/1"}]}
    assert post_kwargs["headers"]["Authorization"] == "Bearer key123"


def test_polls_until_ready(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(bright_data_client, "_POLL_INTERVAL_SECONDS", 0)
    statuses = iter(["starting", "running", "ready"])

    def fake_post(url, **kw):
        return _resp(url, {"snapshot_id": "snap_1"})

    def fake_get(url, **kw):
        if "progress" in url:
            return _resp(url, {"status": next(statuses)})
        return _resp(url, [{"description": "טקסט"}])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result == "טקסט"


def test_returns_none_when_snapshot_reports_failed(monkeypatch):
    _configure(monkeypatch)

    def fake_post(url, **kw):
        return _resp(url, {"snapshot_id": "snap_1"})

    def fake_get(url, **kw):
        return _resp(url, {"status": "failed"})

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result is None


def test_returns_none_on_poll_timeout(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(bright_data_client, "_POLL_TIMEOUT_SECONDS", 0)

    def fake_post(url, **kw):
        return _resp(url, {"snapshot_id": "snap_1"})

    def fake_get(url, **kw):
        return _resp(url, {"status": "running"})  # never becomes ready

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


def test_returns_none_for_empty_snapshot(monkeypatch):
    _configure(monkeypatch)

    def fake_post(url, **kw):
        return _resp(url, {"snapshot_id": "snap_1"})

    def fake_get(url, **kw):
        if "progress" in url:
            return _resp(url, {"status": "ready"})
        return _resp(url, [])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result is None


def test_uses_configured_field_name_first(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv(bright_data_client.DESCRIPTION_FIELD_ENV_VAR, "listing_text")

    def fake_post(url, **kw):
        return _resp(url, {"snapshot_id": "snap_1"})

    def fake_get(url, **kw):
        if "progress" in url:
            return _resp(url, {"status": "ready"})
        return _resp(url, [{"listing_text": "התיאור הנכון", "description": "לא זה"}])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result == "התיאור הנכון"


def test_falls_back_to_common_field_names(monkeypatch):
    _configure(monkeypatch)

    def fake_post(url, **kw):
        return _resp(url, {"snapshot_id": "snap_1"})

    def fake_get(url, **kw):
        if "progress" in url:
            return _resp(url, {"status": "ready"})
        return _resp(url, [{"text": "טקסט חלופי"}])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result == "טקסט חלופי"


def test_returns_none_when_no_recognizable_field(monkeypatch):
    _configure(monkeypatch)

    def fake_post(url, **kw):
        return _resp(url, {"snapshot_id": "snap_1"})

    def fake_get(url, **kw):
        if "progress" in url:
            return _resp(url, {"status": "ready"})
        return _resp(url, [{"unrelated_field": "x"}])

    with patch.object(httpx, "post", fake_post), patch.object(httpx, "get", fake_get):
        result = bright_data_client.fetch_listing_description("https://yad2.co.il/item/1")

    assert result is None
