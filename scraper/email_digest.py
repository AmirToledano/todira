"""Sends the morning email of new matching flats (todira_common/email_digest.py builds it), 2026-11-08.

Who: everyone with an email address (signed up with Google) who is active, has alerts on and a search saved, and did not
stop the email (website /email/stop). Once a day, 09:00-11:59 Israel, main scraper only; only when at least one new flat
matched since the last email (or the last 24 hours the first time). Off until RESEND_API_KEY is set
(todira_common/email_client.py). Sent days are kept in app_flags (_FLAG).
"""
from __future__ import annotations

import datetime as dt
import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from todira_common import activity, alert_hours, app_flags, email_client
from todira_common.email_digest import OFF_FLAG, build
from todira_common.listing_matches import hidden_listing_ids, load_listings, matching_listing_rows
from todira_common.models import Filter, User

logger = logging.getLogger(__name__)

_FLAG = "email_digest_sent"  # JSON {user_id: ISO time of the last email}
FIRST_WINDOW = dt.timedelta(hours=24)


def run_email_digest(session: Session, now: dt.datetime | None = None) -> dict[str, int]:
    now = now or dt.datetime.now(dt.timezone.utc)
    if not 9 <= alert_hours.israel_now(now).hour < 12 or not email_client.enabled():
        return {}
    sent_at: dict = json.loads(app_flags.get_flag(session, _FLAG) or "{}")
    off = set(json.loads(app_flags.get_flag(session, OFF_FLAG) or "[]"))
    today = alert_hours.israel_now(now).date()
    users = session.scalars(select(User).where(
        User.google_email.is_not(None), User.is_active.is_(True), User.notifications_enabled.is_(True),
    ))
    count = 0
    for user in users:
        if user.id in off:
            continue
        last = sent_at.get(str(user.id))
        if last and alert_hours.israel_now(dt.datetime.fromisoformat(last)).date() == today:
            continue
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user.id).order_by(Filter.id).limit(1))
        if filter_row is None:
            continue
        since = dt.datetime.fromisoformat(last) if last else now - FIRST_WINDOW
        rows = matching_listing_rows(session, filter_row, hidden_listing_ids(session, user.id), since=since)
        if not rows:
            continue
        listings = sorted(load_listings(session, [row.id for row in rows[:10]]), key=lambda l: l.first_seen_at, reverse=True)
        city = filter_row.cities[0] if filter_row.cities and len(filter_row.cities) == 1 else None
        subject, page, text = build(listings, user.id, user.first_name, city, len(rows))
        if email_client.send(user.google_email, subject, page, text):
            sent_at[str(user.id)] = now.isoformat()
            app_flags.set_flag(session, _FLAG, json.dumps(sent_at))
            activity.record("email_digest", f"u{user.id}")
            count += 1
    return {"email_digests_sent": count} if count else {}
