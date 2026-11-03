"""One morning message to people whose access ended (2026-11-03, owner: "a message back to every user whose access
ended, in the morning").

Who: a Telegram user who is still active (did not block the bot), is not the owner, has no access now, and whose access
(the later of the trial end and the paid period) ended at least MIN_DAYS_AFTER ago. They keep getting cards without the
link to the ad; the message counts how many matching flats came since their access ended, from the cards actually sent
(SentNotification), and links to /upgrade signed in. Only when that count is at least MIN_FLATS, so it is never "0 flats".
Once for each ended access: the access end it was sent for is kept in app_flags, so paying again and ending again later
sends one new message. Mornings only (09:00-11:59 Israel), main scraper only.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from telegram import Bot
from telegram.error import Forbidden

from todira_common import alert_hours, app_flags
from todira_common.access import has_full_access
from todira_common.bot_strings import bot_text
from todira_common.enums import NotificationReason
from todira_common.language import DEFAULT_LANG
from todira_common.models import SentNotification, User
from todira_common.uid_token import signed_login_query

logger = logging.getLogger(__name__)

MIN_DAYS_AFTER = dt.timedelta(days=2)
MIN_FLATS = 3
_FLAG = "winback_sent"  # JSON {user_id: access end (ISO) the message was sent for}
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://todira.app").rstrip("/")
OWNER_TELEGRAM_USER_ID = os.environ.get("OWNER_TELEGRAM_USER_ID", "").strip()


def access_end(user: User) -> dt.datetime | None:
    ends = [end for end in (user.trial_ends_at, user.paid_until) if end is not None]
    return max(ends) if ends else None


def due_users(session: Session, now: dt.datetime, sent: dict[str, str]) -> list[tuple[User, dt.datetime, int]]:
    """(user, access end, flats sent since) for everyone to message now."""
    conditions = [
        User.is_active.is_(True),
        User.telegram_user_id.is_not(None),
        User.free_access_granted.is_(False),
    ]
    if OWNER_TELEGRAM_USER_ID.isdigit():
        conditions.append(User.telegram_user_id != int(OWNER_TELEGRAM_USER_ID))
    due = []
    for user in session.scalars(select(User).where(*conditions)):
        end = access_end(user)
        if end is None or has_full_access(user) or now - end < MIN_DAYS_AFTER:
            continue
        if sent.get(str(user.id)) == end.isoformat():
            continue
        flats = session.execute(
            select(func.count()).select_from(SentNotification).where(
                SentNotification.user_id == user.id,
                SentNotification.reason == NotificationReason.NEW,
                SentNotification.sent_at >= end,
            )
        ).scalar() or 0
        if flats >= MIN_FLATS:
            due.append((user, end, int(flats)))
    return due


def message(user: User, end: dt.datetime, flats: int) -> str:
    lang = user.language or DEFAULT_LANG
    date = alert_hours.israel_now(end).strftime("%d.%m")
    url = f"{WEBSITE_URL}/upgrade?{signed_login_query(user.telegram_user_id)}"
    return bot_text("winback.text", lang, date=date, count=flats, url=url)


async def _run(session: Session, now: dt.datetime) -> int:
    if not 9 <= alert_hours.israel_now(now).hour < 12:
        return 0
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return 0
    sent: dict[str, str] = json.loads(app_flags.get_flag(session, _FLAG) or "{}")
    due = due_users(session, now, sent)
    if not due:
        return 0
    count = 0
    bot = Bot(token=token)
    await bot.initialize()
    try:
        for user, end, flats in due:
            try:
                await bot.send_message(chat_id=user.telegram_user_id, text=message(user, end, flats))
            except Forbidden:
                user.is_active = False  # blocked the bot
                session.commit()
                continue
            except Exception:
                logger.exception("win-back: Telegram send failed for user_id=%s", user.id)
                continue
            sent[str(user.id)] = end.isoformat()
            app_flags.set_flag(session, _FLAG, json.dumps(sent))
            count += 1
            await asyncio.sleep(0.3)
    finally:
        await bot.shutdown()
    return count


def run_winback(session: Session, now: dt.datetime | None = None) -> dict[str, int]:
    return {"winback_sent": asyncio.run(_run(session, now or dt.datetime.now(dt.timezone.utc)))}
