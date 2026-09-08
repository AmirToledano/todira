"""Thin wrapper around the WhatsApp Cloud API (Meta) for sending messages.

Fails soft, same contract as bot/gemini_client.py: if WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID
aren't set, or the API call fails for any reason, every send_* function returns False and logs —
never raises. Callers (whatsapp_webhook.py, scraper/notifier.py) treat a False return as "the
message didn't go out" without crashing the whole request/run.

Lives in dorin_common (moved here 2026-09-08, was website/whatsapp_client.py) because it's no
longer website-only: send_template_message below is used by scraper/notifier.py for proactive
pushes, the same way dorin_common/cards.py and bright_data_client.py are already shared between
the bot and the scraper.

Two message-sending regimes:
- Free-form text/interactive messages (send_text_message, send_cta_url_message,
  mark_as_read_with_typing_indicator) only work within 24 hours of the user's own last message
  (WhatsApp's "customer service window") — fine for direct replies in an active conversation
  (whatsapp_webhook.py's onboarding/chat), never for a proactive push out of nowhere.
- send_template_message uses a pre-approved WhatsApp Message Template, Meta's only mechanism for
  business-initiated messages outside that window — this is what a proactive "a new listing
  matches your filter" push (scraper/notifier.py) actually needs, and it requires the recipient's
  own opt-in plus a template Meta has already reviewed and approved (see PROJECT_STATE.md for the
  submitted template copy and the User.whatsapp_notifications_opted_in field this is gated on).
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
# in dorin_common/gemini_client.py.
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


def send_template_message(
    to: str, *, template_name: str, language_code: str, body_params: list[str]
) -> bool:
    """Sends a pre-approved WhatsApp Message Template — see this module's own docstring for why
    this is the only way to message a user proactively, outside a conversation they started.

    `template_name`/`language_code` must exactly match a template Meta has already APPROVED in
    WhatsApp Manager (see PROJECT_STATE.md for the exact copy submitted) — an unapproved or
    misspelled name fails the whole send, same fail-soft contract as every other function here
    (logged, returns False, never raises). `body_params` are substituted into the template's
    {{1}}, {{2}}, ... placeholders in order. Meta rejects a param containing a newline or 4+
    consecutive spaces — callers must pre-sanitize (scraper/notifier.py's own
    _whatsapp_template_param does this before calling in)."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": param} for param in body_params],
                }
            ],
        },
    }
    return _post_message(payload, to=to, action_desc=f"send WhatsApp template '{template_name}'")


def mark_as_read_with_typing_indicator(message_id: str) -> bool:
    """Marks the incoming message read AND shows WhatsApp's own "typing…" bubble to the user for
    up to ~25s (Meta clears it automatically the moment we send the actual reply, or after 25s,
    whichever comes first — no need to ever turn it off ourselves). 2026-09-06: the owner compared
    this bot live against a competitor's ("דורין") that shows this, and asked for it specifically —
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
