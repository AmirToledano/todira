"""WhatsApp cost circuit breaker (2026-10-02).

The owner's rule: WhatsApp must never cost a single agora. Layers, in order:
1. Structural: no template message can be sent at all (todira_common/whatsapp_client.py has no
   template sender and refuses any payload of type "template").
2. Window: proactive sends only inside the user's free 24h window (todira_common/whatsapp_window.py).
3. THIS: a persistent "paused" flag. The moment Meta reports a BILLABLE message (webhook status with
   pricing.billable == true) or its pricing analytics show any cost, every proactive send (listing
   pushes and check-ins) stops until the owner deliberately resumes, and the owner is alerted on
   Telegram. Webhook replies to a user's own message are not proactive and are unaffected.

Fail-CLOSED: if the flag cannot be read, WhatsApp is treated as paused.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from todira_common.models import AppFlag

logger = logging.getLogger(__name__)

PAUSED_KEY = "whatsapp_paused"
COST_CHECKED_KEY = "whatsapp_cost_checked_at"


def get_flag(session: Session, key: str) -> str | None:
    row = session.get(AppFlag, key)
    return None if row is None else row.value


def set_flag(session: Session, key: str, value: str) -> None:
    row = session.get(AppFlag, key)
    if row is None:
        session.add(AppFlag(key=key, value=value))
    else:
        row.value = value
    session.commit()


def is_paused(session: Session) -> bool:
    """True when proactive WhatsApp sends are stopped. Any error reading the flag counts as paused."""
    try:
        return bool(get_flag(session, PAUSED_KEY))
    except Exception:
        logger.exception("Could not read the WhatsApp pause flag - treating WhatsApp as paused")
        return True


def pause(session: Session, reason: str) -> None:
    """Stops all proactive WhatsApp sends. `reason` is stored (never contains a phone number)."""
    set_flag(session, PAUSED_KEY, reason[:500] or "paused")
    logger.error("WhatsApp proactive sends PAUSED: %s", reason)


def resume(session: Session) -> None:
    set_flag(session, PAUSED_KEY, "")
