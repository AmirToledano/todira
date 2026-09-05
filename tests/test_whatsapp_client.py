"""Tests for website/whatsapp_client.py's send_text_message — the fail-soft contract (never
raises, returns False on any failure) matching dorin_common/gemini_client.py's pattern.
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

import whatsapp_client  # noqa: E402


def test_returns_false_when_credentials_not_configured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    assert whatsapp_client.send_text_message("972550000000", "hi") is False


def test_returns_true_on_successful_send(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

    with patch.object(httpx, "post", return_value=_FakeResponse()) as post_mock:
        assert whatsapp_client.send_text_message("972550000000", "hi") is True

    call_kwargs = post_mock.call_args.kwargs
    assert call_kwargs["json"]["to"] == "972550000000"
    assert call_kwargs["json"]["text"]["body"] == "hi"
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert "123456" in post_mock.call_args.args[0]


def test_returns_false_on_http_error(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    with patch.object(httpx, "post", side_effect=httpx.ConnectError("boom")):
        assert whatsapp_client.send_text_message("972550000000", "hi") is False


# --- mark_as_read_with_typing_indicator (2026-09-06 typing bubble feature) ---


def test_typing_indicator_returns_false_when_credentials_not_configured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    assert whatsapp_client.mark_as_read_with_typing_indicator("wamid.abc") is False


def test_typing_indicator_sends_correct_payload_on_success(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

    with patch.object(httpx, "post", return_value=_FakeResponse()) as post_mock:
        assert whatsapp_client.mark_as_read_with_typing_indicator("wamid.abc") is True

    call_kwargs = post_mock.call_args.kwargs
    assert call_kwargs["json"] == {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": "wamid.abc",
        "typing_indicator": {"type": "text"},
    }
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert "123456" in post_mock.call_args.args[0]


def test_typing_indicator_returns_false_on_http_error(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    with patch.object(httpx, "post", side_effect=httpx.ConnectError("boom")):
        assert whatsapp_client.mark_as_read_with_typing_indicator("wamid.abc") is False
