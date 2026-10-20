"""Morning summary for the owner (2026-10-20, owner: "a short message every morning in the inbox group").

Daily job (daily-summary CronJob, charts/todira): counts for yesterday (Israel time) - sign-ups, payments, alerts sent,
new listings, messages from people - plus where things stand now (paying, on the free trial). Sent to the owner's
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
from todira_common.models import ContactMessage, Listing, Payment, SentNotification, User

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ISRAEL = ZoneInfo("Asia/Jerusalem")


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
    return {
        "date": start.strftime("%d.%m"),
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
