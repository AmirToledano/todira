"""/profile — plain-text profile/stats. Rendered in-chat rather than deep-linking to a web page,
since Phase 1 has no website yet (see plan Section 5)."""
from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from todira_common.bot_strings import bot_text
from todira_common.db import get_session
from todira_common.language import DEFAULT_LANG
from todira_common.models import Filter, SentNotification, User


def _profile_text(user: User, filter_row: Filter | None, notifications_sent: int, lang: str) -> str:
    status = bot_text("profile.status_active" if user.is_active else "profile.status_paused", lang)
    notif_status = bot_text(
        "profile.notifications_on" if user.notifications_enabled else "profile.notifications_off", lang
    )
    lines = [
        bot_text("profile.header", lang),
        bot_text("profile.status_line", lang, status=status),
        bot_text("profile.notifications_line", lang, status=notif_status),
        bot_text("profile.total_sent_line", lang, count=notifications_sent),
    ]
    if filter_row is None:
        lines.append(bot_text("profile.no_filter_line", lang))
    return "\n".join(lines)


def _keyboard(user: User, lang: str) -> InlineKeyboardMarkup:
    active_label = bot_text("profile.btn_pause" if user.is_active else "profile.btn_resume", lang)
    notif_label = bot_text(
        "profile.btn_notif_off" if user.notifications_enabled else "profile.btn_notif_on", lang
    )
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(active_label, callback_data="profile:toggle_active")],
            [InlineKeyboardButton(notif_label, callback_data="profile:toggle_notifications")],
        ]
    )


def _load_profile_sync(tg_user):
    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
        if user is None:
            return None
        lang = user.language or DEFAULT_LANG
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user.id))
        notifications_sent = (
            session.scalar(
                select(func.count(SentNotification.id)).where(
                    SentNotification.user_id == user.id
                )
            )
            or 0
        )
        return _profile_text(user, filter_row, notifications_sent, lang), _keyboard(user, lang)


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # asyncio.to_thread — see handlers/start.py's _upsert_user_sync comment: a synchronous DB
    # call directly on the event loop would freeze every other user's bot interaction too, not
    # just this one, since PTB processes updates one at a time by default.
    result = await asyncio.to_thread(_load_profile_sync, update.effective_user)
    if result is None:
        await update.message.reply_text(bot_text("profile.not_registered", DEFAULT_LANG))
        return
    text, markup = result
    await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


def _toggle_profile_sync(tg_user, query_data: str):
    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
        if user is None:
            return None
        if query_data == "profile:toggle_active":
            user.is_active = not user.is_active
        elif query_data == "profile:toggle_notifications":
            user.notifications_enabled = not user.notifications_enabled
        session.commit()

        lang = user.language or DEFAULT_LANG
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user.id))
        notifications_sent = (
            session.scalar(
                select(func.count(SentNotification.id)).where(
                    SentNotification.user_id == user.id
                )
            )
            or 0
        )
        return _profile_text(user, filter_row, notifications_sent, lang), _keyboard(user, lang)


async def profile_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    result = await asyncio.to_thread(_toggle_profile_sync, update.effective_user, query.data)
    if result is None:
        await query.answer()
        return
    text, markup = result
    await query.answer()
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


def build_profile_handlers() -> list:
    return [
        CommandHandler("profile", profile),
        CallbackQueryHandler(profile_toggle_callback, pattern=r"^profile:"),
    ]
