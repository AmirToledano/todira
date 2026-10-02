"""WhatsApp's 24-hour customer-service window — the one place that decides whether a free-form
(free) message may be sent to a user right now.

Meta bills business-initiated TEMPLATE messages per message; a free-form message sent within 24h of
the user's own last inbound message (text or a button tap) is a free service message. The owner's
rule (2026-10-02): never pay — so nothing proactive is ever sent unless this says the window is open.
"""
from __future__ import annotations

import datetime as dt

WINDOW = dt.timedelta(hours=24)
# Safety margin: a send takes seconds, clocks differ slightly, and Meta measures from ITS receipt time.
SAFE_WINDOW = dt.timedelta(hours=23, minutes=30)
# The "still looking?" check-in goes out once the window has been open this long (i.e. when the last
# ~4 hours of it remain), leaving margin for the hourly scraper cadence.
CHECKIN_AFTER = dt.timedelta(hours=20)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(value: dt.datetime) -> dt.datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.timezone.utc)


def window_open(last_inbound_at: dt.datetime | None, now: dt.datetime | None = None) -> bool:
    """True when a free-form message may safely be sent (inside the 24h window, with margin)."""
    if last_inbound_at is None:
        return False
    return (now or _now()) - _aware(last_inbound_at) < SAFE_WINDOW


def checkin_due(
    last_inbound_at: dt.datetime | None,
    checkin_sent_at: dt.datetime | None,
    now: dt.datetime | None = None,
) -> bool:
    """True when the window is still open, has been open long enough that it's nearly over, and no
    check-in has been sent for THIS window yet (a check-in older than the last inbound belongs to a
    previous window)."""
    now = now or _now()
    if not window_open(last_inbound_at, now):
        return False
    last_inbound_at = _aware(last_inbound_at)
    if now - last_inbound_at < CHECKIN_AFTER:
        return False
    return checkin_sent_at is None or _aware(checkin_sent_at) < last_inbound_at
