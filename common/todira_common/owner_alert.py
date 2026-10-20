"""Best-effort Telegram message to the owner (never raises): his inbox group first, then his private chat
(todira_common/owner_inbox.py)."""
from __future__ import annotations

import logging
import os

import httpx

from todira_common import owner_inbox

logger = logging.getLogger(__name__)


def alert_owner(text_html: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    owner = os.environ.get("OWNER_TELEGRAM_USER_ID")
    if not token:
        return False
    for chat_id in owner_inbox.owner_chat_ids(owner):
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text_html, "parse_mode": "HTML"},
                timeout=10.0,
            )
        except httpx.HTTPError:
            logger.exception("Failed to push an owner alert to Telegram")
            continue
        if resp.status_code == 200:
            return True
    return False
