"""The hours and days a person wants alerts in (2026-10-31, owner).

users.alert_from_hour / alert_to_hour are whole Israel-time hours, from inclusive and to exclusive (9 and 20 = 09:00 to
19:59); NULL on either side means every hour we scan. users.alerts_on_weekend false means nothing on Friday and Saturday.
A match outside them waits in held_alerts and goes out on the first run inside them (scraper/notifier.py).

Without a choice, alerts arrive whenever we scan: the first Facebook run at about 08:25 to the last main run, which ends
at about 22:55. The texts round that to 08:30 to 23:00.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

ISRAEL = ZoneInfo("Asia/Jerusalem")
DEFAULT_FROM_TEXT = "08:30"
DEFAULT_TO_TEXT = "23:00"
# Friday and Saturday in datetime.weekday()
WEEKEND_DAYS = (4, 5)
FROM_HOURS = (8, 9, 10, 12, 14, 16, 18)
TO_HOURS = (14, 16, 18, 20, 21, 22, 23)
# Morning runs (before this Israel hour) space each person's alerts out instead of sending them back to back.
MORNING_UNTIL_HOUR = 10


def israel_now(now: dt.datetime | None = None) -> dt.datetime:
    return (now or dt.datetime.now(dt.timezone.utc)).astimezone(ISRAEL)


def has_custom_hours(user) -> bool:
    return getattr(user, "alert_from_hour", None) is not None and getattr(user, "alert_to_hour", None) is not None


def in_window(user, now: dt.datetime | None = None) -> bool:
    local = israel_now(now)
    if not getattr(user, "alerts_on_weekend", True) and local.weekday() in WEEKEND_DAYS:
        return False
    if not has_custom_hours(user):
        return True
    start, end = user.alert_from_hour, user.alert_to_hour
    if start < end:
        return start <= local.hour < end
    if start > end:  # across midnight; the menus never offer it, but a stored pair like this still means something
        return local.hour >= start or local.hour < end
    return True


def is_morning(now: dt.datetime | None = None) -> bool:
    return israel_now(now).hour < MORNING_UNTIL_HOUR


def hours_pair(user) -> tuple[str, str]:
    """("08:30", "23:00")-style from and to of the person's hours, for menus."""
    if not has_custom_hours(user):
        return DEFAULT_FROM_TEXT, DEFAULT_TO_TEXT
    return f"{user.alert_from_hour:02d}:00", f"{user.alert_to_hour:02d}:00"
