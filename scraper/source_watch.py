"""Tells the owner the same day when a source brings far fewer new flats than usual (2026-11-08, owner: Yad2 fell to a
fifth from Friday and it was found only two days later).

Each main-scraper run in the afternoon (WATCH_FROM_HOUR onwards, Israel), for every source: new flats since midnight
today against the same hours on each of the last BASELINE_DAYS days (their median). Below LOW_SHARE of the usual, with
a usual of at least MIN_USUAL, the owner's inbox gets one message, once per source per day (app_flags _FLAG). Counts only.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import statistics

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from todira_common import alert_hours, app_flags
from todira_common.models import Listing
from todira_common.owner_alert import alert_owner

logger = logging.getLogger(__name__)

WATCH_FROM_HOUR = 14
BASELINE_DAYS = 7
LOW_SHARE = 1 / 3
MIN_USUAL = 30
_FLAG = "source_watch_alerted"  # JSON {source: date alerted}


def _counts(session: Session, start: dt.datetime, end: dt.datetime) -> dict[str, int]:
    return dict(session.execute(
        select(Listing.source, func.count()).where(
            Listing.first_seen_at >= start, Listing.first_seen_at < end, Listing.duplicate_of_id.is_(None),
        ).group_by(Listing.source)
    ).all())


def low_sources(today: dict[str, int], days: list[dict[str, int]]) -> list[tuple[str, int, int]]:
    """(source, today, usual) for each source far below its usual."""
    out = []
    for source in sorted({s for day in days for s in day}):
        usual = int(statistics.median([day.get(source, 0) for day in days]))
        if usual >= MIN_USUAL and today.get(source, 0) < usual * LOW_SHARE:
            out.append((source, today.get(source, 0), usual))
    return out


def run_source_watch(session: Session, now: dt.datetime | None = None) -> dict[str, int]:
    now = now or dt.datetime.now(dt.timezone.utc)
    local = alert_hours.israel_now(now)
    if local.hour < WATCH_FROM_HOUR:
        return {}
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = local - midnight
    today = _counts(session, midnight, local)
    days = [_counts(session, midnight - dt.timedelta(days=n), midnight - dt.timedelta(days=n) + elapsed)
            for n in range(1, BASELINE_DAYS + 1)]
    low = low_sources(today, days)
    if not low:
        return {}
    done: dict = json.loads(app_flags.get_flag(session, _FLAG) or "{}")
    date = local.date().isoformat()
    new = [row for row in low if done.get(row[0]) != date]
    if not new:
        return {}
    lines = ["⚠️ <b>מקור דירות הביא היום הרבה פחות מהרגיל</b>", f"מחצות עד {local:%H:%M}, מול אותן שעות בשבוע האחרון:", ""]
    lines += [f"{source}: {count} היום, בדרך כלל {usual}" for source, count, usual in new]
    if alert_owner("\n".join(lines)):
        for source, _, _ in new:
            done[source] = date
        app_flags.set_flag(session, _FLAG, json.dumps(done))
    return {"source_watch_alerts": len(new)}
