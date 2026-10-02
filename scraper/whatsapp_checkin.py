"""The "still looking?" WhatsApp check-in — what keeps WhatsApp free (2026-10-02).

Meta bills every business-initiated template message, but a free-form message sent within 24h of the
user's own last inbound message is free. So the bot only ever messages inside that window
(todira_common/whatsapp_window.py) and keeps it open by asking, near the end of each window, a
question with reply buttons — a tap is an inbound message and opens a fresh 24h window.

Runs once per scraper run (hourly): for every opted-in user whose window is still open but nearly over
and who hasn't been asked yet in this window, send the check-in. A user who never taps simply stops
receiving anything — no template fallback, ever — until they write or tap again.
"""
from __future__ import annotations

import datetime as dt
import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from todira_common import whatsapp_client, whatsapp_guard
from todira_common.bot_strings import bot_text
from todira_common.language import DEFAULT_LANG
from todira_common.models import User
from todira_common.whatsapp_window import checkin_due

logger = logging.getLogger(__name__)

CHECKIN_CONTINUE_ID = "checkin_continue"
CHECKIN_FOUND_ID = "checkin_found"
CHECKIN_STOP_ID = "checkin_stop"

_SEND_DELAY_SECONDS = 0.3


def send_checkin(user: User) -> bool:
    lang = user.language or DEFAULT_LANG
    return whatsapp_client.send_reply_buttons_message(
        user.whatsapp_phone_number,
        bot_text("whatsapp.checkin_body", lang),
        [
            (CHECKIN_CONTINUE_ID, bot_text("whatsapp.checkin_continue_button", lang)),
            (CHECKIN_FOUND_ID, bot_text("whatsapp.checkin_found_button", lang)),
            (CHECKIN_STOP_ID, bot_text("whatsapp.checkin_stop_button", lang)),
        ],
    )


def run_whatsapp_checkins(session: Session) -> dict[str, int]:
    """Sends every due check-in. Returns {"whatsapp_checkins_sent": n} for the run summary."""
    if whatsapp_guard.is_paused(session):
        return {"whatsapp_checkins_sent": 0, "whatsapp_paused": 1}
    now = dt.datetime.now(dt.timezone.utc)
    users = session.scalars(
        select(User).where(
            User.whatsapp_phone_number.isnot(None),
            User.whatsapp_notifications_opted_in.is_(True),
            User.whatsapp_last_inbound_at.isnot(None),
        )
    ).all()
    sent = 0
    for user in users:
        if not checkin_due(user.whatsapp_last_inbound_at, user.whatsapp_checkin_sent_at, now):
            continue
        if send_checkin(user):
            user.whatsapp_checkin_sent_at = now
            session.commit()
            sent += 1
        time.sleep(_SEND_DELAY_SECONDS)
    return {"whatsapp_checkins_sent": sent}
