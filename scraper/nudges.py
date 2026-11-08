"""Occasional Telegram messages that help people get more out of Todira (2026-11-08, owner: "most users are on Telegram,
so now and then we should also send messages about the subscription, the price, the benefits"; approved plan).

Three kinds, at most one of them a week per person (the trial/paid reminders, check-in and win-back are separate and not
counted), only between 09:00 and 12:00 Israel and inside the person's own alert hours and days:

- weekly: Sunday, to anyone with access who got at least WEEKLY_MIN new flats in the last 7 days: how many flats and price
  drops we sent, with a button to see them on the site. Paying people get only this one.
- tip: once, on the third day of the free trial: one thing they have not used yet (alert hours, else inviting a friend).
- price: once, TRIAL_PRICE_LEAD before the trial ends, to someone who got at least PRICE_MIN flats: what they got and
  what the month costs a day, with a button to /upgrade signed in.

NOT WIRED IN YET (2026-11-08): the texts (nudge.*) and the bot button are still to come; scraper/main.py does not call it.

Every message has a "fewer messages like this" button (bot/handlers/nudges.py); after it, none of these is sent to that
person again. State lives in app_flags (_FLAG): {user_id: {"last": iso, "done": [kinds], "off": bool}}. Each send is
counted in activity as nudge_<kind> and a tap on its link as src_nudge_<kind>, so the Sunday report shows both.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden
from todira_common import activity, alert_hours, app_flags, referrals
from todira_common.access import PLAN_PRICES_ILS, has_full_access
from todira_common.bot_strings import bot_text
from todira_common.enums import NotificationReason
from todira_common.language import DEFAULT_LANG
from todira_common.models import SentNotification, User
from todira_common.uid_token import signed_login_query

logger = logging.getLogger(__name__)

_FLAG = "nudges_state"
EVERY = dt.timedelta(days=7)
SUNDAY = 6
WEEKLY_MIN = 3
TIP_AFTER = dt.timedelta(days=2)  # the third day of the trial
TRIAL_PRICE_LEAD = dt.timedelta(hours=48)
PRICE_MIN = 3
MONTH_PLAN = "pass_30"
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://todira.app").rstrip("/")


def _paying(user: User, now: dt.datetime) -> bool:
    return user.paid_until is not None and user.paid_until > now


def _on_trial(user: User, now: dt.datetime) -> bool:
    return (
        user.trial_ends_at is not None and user.trial_ends_at > now and not _paying(user, now)
        and not user.free_access_granted
    )


def _counts(session: Session, user_id: int, since: dt.datetime) -> tuple[int, int]:
    """(new flats, price drops) sent to this person since `since`."""
    rows = dict(session.execute(
        select(SentNotification.reason, func.count()).where(
            SentNotification.user_id == user_id, SentNotification.sent_at >= since,
            SentNotification.reason.in_([NotificationReason.NEW, NotificationReason.PRICE_DROP]),
        ).group_by(SentNotification.reason)
    ).all())
    return int(rows.get(NotificationReason.NEW, 0)), int(rows.get(NotificationReason.PRICE_DROP, 0))


def pick(session: Session, user: User, state: dict, now: dt.datetime) -> tuple[str, dict] | None:
    """(kind, text arguments) of the one message due for this person now, or None."""
    mine = state.get(str(user.id), {})
    if mine.get("off"):
        return None
    last = mine.get("last")
    if last and now - dt.datetime.fromisoformat(last) < EVERY:
        return None
    done = set(mine.get("done", []))
    if _on_trial(user, now):
        if "price" not in done and user.trial_ends_at - now <= TRIAL_PRICE_LEAD:
            new, _ = _counts(session, user.id, user.created_at or now - dt.timedelta(days=30))
            if new >= PRICE_MIN:
                price = PLAN_PRICES_ILS[MONTH_PLAN]
                per_day = (price / Decimal(30)).quantize(Decimal("0.01"))
                return "price", {"count": new, "price": f"{price:.2f}", "per_day": f"{per_day:.2f}"}
        if "tip" not in done and user.created_at is not None and now - user.created_at >= TIP_AFTER:
            return ("tip_hours" if not alert_hours.has_custom_hours(user) else "tip_invite"), {}
    if alert_hours.israel_now(now).weekday() == SUNDAY and has_full_access(user):
        week = alert_hours.israel_now(now).strftime("%G-%V")
        if f"weekly:{week}" not in done:
            new, drops = _counts(session, user.id, now - dt.timedelta(days=7))
            if new >= WEEKLY_MIN:
                return "weekly", {"count": new, "drops": drops, "week": week}
    return None


def _markup(kind: str, user: User, lang: str) -> InlineKeyboardMarkup:
    rows = []
    login = signed_login_query(user.telegram_user_id)
    if kind == "weekly":
        rows.append([InlineKeyboardButton(bot_text("nudge.weekly_btn", lang),
                                          url=f"{WEBSITE_URL}/apartments?{login}&src=nudge_weekly")])
    elif kind == "price":
        rows.append([InlineKeyboardButton(bot_text("nudge.price_btn", lang),
                                          url=f"{WEBSITE_URL}/upgrade?{login}&src=nudge_price")])
    rows.append([InlineKeyboardButton(bot_text("nudge.less_btn", lang), callback_data="ng:off")])
    return InlineKeyboardMarkup(rows)


def text(kind: str, user: User, args: dict, lang: str) -> str:
    if kind == "weekly":
        key = "nudge.weekly_drops" if args["drops"] else "nudge.weekly"
        return bot_text(key, lang, count=args["count"], drops=args["drops"])
    if kind == "price":
        return bot_text("nudge.price", lang, count=args["count"], price=args["price"], per_day=args["per_day"])
    if kind == "tip_invite":
        return bot_text("nudge.tip_invite", lang, link=referrals.invite_link(user.id), days=referrals.REWARD_DAYS)
    return bot_text("nudge.tip_hours", lang)


def due_users(session: Session) -> list[User]:
    return list(session.scalars(select(User).where(
        User.is_active.is_(True), User.notifications_enabled.is_(True), User.telegram_user_id.is_not(None),
    )))


async def _run(session: Session, now: dt.datetime) -> int:
    if not 9 <= alert_hours.israel_now(now).hour < 12:
        return 0
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return 0
    state: dict = json.loads(app_flags.get_flag(session, _FLAG) or "{}")
    due = []
    for user in due_users(session):
        if not alert_hours.in_window(user, now):
            continue
        chosen = pick(session, user, state, now)
        if chosen:
            due.append((user, *chosen))
    if not due:
        return 0
    sent = 0
    bot = Bot(token=token)
    await bot.initialize()
    try:
        for user, kind, args in due:
            lang = user.language or DEFAULT_LANG
            try:
                await bot.send_message(chat_id=user.telegram_user_id, text=text(kind, user, args, lang),
                                       reply_markup=_markup(kind, user, lang), disable_web_page_preview=True)
            except Forbidden:
                user.is_active = False  # blocked the bot
                session.commit()
                activity.record(f"nudge_blocked_{kind.split('_')[0]}", f"t{user.telegram_user_id}")
                continue
            except Exception:
                logger.exception("nudge: Telegram send failed for user_id=%s", user.id)
                continue
            mine = state.setdefault(str(user.id), {})
            mine["last"] = now.isoformat()
            done = mine.setdefault("done", [])
            done.append(f"weekly:{args['week']}" if kind == "weekly" else kind.split("_")[0])
            mine["done"] = done[-12:]
            app_flags.set_flag(session, _FLAG, json.dumps(state))
            activity.record(f"nudge_{kind.split('_')[0]}", f"t{user.telegram_user_id}")
            sent += 1
            await asyncio.sleep(0.3)
    finally:
        await bot.shutdown()
    return sent


def turn_off(session: Session, user_id: int) -> None:
    """The "fewer messages like this" button: none of these messages is sent to this person again."""
    state: dict = json.loads(app_flags.get_flag(session, _FLAG) or "{}")
    state.setdefault(str(user_id), {})["off"] = True
    app_flags.set_flag(session, _FLAG, json.dumps(state))


def run_nudges(session: Session, now: dt.datetime | None = None) -> dict[str, int]:
    return {"nudges_sent": asyncio.run(_run(session, now or dt.datetime.now(dt.timezone.utc)))}
