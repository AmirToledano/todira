"""Best-effort Telegram message to the owner (never raises)."""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


def alert_owner(text_html: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    owner = os.environ.get("OWNER_TELEGRAM_USER_ID")
    if not token or not owner:
        return False
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": owner, "text": text_html, "parse_mode": "HTML"},
            timeout=10.0,
        )
        return resp.status_code == 200
    except httpx.HTTPError:
        logger.exception("Failed to push an owner alert to Telegram")
        return False
