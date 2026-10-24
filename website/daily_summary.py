"""Morning summary for the owner (2026-10-20, owner: "a short message every morning in the inbox group").

Daily job (daily-summary CronJob, charts/todira): counts for yesterday (Israel time) - sign-ups, payments, alerts sent,
new listings, messages from people, site visitors and where they came from, clicks to the bot, questions to the site
assistant, people active in the bot - plus where things stand now (paying, on the free trial, whose trial ends this
week). Sent to the owner's
inbox group (todira_common/owner_inbox.py), or his private chat when there is no group. Counts only.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select
from todira_common import owner_inbox
from todira_common.db import get_session
from todira_common.models import ActivityDay, ContactMessage, Listing, Payment, SentNotification, User

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ISRAEL = ZoneInfo("Asia/Jerusalem")

# The referrer kinds main.py's _referrer_kind records as site_from_<kind>.
_SOURCE_NAMES = {
    "instagram": "אינסטגרם", "facebook": "פייסבוק", "google": "גוגל", "telegram": "טלגרם", "whatsapp": "וואטסאפ",
    "tiktok": "טיקטוק", "linkedin": "לינקדאין", "bing": "בינג", "other": "אחר",
}
TRIAL_DAYS_AHEAD = 7


def yesterday_bounds(now: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """[start, end) of yesterday in Israel time, as aware datetimes."""
    today = now.astimezone(ISRAEL).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - dt.timedelta(days=1), today


def collect(session, now: dt.datetime) -> dict:
    start, end = yesterday_bounds(now)

    def count(stmt) -> int:
        return session.scalar(stmt) or 0

    paid_rows = session.execute(
        select(func.count(), func.coalesce(func.sum(Payment.amount_ils), 0)).where(
            Payment.status == "paid", Payment.paid_at >= start, Payment.paid_at < end
        )
    ).one()
    day = start.date()

    def people(*kinds: str) -> int:
        return count(select(func.count(func.distinct(ActivityDay.who))).where(
            ActivityDay.day == day, ActivityDay.kind.in_(kinds)))

    sources = {
        kind.removeprefix("site_from_"): n
        for kind, n in session.execute(
            select(ActivityDay.kind, func.count()).where(
                ActivityDay.day == day, ActivityDay.kind.like("site_from_%")).group_by(ActivityDay.kind)
        ).all()
    }
    campaigns = {
        kind.removeprefix("src_"): n
        for kind, n in session.execute(
            select(ActivityDay.kind, func.count()).where(
                ActivityDay.day == day, ActivityDay.kind.like("src\\_%")).group_by(ActivityDay.kind)
        ).all()
    }
    trial_ends = session.scalars(select(User.trial_ends_at).where(
        User.trial_ends_at > now, User.trial_ends_at <= now + dt.timedelta(days=TRIAL_DAYS_AHEAD),
        (User.paid_until.is_(None)) | (User.paid_until <= now), User.free_access_granted.is_(False))).all()
    ending: dict[dt.date, int] = {}
    for ends_at in trial_ends:
        local = ends_at.astimezone(ISRAEL).date()
        ending[local] = ending.get(local, 0) + 1
    return {
        "date": start.strftime("%d.%m"),
        "visitors": people("site_visit"),
        "sources": dict(sorted(sources.items(), key=lambda kv: -kv[1])),
        "campaigns": dict(sorted(campaigns.items(), key=lambda kv: -kv[1])),
        "bot_clicks": people("click_bot_hero", "click_bot_end", "click_bot_menu", "click_bot_nofilter", "click_bot_share"),
        "assistant_questions": count(select(func.coalesce(func.sum(ActivityDay.hits), 0)).where(
            ActivityDay.day == day, ActivityDay.kind == "assistant_question")),
        "bot_active": people("bot_message", "bot_button"),
        "trial_ending": [(d.strftime("%d.%m"), n) for d, n in sorted(ending.items())],
        "signups": count(select(func.count()).select_from(User).where(User.created_at >= start, User.created_at < end)),
        "payments": paid_rows[0],
        "income": paid_rows[1],
        "alerts": count(select(func.count()).select_from(SentNotification).where(
            SentNotification.sent_at >= start, SentNotification.sent_at < end)),
        "alerted_users": count(select(func.count(func.distinct(SentNotification.user_id))).where(
            SentNotification.sent_at >= start, SentNotification.sent_at < end)),
        "new_listings": count(select(func.count()).select_from(Listing).where(
            Listing.first_seen_at >= start, Listing.first_seen_at < end, Listing.duplicate_of_id.is_(None))),
        "messages": count(select(func.count()).select_from(ContactMessage).where(
            ContactMessage.created_at >= start, ContactMessage.created_at < end)),
        "paying_now": count(select(func.count()).select_from(User).where(User.paid_until > now)),
        "trial_now": count(select(func.count()).select_from(User).where(
            User.trial_ends_at > now, (User.paid_until.is_(None)) | (User.paid_until <= now),
            User.free_access_granted.is_(False))),
        "users_total": count(select(func.count()).select_from(User)),
    }


def summary_text(c: dict) -> str:
    income = f"{c['income']:,.2f}".rstrip("0").rstrip(".")
    lines = [
        f"☀️ <b>בוקר טוב! מה היה אתמול ({c['date']})</b>",
        "",
        f"👤 נרשמו: <b>{c['signups']}</b>",
        f"💳 תשלומים: <b>{c['payments']}</b> (₪{income})",
        f"🔔 התראות שנשלחו: <b>{c['alerts']:,}</b> ל־{c['alerted_users']} משתמשים",
        f"🏠 דירות חדשות: <b>{c['new_listings']:,}</b>",
        f"📬 פניות: <b>{c['messages']}</b>",
        f"🤖 פעילים בבוט: <b>{c.get('bot_active', 0)}</b>",
    ]
    sources = c.get("sources") or {}
    where = ", ".join(f"{_SOURCE_NAMES.get(k, k)} {n}" for k, n in sources.items())
    lines.append(f"🌐 נכנסו לאתר: <b>{c.get('visitors', 0)}</b>" + (f" (הגיעו מ: {where})" if where else ""))
    campaigns = c.get("campaigns") or {}
    if campaigns:
        lines.append("🔗 הגיעו מקישורים: " + ", ".join(f"{k} {n}" for k, n in campaigns.items()))
    lines.append(f"👆 עברו מהאתר לבוט: <b>{c.get('bot_clicks', 0)}</b>")
    lines.append(f"💬 שאלות לעוזר באתר: <b>{c.get('assistant_questions', 0)}</b>")
    ending = c.get("trial_ending") or []
    if ending:
        days = ", ".join(f"{d} ({n})" for d, n in ending)
        lines.append(f"⏳ ניסיון נגמר השבוע: <b>{sum(n for _, n in ending)}</b> ({days})")
    lines += [
        "",
        f"📊 עכשיו: {c['paying_now']} משלמים, {c['trial_now']} בתקופת ניסיון, {c['users_total']} משתמשים בסך הכל",
    ]
    return "\n".join(lines)


def send(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner = os.environ.get("OWNER_TELEGRAM_USER_ID", "").strip() or None
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set - no summary sent")
        return False
    for chat_id in owner_inbox.owner_chat_ids(owner):
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=15.0,
            )
        except httpx.HTTPError:
            logger.exception("Sending the morning summary failed")
            continue
        if resp.status_code == 200:
            return True
        logger.warning("Telegram rejected the morning summary: status=%d", resp.status_code)
    return False


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    with get_session() as session:
        counts = collect(session, now)
    logger.info("morning summary sent: %s", send(summary_text(counts)))


if __name__ == "__main__":
    main()
