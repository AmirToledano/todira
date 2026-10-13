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

from todira_common.bot_strings import bot_text
from todira_common.language import DEFAULT_LANG
from todira_common.models import User
from todira_common.uid_token import signed_login_query

logger = logging.getLogger(__name__)

REMINDER_LEAD = dt.timedelta(days=3)
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


def _message(user: User, url: str) -> str:
    lang = user.language or DEFAULT_LANG
    date = user.paid_until.astimezone(_ISRAEL).strftime("%d.%m.%Y")
    return bot_text("renewal.reminder", lang, date=date, url=url)


async def _send_telegram(bot: Bot, user: User) -> bool | None:
    """True = sent, None = can never be delivered (blocked), False = failed, retry later."""
    url = f"{WEBSITE_URL}/upgrade?{signed_login_query(user.telegram_user_id)}"
    try:
        await bot.send_message(chat_id=user.telegram_user_id, text=_message(user, url))
        return True
    except Forbidden:
        return None
    except Exception:
        logger.exception("renewal reminder: Telegram send failed for user_id=%s", user.id)
        return False


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


def run_renewal_reminders(session: Session) -> dict[str, int]:
    """Returns {"renewal_reminders_sent": n} for the run summary."""
    now = dt.datetime.now(dt.timezone.utc)
    return {"renewal_reminders_sent": asyncio.run(_run(session, now))}
