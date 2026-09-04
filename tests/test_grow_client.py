"""Tests for website/grow_client.py — the (provisional, unverified against Grow's own docs — see
that module's docstring) Grow/Meshulam hosted-checkout wrapper. Covers is_configured()'s
all-three-or-nothing gate, the sandbox/live URL switch, and create_checkout_url()'s tolerant
response parsing / failure modes — NOT the real Grow API shape itself, which this sandbox's
network egress blocks fetching docs for.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

import grow_client  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        grow_client.PAGE_CODE_ENV_VAR,
        grow_client.USER_ID_ENV_VAR,
        grow_client.API_KEY_ENV_VAR,
        grow_client.SANDBOX_ENV_VAR,
    ):
        monkeypatch.delenv(var, raising=False)


def _configure(monkeypatch, sandbox=None):
    monkeypatch.setenv(grow_client.PAGE_CODE_ENV_VAR, "page123")
    monkeypatch.setenv(grow_client.USER_ID_ENV_VAR, "user456")
    monkeypatch.setenv(grow_client.API_KEY_ENV_VAR, "key789")
    if sandbox is not None:
        monkeypatch.setenv(grow_client.SANDBOX_ENV_VAR, sandbox)


# --- is_configured ---


def test_not_configured_when_all_unset():
    assert grow_client.is_configured() is False


def test_not_configured_when_only_some_are_set(monkeypatch):
    monkeypatch.setenv(grow_client.PAGE_CODE_ENV_VAR, "page123")
    monkeypatch.setenv(grow_client.USER_ID_ENV_VAR, "user456")
    assert grow_client.is_configured() is False


def test_configured_when_all_three_set(monkeypatch):
    _configure(monkeypatch)
    assert grow_client.is_configured() is True


# --- create_checkout_url ---


def test_create_checkout_url_returns_none_when_not_configured():
    result = grow_client.create_checkout_url(
        payment_id=1, amount_ils=15, description="x",
        success_url="https://x/success", cancel_url="https://x/cancel", notify_url="https://x/hook",
    )
    assert result is None


def test_create_checkout_url_uses_sandbox_endpoint_by_default(monkeypatch):
    _configure(monkeypatch)
    captured = {}

    def _fake_post(url, **kw):
        captured["url"] = url
        captured["data"] = kw.get("data")
        return httpx.Response(200, json={"url": "https://checkout.example/abc"}, request=httpx.Request("POST", url))

    with patch.object(httpx, "post", _fake_post):
        result = grow_client.create_checkout_url(
            payment_id=42, amount_ils=15, description="טודירה — מנוי שבועי",
            success_url="https://x/success", cancel_url="https://x/cancel",
            notify_url="https://x/hook",
        )

    assert result == "https://checkout.example/abc"
    assert captured["url"] == grow_client._SANDBOX_URL
    assert captured["data"]["pageCode"] == "page123"
    assert captured["data"]["userId"] == "user456"
    assert captured["data"]["apiKey"] == "key789"
    assert captured["data"]["sum"] == "15"
    assert captured["data"]["cField1"] == "42"
    assert captured["data"]["notifyUrl"] == "https://x/hook"


def test_create_checkout_url_uses_live_endpoint_when_sandbox_disabled(monkeypatch):
    _configure(monkeypatch, sandbox="false")
    captured = {}

    def _fake_post(url, **kw):
        captured["url"] = url
        return httpx.Response(200, json={"url": "https://checkout.example/live"}, request=httpx.Request("POST", url))

    with patch.object(httpx, "post", _fake_post):
        grow_client.create_checkout_url(
            payment_id=1, amount_ils=15, description="x",
            success_url="https://x/success", cancel_url="https://x/cancel", notify_url="https://x/hook",
        )

    assert captured["url"] == grow_client._LIVE_URL


def test_create_checkout_url_parses_nested_data_url(monkeypatch):
    _configure(monkeypatch)
    with patch.object(
        httpx,
        "post",
        lambda url, **kw: httpx.Response(
            200, json={"data": {"url": "https://nested/url"}}, request=httpx.Request("POST", url)
        ),
    ):
        result = grow_client.create_checkout_url(
            payment_id=1, amount_ils=15, description="x",
            success_url="https://x/success", cancel_url="https://x/cancel", notify_url="https://x/hook",
        )
    assert result == "https://nested/url"


def test_create_checkout_url_returns_none_when_no_recognizable_url_field(monkeypatch):
    _configure(monkeypatch)
    with patch.object(
        httpx,
        "post",
        lambda url, **kw: httpx.Response(200, json={"status": "ok"}, request=httpx.Request("POST", url)),
    ):
        result = grow_client.create_checkout_url(
            payment_id=1, amount_ils=15, description="x",
            success_url="https://x/success", cancel_url="https://x/cancel", notify_url="https://x/hook",
        )
    assert result is None


def test_create_checkout_url_returns_none_on_http_error(monkeypatch):
    _configure(monkeypatch)

    def _fake_post(url, **kw):
        raise httpx.ConnectError("boom", request=httpx.Request("POST", url))

    with patch.object(httpx, "post", _fake_post):
        result = grow_client.create_checkout_url(
            payment_id=1, amount_ils=15, description="x",
            success_url="https://x/success", cancel_url="https://x/cancel", notify_url="https://x/hook",
        )
    assert result is None


def test_create_checkout_url_returns_none_on_non_json_response(monkeypatch):
    _configure(monkeypatch)
    with patch.object(
        httpx,
        "post",
        lambda url, **kw: httpx.Response(200, text="not json", request=httpx.Request("POST", url)),
    ):
        result = grow_client.create_checkout_url(
            payment_id=1, amount_ils=15, description="x",
            success_url="https://x/success", cancel_url="https://x/cancel", notify_url="https://x/hook",
        )
    assert result is None
