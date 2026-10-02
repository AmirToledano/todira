"""Thin wrapper around the WhatsApp Cloud API (Meta) for sending messages.

Fails soft, same contract as bot/gemini_client.py: if WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID
aren't set, or the API call fails for any reason, every send_* function returns False and logs —
never raises. Callers (whatsapp_webhook.py, scraper/notifier.py) treat a False return as "the
message didn't go out" without crashing the whole request/run.

Lives in todira_common (moved here 2026-09-08, was website/whatsapp_client.py) because it's no
longer website-only: scraper/notifier.py and scraper/whatsapp_checkin.py use it for proactive
sends, the same way todira_common/cards.py and bright_data_client.py are already shared between
the bot and the scraper.

ONLY free-form messages exist here (2026-10-02, owner's rule: never pay Meta). A free-form message
(text, interactive, image + button) is free when sent within 24 hours of the user's own last inbound
message ("customer service window", see todira_common/whatsapp_window.py) and is rejected by Meta
outside it. Message Templates - the only way to message someone outside the window, and billed per
message - are deliberately NOT supported: there is no template sender, and _post_message refuses any
payload of type "template".
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

ACCESS_TOKEN_ENV_VAR = "WHATSAPP_ACCESS_TOKEN"
PHONE_NUMBER_ID_ENV_VAR = "WHATSAPP_PHONE_NUMBER_ID"

_GRAPH_API_VERSION = "v21.0"
_REQUEST_TIMEOUT_SECONDS = 15.0

# 2026-09-06 speed pass: `httpx.post(...)` (the module-level convenience function used here until
# now) opens and tears down a brand-new TCP+TLS connection to graph.facebook.com on EVERY single
# call — real, measurable latency (a fresh HTTPS handshake typically costs on the order of a
# hundred-plus ms) paid again and again, even though every call in this module hits the exact same
# host. A single reused `httpx.Client` keeps that connection alive (HTTP keep-alive) across calls,
# so only the FIRST request per pod lifetime pays full handshake cost — every call after that,
# including the typing-indicator call that immediately precedes almost every real reply here, reuses
# the same warm connection. Module-level and created once, same lifetime as the cached Gemini client
# in todira_common/gemini_client.py.
_http_client = httpx.Client(timeout=_REQUEST_TIMEOUT_SECONDS)


def _credentials() -> tuple[str, str] | None:
    access_token = os.environ.get(ACCESS_TOKEN_ENV_VAR, "").strip()
    phone_number_id = os.environ.get(PHONE_NUMBER_ID_ENV_VAR, "").strip()
    if not access_token or not phone_number_id:
        return None
    return access_token, phone_number_id


def _post_message(payload: dict, *, to: str, action_desc: str) -> bool:
    """Shared send path for every message shape below — same fail-soft contract throughout
    (never raises; a False return means "didn't go out", logged, not fatal to the caller)."""
    creds = _credentials()
    if creds is None:
        logger.error(
            "%s/%s not set — cannot %s to %s", ACCESS_TOKEN_ENV_VAR, PHONE_NUMBER_ID_ENV_VAR, action_desc, to
        )
        return False
    if payload.get("type") == "template":
        # Meta bills every template message. This project never sends one (owner's rule, 2026-10-02),
        # so even a future bug that builds such a payload cannot reach Meta.
        logger.error("Refusing to send a WhatsApp template message (templates are billed)")
        return False
    access_token, phone_number_id = creds
    url = f"https://graph.facebook.com/{_GRAPH_API_VERSION}/{phone_number_id}/messages"
    try:
        response = _http_client.post(url, json=payload, headers={"Authorization": f"Bearer {access_token}"})
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception("Failed to %s to %s", action_desc, to)
        return False


def send_text_message(to: str, body: str) -> bool:
    """`to` is the recipient's wa_id (E.164 digits, no leading '+') — same format the webhook
    payload's `messages[].from` field uses, so a reply can pass that value straight back in."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body, "preview_url": True},
    }
    return _post_message(payload, to=to, action_desc="send WhatsApp message")


def send_cta_url_message(to: str, body: str, button_text: str, url: str) -> bool:
    """A tappable button instead of a bare link in the message text — WhatsApp Cloud API's
    "interactive cta_url" message type (POST .../messages with type: "interactive",
    interactive.type: "cta_url"; action.name is always the literal string "cta_url", not
    caller-configurable — that's Meta's own required constant for this message shape, not a typo).
    2026-09-06: the owner compared this against the reference competitor bot, whose own filter-edit
    prompt renders as a real button ("עדכון סינון ⚙️"), not a plain https:// link sitting in the
    message text — this is the same UI element. `button_text` should stay short (WhatsApp truncates
    a long CTA label; keep it well under the ~20-character budget other WhatsApp button types use)."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {"text": body},
            "action": {"name": "cta_url", "parameters": {"display_text": button_text, "url": url}},
        },
    }
    return _post_message(payload, to=to, action_desc="send WhatsApp CTA button message")


def send_image_cta_message(
    to: str, *, media_id: str, body: str, button_text: str, url: str
) -> bool:
    """One free-form message: the listing's photo on top, the text, and a tappable URL button —
    "interactive cta_url" with an image header. Free-form, so only valid inside the 24h window (see
    todira_common/whatsapp_window.py) — and therefore free. `body` max 1024 characters."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "header": {"type": "image", "image": {"id": media_id}},
            "body": {"text": body},
            "action": {"name": "cta_url", "parameters": {"display_text": button_text, "url": url}},
        },
    }
    return _post_message(payload, to=to, action_desc="send WhatsApp image + button message")


def send_reply_buttons_message(to: str, body: str, buttons: list[tuple[str, str]]) -> bool:
    """Up to 3 quick-reply buttons. `buttons` is [(button_id, title), ...]; a title is max 20
    characters. A tap arrives on the webhook as message.type == "interactive" with
    interactive.button_reply.id, and counts as an inbound message — it reopens the 24h window."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": button_id, "title": title}}
                    for button_id, title in buttons
                ]
            },
        },
    }
    return _post_message(payload, to=to, action_desc="send WhatsApp reply-buttons message")


def send_language_picker_message(
    to: str, body: str, button_text: str, language_rows: list[tuple[str, str]]
) -> bool:
    """WhatsApp Cloud API's "interactive list" message type — up to 10 tappable rows in one
    message (a "reply buttons" message caps out at 3, not enough for our 5 supported languages).
    `language_rows` is [(row_id, title), ...] in display order; the reply comes back on a later
    webhook delivery as message.type == "interactive", message.interactive.list_reply.id — handled
    in website/whatsapp_webhook.py's own language-selection flow."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {
                "button": button_text,
                "sections": [
                    {"rows": [{"id": row_id, "title": title} for row_id, title in language_rows]}
                ],
            },
        },
    }
    return _post_message(payload, to=to, action_desc="send WhatsApp language picker")


def upload_media(file_bytes: bytes, *, mime_type: str = "image/jpeg") -> str | None:
    """Uploads media to WhatsApp's own CDN via the Cloud API's /media endpoint, returning a media
    id usable as send_image_cta_message's media_id (a different real photo/collage per listing). Same
    fail-soft contract as every other function here: returns None and logs on any failure, never
    raises — a failed upload just means the caller falls back to sending without a header image
    rather than failing the whole notification."""
    creds = _credentials()
    if creds is None:
        logger.error(
            "%s/%s not set — cannot upload WhatsApp media", ACCESS_TOKEN_ENV_VAR, PHONE_NUMBER_ID_ENV_VAR
        )
        return None
    access_token, phone_number_id = creds
    url = f"https://graph.facebook.com/{_GRAPH_API_VERSION}/{phone_number_id}/media"
    try:
        response = _http_client.post(
            url,
            data={"messaging_product": "whatsapp", "type": mime_type},
            files={"file": ("photo.jpg", file_bytes, mime_type)},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json().get("id")
    except httpx.HTTPError:
        logger.exception("Failed to upload WhatsApp media")
        return None


def mark_as_read_with_typing_indicator(message_id: str) -> bool:
    """Marks the incoming message read AND shows WhatsApp's own "typing…" bubble to the user for
    up to ~25s (Meta clears it automatically the moment we send the actual reply, or after 25s,
    whichever comes first — no need to ever turn it off ourselves). 2026-09-06: the owner compared
    this bot live against a competitor's bot that shows this, and asked for it specifically —
    it doesn't make the underlying Gemini call any faster, but it turns the same wait from "did it
    even get my message?" into visibly "it's working on it," which is most of what "feels slow"
    actually is for a chat bot."""
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
    }
    return _post_message(payload, to=message_id, action_desc="mark WhatsApp message as read/typing")
