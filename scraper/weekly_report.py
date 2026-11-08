"""A short weekly report for the owner, in his inbox group (2026-11-03, owner: "what else can you do, you do it").

Sunday morning (09:00-12:00 Israel), once a week: the last 7 days in counts only. New users, who has access now,
paid and unpaid checkouts, people on the site and in the bot, where visits came from (the channel, the leads replies,
Google and so on), and new flats. Main scraper only; the week sent is kept in app_flags so a later run does not send it
again. Nothing about any one person.
"""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from todira_common import alert_hours, app_flags
from todira_common.models import ActivityDay, Listing, Payment, User
from todira_common.owner_alert import alert_owner

logger = logging.getLogger(__name__)

SUNDAY = 6
FROM_HOUR, UNTIL_HOUR = 9, 12
_FLAG = "weekly_report_sent"
_SOURCE_NAMES = {
    "src_fblead": "תגובות לידים בפייסבוק",
    "src_ig": "הקישור בביו של האינסטגרם",
    "src_pwa": "פתיחות מהאייקון במסך הבית",
    "src_nudge_weekly": "לחיצות על הסיכום השבועי בטלגרם",
    "src_nudge_price": "לחיצות על הודעת המחיר לפני סוף הניסיון",
    "site_from_google": "גוגל",
    "site_from_facebook": "פייסבוק",
    "site_from_telegram": "טלגרם",
    "site_from_whatsapp": "וואטסאפ",
    "site_from_instagram": "אינסטגרם",
    "site_from_tiktok": "טיקטוק",
    "site_from_bing": "בינג",
}

_NUDGE_NAMES = {
    "nudge_weekly": "סיכום שבועי נשלח",
    "nudge_tip": "טיפ ביום השלישי נשלח",
    "nudge_price": "מחיר לפני סוף הניסיון נשלח",
    "nudge_off": "ביקשו פחות הודעות כאלה",
    "nudge_blocked_weekly": "הבוט כבר היה חסום אצלם (סיכום שבועי)",
    "nudge_blocked_tip": "הבוט כבר היה חסום אצלם (טיפ)",
    "nudge_blocked_price": "הבוט כבר היה חסום אצלם (מחיר)",
}


def due(state: str | None, now: dt.datetime) -> str | None:
    """The week's label (ISO year-week) when the report is due now, else None."""
    local = alert_hours.israel_now(now)
    if local.weekday() != SUNDAY or not FROM_HOUR <= local.hour < UNTIL_HOUR:
        return None
    year, week, _ = local.isocalendar()
    label = f"{year}-{week:02d}"
    return None if state == label else label


def _count(session: Session, query) -> int:
    return int(session.execute(query).scalar() or 0)


def build(session: Session, now: dt.datetime) -> str:
    since = now - dt.timedelta(days=7)
    day_since = alert_hours.israel_now(since).date()
    new_users = _count(session, select(func.count()).select_from(User).where(User.created_at >= since))
    access = _count(session, select(func.count()).select_from(User).where(
        User.is_active.is_(True),
        or_(User.trial_ends_at > now, User.paid_until > now, User.free_access_granted.is_(True)),
    ))
    paid = session.execute(
        select(func.count(), func.coalesce(func.sum(Payment.amount_ils), 0)).where(
            Payment.status == "paid", Payment.paid_at >= since
        )
    ).one()
    pending = _count(session, select(func.count()).select_from(Payment).where(
        Payment.status == "pending", Payment.created_at >= since
    ))
    people = dict(session.execute(
        select(ActivityDay.kind, func.count(func.distinct(ActivityDay.who)))
        .where(ActivityDay.day >= day_since).group_by(ActivityDay.kind)
    ).all())
    new_flats = _count(session, select(func.count()).select_from(Listing).where(
        Listing.first_seen_at >= since, Listing.duplicate_of_id.is_(None)
    ))
    bot_people = max(people.get("bot_message", 0), people.get("bot_button", 0))
    lines = [
        "<b>סיכום השבוע בטודירה</b>",
        "",
        f"משתמשים חדשים: {new_users}",
        f"עם גישה עכשיו: {access}",
        f"תשלומים: {paid[0]} (₪{int(paid[1]):,})",
        f"התחילו לשלם ולא סיימו: {pending}",
        f"ביקורים באתר: {people.get('site_visit', 0)}",
        f"השתמשו בבוט: {bot_people}",
        f"דירות חדשות: {new_flats:,}",
    ]
    sources = [(name, people.get(kind, 0)) for kind, name in _SOURCE_NAMES.items() if people.get(kind)]
    # 2026-11-08: the occasional Telegram messages (scraper/nudges.py): sent, "fewer like this", and already blocked when sent
    nudges = [(name, people.get(kind, 0)) for kind, name in _NUDGE_NAMES.items() if people.get(kind)]
    if nudges:
        lines += ["", "הודעות יזומות בטלגרם:"] + [f"{name}: {count}" for name, count in nudges]
    if sources:
        lines += ["", "מאיפה הגיעו לאתר:"] + [f"{name}: {count}" for name, count in sources]
    return "\n".join(lines)


def run_weekly_report(session: Session, now: dt.datetime | None = None) -> dict[str, str]:
    now = now or dt.datetime.now(dt.timezone.utc)
    label = due(app_flags.get_flag(session, _FLAG), now)
    if label is None:
        return {}
    if alert_owner(build(session, now)):
        app_flags.set_flag(session, _FLAG, label)
        return {"weekly_report": label}
    return {}
