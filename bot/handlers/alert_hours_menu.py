"""Choosing the hours and days alerts come in (2026-10-31, owner). Opened by "⏰ alert hours" in /filter and by the button
under the last onboarding message; every later press edits the same message.

hours:menu sends the menu as a new message. hours:from asks for the first hour, hours:f:<h> for the last one, and
hours:t:<from>:<to> saves both. hours:wk switches Friday and Saturday on or off, hours:all goes back to every hour, and
hours:done closes the menu. The rules live in todira_common.alert_hours.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, ContextTypes

from todira_common import alert_hours
from todira_common.bot_strings import bot_text
from todira_common.db import get_session
from todira_common.language import DEFAULT_LANG
from todira_common.models import User


def _hour(h: int) -> str:
    return f"{h:02d}:00"


def _apply_sync(telegram_user_id: int, action: str, args: list[str]):
    """Applies a change (if any) and returns what the menu shows: (lang, from, to, weekend, custom)."""
    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
        if user is None:
            return None
        if action == "t":
            start, end = int(args[0]), int(args[1])
            if start in alert_hours.FROM_HOURS and end in alert_hours.TO_HOURS and start < end:
                user.alert_from_hour, user.alert_to_hour = start, end
        elif action == "wk":
            user.alerts_on_weekend = not user.alerts_on_weekend
        elif action == "all":
            user.alert_from_hour = user.alert_to_hour = None
        session.commit()
        start_text, end_text = alert_hours.hours_pair(user)
        return (
            user.language or DEFAULT_LANG, start_text, end_text, user.alerts_on_weekend, alert_hours.has_custom_hours(user)
        )


def _menu(lang: str, start_text: str, end_text: str, weekend: bool, custom: bool) -> tuple[str, InlineKeyboardMarkup]:
    # 2026-10-31 (owner's wording): the default says so and promises the next morning; a choice of their own says when
    # their hours start instead, since "the next morning" would be wrong for, say, 16:00 to 23:00
    is_default = weekend and not custom
    days = bot_text("hours.days_all" if weekend else "hours.days_weekdays", lang)
    lines = [
        bot_text("hours.heading", lang),
        bot_text("hours.now_default" if is_default else "hours.now_custom", lang, days=days, start=start_text, end=end_text),
        bot_text("hours.outside_default" if is_default else "hours.outside_custom", lang),
    ]
    if weekend:
        lines.append(bot_text("hours.weekend_hint", lang))
    text = "\n\n".join(lines)
    rows = [
        [InlineKeyboardButton(bot_text("hours.btn_change", lang), callback_data="hours:from")],
        [InlineKeyboardButton(bot_text("hours.btn_weekend_on" if weekend else "hours.btn_weekend_off", lang),
                              callback_data="hours:wk")],
    ]
    if custom:
        rows.append([InlineKeyboardButton(bot_text("hours.btn_all", lang), callback_data="hours:all")])
    rows.append([InlineKeyboardButton(bot_text("hours.btn_done", lang), callback_data="hours:done")])
    return text, InlineKeyboardMarkup(rows)


def _hour_rows(hours, callback) -> list[list[InlineKeyboardButton]]:
    buttons = [InlineKeyboardButton(_hour(h), callback_data=callback(h)) for h in hours]
    return [buttons[i:i + 4] for i in range(0, len(buttons), 4)]


async def _edit(query, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except BadRequest:
        pass  # the same menu pressed twice: Telegram refuses an edit that changes nothing


async def _answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    action, args = parts[1], parts[2:]
    state = await asyncio.to_thread(_apply_sync, update.effective_user.id, action, args)
    if state is None:
        await query.answer()
        return
    lang = state[0]
    if action == "done":
        await query.answer("✅")
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except BadRequest:
            pass
        return
    await query.answer()
    if action == "from":
        rows = _hour_rows(alert_hours.FROM_HOURS, lambda h: f"hours:f:{h}")
        await _edit(query, bot_text("hours.ask_from", lang), InlineKeyboardMarkup(rows))
        return
    if action == "f":
        start = int(args[0])
        ends = [h for h in alert_hours.TO_HOURS if h > start]
        rows = _hour_rows(ends, lambda h: f"hours:t:{start}:{h}")
        await _edit(query, bot_text("hours.ask_to", lang), InlineKeyboardMarkup(rows))
        return
    text, markup = _menu(*state)
    if action == "menu":
        await query.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        return
    await _edit(query, text, markup)


def build_alert_hours_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(_answer, pattern=r"^hours:(menu|from|f:\d+|t:\d+:\d+|wk|all|done)$")
