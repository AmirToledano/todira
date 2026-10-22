""""Your access ends in a few days" reminder (2026-10-05).

The free Takbull flow sells 30 days of access with no auto-renewal, so a paying user's access just
stops at `paid_until`. Once per paid period, REMINDER_LEAD before it ends, this sends them one message
with a login-linked /upgrade link. Runs once per scraper run (hourly, main scraper only).

Who is reminded: paid (paid_until in the future, within REMINDER_LEAD), not already reminded for this
exact paid_until (User.renewal_reminder_for), and NOT on a live auto-renewing subscription (a user
whose Takbull subscription is active and not cancelled is renewed automatically — no reminder).

Sent on Telegram (free). A user who can't be reached right now (a failed send, or no Telegram linked yet) is simply
retried on the next run until paid_until passes. A user who blocked the bot is marked done (nothing will ever get
through).

2026-10-16 (owner): the same once-only message before the FREE TRIAL ends, TRIAL_REMINDER_LEAD before trial_ends_at
("your free trial ends tomorrow at 09:30"), to anyone still on the trial: not paying, no comp access, not paused, not the
owner. Recorded in User.trial_reminder_sent_at. Runs only 9:00-22:00 with the scraper, so a trial ending at night is
reminded the same morning ("today at 23:30").
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from telegram import Bot
from telegram.error import Forbidden

from todira_common import testimonials
from todira_common.bot_strings import bot_text
from todira_common.language import DEFAULT_LANG
from todira_common.models import User
from todira_common.uid_token import signed_login_query

logger = logging.getLogger(__name__)

REMINDER_LEAD = dt.timedelta(days=3)
TRIAL_REMINDER_LEAD = dt.timedelta(hours=24)
OWNER_TELEGRAM_USER_ID = os.environ.get("OWNER_TELEGRAM_USER_ID", "").strip()
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://todira.app").rstrip("/")
_ISRAEL = ZoneInfo("Asia/Jerusalem")


def _due_users(session: Session, now: dt.datetime) -> list[User]:
    return list(
        session.scalars(
            select(User).where(
                User.paid_until.is_not(None),
                User.paid_until > now,
                User.paid_until <= now + REMINDER_LEAD,
                or_(User.renewal_reminder_for.is_(None), User.renewal_reminder_for != User.paid_until),
                or_(
                    User.takbull_subscription_uniqid.is_(None),
                    User.cancel_at_period_end.is_(True),
                ),
            )
        )
    )


def _due_trial_users(session: Session, now: dt.datetime) -> list[User]:
    conditions = [
        User.trial_ends_at > now,
        User.trial_ends_at <= now + TRIAL_REMINDER_LEAD,
        User.trial_reminder_sent_at.is_(None),
        or_(User.paid_until.is_(None), User.paid_until <= now),
        User.free_access_granted.is_(False),
        User.is_active.is_(True),
    ]
    if OWNER_TELEGRAM_USER_ID.isdigit():
        conditions.append(or_(User.telegram_user_id.is_(None), User.telegram_user_id != int(OWNER_TELEGRAM_USER_ID)))
    return list(session.scalars(select(User).where(*conditions)))


def _trial_when(ends_at: dt.datetime, now: dt.datetime, lang: str) -> str:
    """"today at 23:30" / "tomorrow at 09:30" in Israel time (the date itself if neither)."""
    end_local, now_local = ends_at.astimezone(_ISRAEL), now.astimezone(_ISRAEL)
    time_text = end_local.strftime("%H:%M")
    days = (end_local.date() - now_local.date()).days
    if days == 0:
        return bot_text("trial.when_today", lang, time=time_text)
    if days == 1:
        return bot_text("trial.when_tomorrow", lang, time=time_text)
    return bot_text("trial.when_date", lang, date=end_local.strftime("%d.%m.%Y"))


def _trial_message(user: User, url: str, now: dt.datetime) -> str:
    lang = user.language or DEFAULT_LANG
    return bot_text("trial.reminder", lang, when=_trial_when(user.trial_ends_at, now, lang), url=url)


def _message(user: User, url: str) -> str:
    lang = user.language or DEFAULT_LANG
    date = user.paid_until.astimezone(_ISRAEL).strftime("%d.%m.%Y")
    return bot_text("renewal.reminder", lang, date=date, url=url)


async def _send_telegram(bot: Bot, user: User, compose=None) -> bool | None:
    """True = sent, None = can never be delivered (blocked), False = failed, retry later."""
    url = f"{WEBSITE_URL}/upgrade?{signed_login_query(user.telegram_user_id)}"
    try:
        await bot.send_message(chat_id=user.telegram_user_id, text=(compose or _message)(user, url))
        return True
    except Forbidden:
        return None
    except Exception:
        logger.exception("renewal reminder: Telegram send failed for user_id=%s", user.id)
        return False


async def _run_trial(session: Session, now: dt.datetime) -> int:
    users = [user for user in _due_trial_users(session, now) if user.telegram_user_id]
    if not users:
        return 0
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return 0
    sent = 0
    bot = Bot(token=token)
    await bot.initialize()
    try:
        for user in users:
            result = await _send_telegram(bot, user, compose=lambda u, url: _trial_message(u, url, now))
            if result is False:
                continue  # retry next run, while the trial lasts
            user.trial_reminder_sent_at = now
            session.commit()
            if result:
                sent += 1
            await asyncio.sleep(0.3)
    finally:
        await bot.shutdown()
    return sent


async def _run(session: Session, now: dt.datetime) -> int:
    users = _due_users(session, now)
    if not users:
        return 0
    sent = 0
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    bot_cm = Bot(token=token) if token else None
    try:
        if bot_cm is not None:
            await bot_cm.initialize()
        for user in users:
            result: bool | None = False
            if user.telegram_user_id and bot_cm is not None:
                result = await _send_telegram(bot_cm, user)
            if result is False:
                continue  # retry next run
            user.renewal_reminder_for = user.paid_until
            session.commit()
            if result:
                sent += 1
            await asyncio.sleep(0.3)
    finally:
        if bot_cm is not None:
            await bot_cm.shutdown()
    return sent


FOUND_ASK_AFTER = dt.timedelta(days=2)
FOUND_ASK_WITHIN = dt.timedelta(days=10)


def _due_found_users(session: Session, now: dt.datetime) -> list[User]:
    """2026-10-22 (owner): "did you find a flat?" a couple of days after a pass or the free trial ended without a new
    one (todira_common/testimonials.py). Mornings only (09:00-12:00 Israel); at most once per 60 days per user."""
    ended = or_(
        (User.paid_until.is_not(None)) & (User.paid_until <= now - FOUND_ASK_AFTER)
        & (User.paid_until > now - FOUND_ASK_WITHIN),
        (User.paid_until.is_(None)) & (User.trial_ends_at <= now - FOUND_ASK_AFTER)
        & (User.trial_ends_at > now - FOUND_ASK_WITHIN),
    )
    conditions = [User.telegram_user_id.is_not(None), User.free_access_granted.is_(False), ended]
    if OWNER_TELEGRAM_USER_ID.isdigit():
        conditions.append(User.telegram_user_id != int(OWNER_TELEGRAM_USER_ID))
    users = session.scalars(select(User).where(*conditions)).all()
    return [user for user in users if not testimonials.asked_recently(session, user.id, now)]


async def _run_found(session: Session, now: dt.datetime) -> int:
    if not 9 <= now.astimezone(_ISRAEL).hour < 12:
        return 0
    users = _due_found_users(session, now)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not users or not token:
        return 0
    sent = 0
    bot = Bot(token=token)
    await bot.initialize()
    try:
        for user in users:
            lang = user.language or DEFAULT_LANG
            try:
                await bot.send_message(
                    chat_id=user.telegram_user_id,
                    text=bot_text("found_ask.question", lang),
                    reply_markup=testimonials.found_keyboard(lang),
                )
            except Forbidden:
                pass  # blocked the bot - marked asked below so it isn't tried again
            except Exception:
                logger.exception("found question: Telegram send failed for user_id=%s", user.id)
                continue
            else:
                sent += 1
            testimonials.mark_asked(session, user.id, now)
            await asyncio.sleep(0.3)
    finally:
        await bot.shutdown()
    return sent


def run_renewal_reminders(session: Session) -> dict[str, int]:
    """Returns {"renewal_reminders_sent": n} for the run summary."""
    now = dt.datetime.now(dt.timezone.utc)
    summary = {"renewal_reminders_sent": asyncio.run(_run(session, now))}
    try:
        summary["trial_reminders_sent"] = asyncio.run(_run_trial(session, now))
    except Exception:
        session.rollback()
        logger.exception("trial reminder step failed")
    try:
        summary["found_questions_sent"] = asyncio.run(_run_found(session, now))
    except Exception:
        session.rollback()
        logger.exception("found question step failed")
    return summary
