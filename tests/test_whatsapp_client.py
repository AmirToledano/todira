"""Tests for todira_common/whatsapp_client.py's send_text_message — the fail-soft contract (never
raises, returns False on any failure) matching todira_common/gemini_client.py's pattern.

Moved from website/whatsapp_client.py 2026-09-08 (now shared with scraper/notifier.py — see that
module's own docstring); conftest.py already puts `common/` on sys.path for every test.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import httpx
from todira_common import whatsapp_client

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")


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

    with patch.object(whatsapp_client._http_client, "post", return_value=_FakeResponse()) as post_mock:
        assert whatsapp_client.send_text_message("972550000000", "hi") is True

    call_kwargs = post_mock.call_args.kwargs
    assert call_kwargs["json"]["to"] == "972550000000"
    assert call_kwargs["json"]["text"]["body"] == "hi"
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert "123456" in post_mock.call_args.args[0]


def test_returns_false_on_http_error(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    with patch.object(whatsapp_client._http_client, "post", side_effect=httpx.ConnectError("boom")):
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

    with patch.object(whatsapp_client._http_client, "post", return_value=_FakeResponse()) as post_mock:
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

    with patch.object(whatsapp_client._http_client, "post", side_effect=httpx.ConnectError("boom")):
        assert whatsapp_client.mark_as_read_with_typing_indicator("wamid.abc") is False


# --- 2026-09-06 speed pass: a single reused httpx.Client (connection keep-alive) instead of a
# fresh TCP+TLS handshake on every call ---


def test_send_text_message_and_typing_indicator_share_one_http_client(monkeypatch):
    """Both calls must go through the SAME httpx.Client instance so the connection opened by
    whichever fires first (almost always the typing indicator) is reused by the other — a
    per-call httpx.post() would pay a fresh handshake on every single request instead."""
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

    with patch.object(whatsapp_client._http_client, "post", return_value=_FakeResponse()) as post_mock:
        whatsapp_client.mark_as_read_with_typing_indicator("wamid.abc")
        whatsapp_client.send_text_message("972550000000", "hi")

    assert post_mock.call_count == 2  # both routed through the one shared client's .post


def test_http_client_is_a_real_persistent_httpx_client():
    assert isinstance(whatsapp_client._http_client, httpx.Client)


# --- send_cta_url_message (2026-09-06 tappable-button feature, matches the reference competitor
# bot's own "עדכון סינון ⚙️" button instead of a bare https:// link sitting in the message text) ---


def test_cta_url_returns_false_when_credentials_not_configured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    assert (
        whatsapp_client.send_cta_url_message("972550000000", "body", "כפתור", "https://x.test")
        is False
    )


def test_cta_url_sends_correct_payload_on_success(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

    with patch.object(whatsapp_client._http_client, "post", return_value=_FakeResponse()) as post_mock:
        assert (
            whatsapp_client.send_cta_url_message(
                "972550000000", "כבר יש לך פילטר", "✏️ עריכת הסינון", "https://todira.app/filter?wid=972550000000"
            )
            is True
        )

    call_kwargs = post_mock.call_args.kwargs
    assert call_kwargs["json"] == {
        "messaging_product": "whatsapp",
        "to": "972550000000",
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {"text": "כבר יש לך פילטר"},
            "action": {
                "name": "cta_url",
                "parameters": {
                    "display_text": "✏️ עריכת הסינון",
                    "url": "https://todira.app/filter?wid=972550000000",
                },
            },
        },
    }
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-token"


def test_cta_url_returns_false_on_http_error(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    with patch.object(whatsapp_client._http_client, "post", side_effect=httpx.ConnectError("boom")):
        assert (
            whatsapp_client.send_cta_url_message("972550000000", "body", "כפתור", "https://x.test")
            is False
        )


# --- send_template_message (2026-09-08 proactive-notification feature) ---


def test_template_returns_false_when_credentials_not_configured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    assert (
        whatsapp_client.send_template_message(
            "972550000000", template_name="new_listing_match", language_code="he", body_params=["x"]
        )
        is False
    )


def test_template_sends_correct_payload_on_success(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

    with patch.object(whatsapp_client._http_client, "post", return_value=_FakeResponse()) as post_mock:
        assert (
            whatsapp_client.send_template_message(
                "972550000000",
                template_name="new_listing_match",
                language_code="he",
                body_params=["רוטשילד, תל אביב", "3", "5,500", "https://todira.app/apartments"],
            )
            is True
        )

    call_kwargs = post_mock.call_args.kwargs
    assert call_kwargs["json"] == {
        "messaging_product": "whatsapp",
        "to": "972550000000",
        "type": "template",
        "template": {
            "name": "new_listing_match",
            "language": {"code": "he"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "רוטשילד, תל אביב"},
                        {"type": "text", "text": "3"},
                        {"type": "text", "text": "5,500"},
                        {"type": "text", "text": "https://todira.app/apartments"},
                    ],
                }
            ],
        },
    }
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert "123456" in post_mock.call_args.args[0]


def test_template_returns_false_on_http_error(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    with patch.object(whatsapp_client._http_client, "post", side_effect=httpx.ConnectError("boom")):
        assert (
            whatsapp_client.send_template_message(
                "972550000000", template_name="new_listing_match", language_code="he", body_params=["x"]
            )
            is False
        )


# --- send_template_message's optional header image / dynamic button (2026-09-27, the rich
# per-listing card) — both default to None so every test above (the plain 3-variable template)
# stays completely unaffected. ---


def test_template_with_header_image_adds_a_header_component_first(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

    with patch.object(whatsapp_client._http_client, "post", return_value=_FakeResponse()) as post_mock:
        assert (
            whatsapp_client.send_template_message(
                "972550000000",
                template_name="new_listing_match_rich",
                language_code="he",
                body_params=["רוטשילד", "5,500"],
                header_image_media_id="media-id-123",
            )
            is True
        )

    components = post_mock.call_args.kwargs["json"]["template"]["components"]
    assert components[0] == {
        "type": "header",
        "parameters": [{"type": "image", "image": {"id": "media-id-123"}}],
    }
    assert components[1]["type"] == "body"


def test_template_with_button_url_param_adds_a_button_component_last(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

    with patch.object(whatsapp_client._http_client, "post", return_value=_FakeResponse()) as post_mock:
        whatsapp_client.send_template_message(
            "972550000000",
            template_name="new_listing_match_rich",
            language_code="he",
            body_params=["רוטשילד"],
            button_url_param="42&wid=abc123",
        )

    components = post_mock.call_args.kwargs["json"]["template"]["components"]
    assert components[-1] == {
        "type": "button",
        "sub_type": "url",
        "index": "0",
        "parameters": [{"type": "text", "text": "42&wid=abc123"}],
    }


# --- upload_media (2026-09-27, the rich per-listing card's dynamic header image) ---


def test_upload_media_returns_none_when_credentials_not_configured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    assert whatsapp_client.upload_media(b"fake-jpeg-bytes") is None


def test_upload_media_returns_the_id_on_success(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "media-id-999"}

    with patch.object(whatsapp_client._http_client, "post", return_value=_FakeResponse()) as post_mock:
        assert whatsapp_client.upload_media(b"fake-jpeg-bytes") == "media-id-999"

    assert "123456" in post_mock.call_args.args[0]
    assert post_mock.call_args.kwargs["data"] == {
        "messaging_product": "whatsapp",
        "type": "image/jpeg",
    }


def test_upload_media_returns_none_on_http_error(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    with patch.object(whatsapp_client._http_client, "post", side_effect=httpx.ConnectError("boom")):
        assert whatsapp_client.upload_media(b"fake-jpeg-bytes") is None
