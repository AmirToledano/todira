"""The morning "is the search still right?" message (2026-10-31, owner-approved wording).

Measured that day: of 103 person-days with alerts in a week, only 7 had a visit to the site and 7 had any use of the
bot. Someone who keeps getting cards and never opens one may have a search that no longer fits, or may have stopped
looking. Rather than let them mute or block the bot, they get one question with four answers (bot/handlers/checkin.py).

Who: alerts on each of the last CHECKIN_DAYS full Israel days (at least CHECKIN_MIN_PER_DAY a day) and no activity at all
on those days or today: no message or button in the bot, no visit to the site (todira_common.activity). Not paused, and
not asked in the last CHECKIN_EVERY. Mornings only (09:00-11:59 Israel), main scraper only. The owner is never asked.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden

from todira_common import alert_hours
from todira_common.bot_strings import bot_text
from todira_common.enums import NotificationReason
from todira_common.language import DEFAULT_LANG
from todira_common.models import ActivityDay, SentNotification, User

logger = logging.getLogger(__name__)

CHECKIN_DAYS = 3
CHECKIN_MIN_PER_DAY = 5
CHECKIN_EVERY = dt.timedelta(days=7)
OWNER_TELEGRAM_USER_ID = os.environ.get("OWNER_TELEGRAM_USER_ID", "").strip()


def checkin_markup(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(bot_text("checkin.ok", lang), callback_data="ci:ok")],
        [InlineKeyboardButton(bot_text("checkin.edit", lang), callback_data="ci:edit")],
        [InlineKeyboardButton(bot_text("checkin.pause", lang), callback_data="ci:pause")],
        [InlineKeyboardButton(bot_text("checkin.found", lang), callback_data="ci:found")],
    ])


def due_users(session: Session, now: dt.datetime) -> list[tuple[User, int]]:
    """(user, alerts in the last CHECKIN_DAYS days) for everyone who should be asked now."""
    today = alert_hours.israel_now(now).date()
    first_day = today - dt.timedelta(days=CHECKIN_DAYS)
    israel_day = func.date(func.timezone("Asia/Jerusalem", SentNotification.sent_at))
    per_day = (
        select(SentNotification.user_id, israel_day.label("day"), func.count().label("n"))
        .where(
            SentNotification.reason == NotificationReason.NEW,
            SentNotification.sent_at >= now - dt.timedelta(days=CHECKIN_DAYS + 2),
            israel_day >= first_day,
            israel_day < today,
        )
        .group_by(SentNotification.user_id, israel_day)
        .subquery()
    )
    busy = (
        select(per_day.c.user_id, func.sum(per_day.c.n).label("total"))
        .where(per_day.c.n >= CHECKIN_MIN_PER_DAY)
        .group_by(per_day.c.user_id)
        .having(func.count() == CHECKIN_DAYS)
        .subquery()
    )
    conditions = [
        User.is_active.is_(True),
        User.notifications_enabled.is_(True),
        User.telegram_user_id.is_not(None),
        (User.checkin_sent_at.is_(None)) | (User.checkin_sent_at < now - CHECKIN_EVERY),
    ]
    if OWNER_TELEGRAM_USER_ID.isdigit():
        conditions.append(User.telegram_user_id != int(OWNER_TELEGRAM_USER_ID))
    rows = session.execute(select(User, busy.c.total).join(busy, busy.c.user_id == User.id).where(*conditions)).all()
    if not rows:
        return []
    active = set(
        session.scalars(
            select(ActivityDay.who).where(
                ActivityDay.day >= first_day,
                ActivityDay.who.in_(
                    [f"t{user.telegram_user_id}" for user, _ in rows] + [f"u{user.id}" for user, _ in rows]
                ),
            )
        )
    )
    return [
        (user, int(total))
        for user, total in rows
        if f"t{user.telegram_user_id}" not in active and f"u{user.id}" not in active
    ]


async def _run(session: Session, now: dt.datetime) -> int:
    if not 9 <= alert_hours.israel_now(now).hour < 12:
        return 0
    due = due_users(session, now)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not due or not token:
        return 0
    sent = 0
    bot = Bot(token=token)
    await bot.initialize()
    try:
        for user, total in due:
            lang = user.language or DEFAULT_LANG
            try:
                await bot.send_message(
                    chat_id=user.telegram_user_id,
                    text=bot_text("checkin.text", lang, days=CHECKIN_DAYS, count=total),
                    reply_markup=checkin_markup(lang),
                )
            except Forbidden:
                user.is_active = False  # blocked the bot: nothing will get through
                session.commit()
                continue
            except Exception:
                logger.exception("check-in: Telegram send failed for user_id=%s", user.id)
                continue
            user.checkin_sent_at = now
            session.commit()
            sent += 1
            await asyncio.sleep(0.3)
    finally:
        await bot.shutdown()
    return sent


def run_checkins(session: Session, now: dt.datetime | None = None) -> dict[str, int]:
    return {"checkins_sent": asyncio.run(_run(session, now or dt.datetime.now(dt.timezone.utc)))}
