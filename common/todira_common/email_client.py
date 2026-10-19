"""Sends email through Resend (https://resend.com) - 2026-10-19, owner's choice of the cheapest option: 3,000 emails a
month free, no sandbox and no provider branding in the message. Used for people who signed up with Google only, whom the
Telegram bot can't reach.

Off until RESEND_API_KEY is set (the owner adds it as a GitHub secret after verifying todira.app in Resend - see
RUNBOOK.md); send() then returns False without trying, so nothing breaks before that. Never raises."""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "טודירה <hello@todira.app>"


def enabled() -> bool:
    return bool(os.environ.get("RESEND_API_KEY", "").strip())


def send(to: str, subject: str, html: str, text: str) -> bool:
    """True when Resend accepted the message."""
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key or not to:
        return False
    payload = {
        "from": os.environ.get("EMAIL_FROM", "").strip() or DEFAULT_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
    }
    try:
        response = httpx.post(
            RESEND_API_URL, json=payload, headers={"Authorization": f"Bearer {api_key}"}, timeout=20.0
        )
    except httpx.HTTPError:
        logger.exception("Resend request failed")
        return False
    if response.status_code >= 300:
        # The body is Resend's own error (no recipient data in it) - logged so a wrong key/domain is visible.
        logger.error("Resend refused the email: HTTP %s %s", response.status_code, response.text[:300])
        return False
    return True
