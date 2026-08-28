"""/profile — plain-text profile/stats. Rendered in-chat rather than deep-linking to a web page,
since Phase 1 has no website yet (see plan Section 5)."""
from __future__ import annotations

from sqlalchemy import func, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from dorin_common.db import get_session
from dorin_common.models import Filter, SentNotification, User


def _profile_text(user: User, filter_row: Filter | None, notifications_sent: int) -> str:
    lines = [
        "👤 <b>הפרופיל שלך</b>",
        f"סטטוס חיפוש: {'🟢 פעיל' if user.is_active else '⏸️ מושהה'}",
        f"התראות: {'🔔 מופעלות' if user.notifications_enabled else '🔕 כבויות'}",
        f'סה"כ התראות שנשלחו: {notifications_sent}',
    ]
    if filter_row is None:
        lines.append("\nעדיין לא הגדרת סינון. שלח/י /filter כדי להתחיל.")
    return "\n".join(lines)


def _keyboard(user: User) -> InlineKeyboardMarkup:
    active_label = "⏸️ השהה חיפוש" if user.is_active else "▶️ המשך חיפוש"
    notif_label = "🔕 כבה התראות" if user.notifications_enabled else "🔔 הפעל התראות"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(active_label, callback_data="profile:toggle_active")],
            [InlineKeyboardButton(notif_label, callback_data="profile:toggle_notifications")],
        ]
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
        if user is None:
            await update.message.reply_text("שלח/י /start כדי להתחיל.")
            return
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user.id))
        notifications_sent = (
            session.scalar(
                select(func.count(SentNotification.id)).where(
                    SentNotification.user_id == user.id
                )
            )
            or 0
        )
        text = _profile_text(user, filter_row, notifications_sent)
        markup = _keyboard(user)

    await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


async def profile_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    tg_user = update.effective_user
    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
        if user is None:
            await query.answer()
            return
        if query.data == "profile:toggle_active":
            user.is_active = not user.is_active
        elif query.data == "profile:toggle_notifications":
            user.notifications_enabled = not user.notifications_enabled
        session.commit()

        filter_row = session.scalar(select(Filter).where(Filter.user_id == user.id))
        notifications_sent = (
            session.scalar(
                select(func.count(SentNotification.id)).where(
                    SentNotification.user_id == user.id
                )
            )
            or 0
        )
        text = _profile_text(user, filter_row, notifications_sent)
        markup = _keyboard(user)

    await query.answer()
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


def build_profile_handlers() -> list:
    return [
        CommandHandler("profile", profile),
        CallbackQueryHandler(profile_toggle_callback, pattern=r"^profile:"),
    ]
