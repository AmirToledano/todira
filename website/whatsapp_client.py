"""Thin wrapper around the WhatsApp Cloud API (Meta) for sending free-form text messages.

Fails soft, same contract as bot/gemini_client.py: if WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID
aren't set, or the API call fails for any reason, send_text_message returns False and logs — never
raises. Callers (whatsapp_webhook.py) treat a False return as "the reply didn't go out" without
crashing the whole request.

Only free-form text is implemented (no message templates). WhatsApp only allows free-form replies
within 24 hours of the user's last message (the "customer service window") — fine for the
onboarding conversation itself (always a direct reply to something the user just sent), but NOT
enough for proactive "a new listing matches your filter" pushes outside that window, which need a
pre-approved message template (a separate Meta review process — see PROJECT_STATE.md). Not built
yet; scraper/notifier.py still only sends via Telegram.
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


def send_text_message(to: str, body: str) -> bool:
    """`to` is the recipient's wa_id (E.164 digits, no leading '+') — same format the webhook
    payload's `messages[].from` field uses, so a reply can pass that value straight back in."""
    access_token = os.environ.get(ACCESS_TOKEN_ENV_VAR, "").strip()
    phone_number_id = os.environ.get(PHONE_NUMBER_ID_ENV_VAR, "").strip()
    if not access_token or not phone_number_id:
        logger.error(
            "%s/%s not set — cannot send WhatsApp message to %s",
            ACCESS_TOKEN_ENV_VAR,
            PHONE_NUMBER_ID_ENV_VAR,
            to,
        )
        return False

    url = f"https://graph.facebook.com/{_GRAPH_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body, "preview_url": True},
    }
    try:
        response = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception("Failed to send WhatsApp message to %s", to)
        return False


def mark_as_read_with_typing_indicator(message_id: str) -> bool:
    """Marks the incoming message read AND shows WhatsApp's own "typing…" bubble to the user for
    up to ~25s (Meta clears it automatically the moment we send the actual reply, or after 25s,
    whichever comes first — no need to ever turn it off ourselves). 2026-09-06: the owner compared
    this bot live against a competitor's ("דורין") that shows this, and asked for it specifically —
    it doesn't make the underlying Gemini call any faster, but it turns the same wait from "did it
    even get my message?" into visibly "it's working on it," which is most of what "feels slow"
    actually is for a chat bot."""
    access_token = os.environ.get(ACCESS_TOKEN_ENV_VAR, "").strip()
    phone_number_id = os.environ.get(PHONE_NUMBER_ID_ENV_VAR, "").strip()
    if not access_token or not phone_number_id:
        return False

    url = f"https://graph.facebook.com/{_GRAPH_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
    }
    try:
        response = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception("Failed to mark WhatsApp message %s as read/typing", message_id)
        return False
