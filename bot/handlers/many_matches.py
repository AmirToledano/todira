"""2026-10-27 (owner-approved, plan item 2): a new search that brings more than 30 new apartments a day gets ONE
question at the end of onboarding: "That's a lot 🙂 only 9 of them have a balcony. Is a balcony a must?", with
"yes, only with a balcony" / "no, keep it as is". Never more than one question.

The feature asked about is the one that narrows the search the most while still leaving a few a day. A listing whose
feature is unknown still matches a required feature (todira_common.matching gives it the benefit of the doubt), so
the number shown is what the search would really bring after "yes", and a feature mostly unknown is not offered at
all - its number would not mean "with a balcony".
"""
from __future__ import annotations

import asyncio

from todira_common.bot_strings import bot_text
from todira_common.db import get_session
from todira_common.models import User
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

MANY_PER_DAY = 30
_MIN_AFTER_PER_DAY = 3
_MAX_UNKNOWN_SHARE = 0.2

# (name in the strings and buttons, listing column, filter switch)
FEATURES = (
    ("balcony", "has_balcony", "require_balcony"),
    ("parking", "has_parking", "require_parking"),
    ("elevator", "has_elevator", "require_elevator"),
)


def pick_question(rows, days: int, filter_row) -> tuple[str, int] | None:
    """(feature, new apartments a day with it) to ask about, or None. `rows` are the search's matches first seen in the
    last `days` days."""
    per_day = len(rows) / days
    if per_day <= MANY_PER_DAY:
        return None
    best = None
    for name, column, switch in FEATURES:
        if getattr(filter_row, switch, False):
            continue
        kept = [row for row in rows if getattr(row, column) is not False]
        if not kept:
            continue
        unknown = sum(1 for row in kept if getattr(row, column) is None)
        after = round(len(kept) / days)
        if unknown / len(kept) > _MAX_UNKNOWN_SHARE or not _MIN_AFTER_PER_DAY <= after <= per_day * 0.6:
            continue
        if best is None or after < best[1]:
            best = (name, after)
    return best


def question_markup(feature: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(bot_text(f"many.yes_{feature}", lang), callback_data=f"mm:{feature}")],
        [InlineKeyboardButton(bot_text("many.no", lang), callback_data="mm:no")],
    ])


def _require_sync(telegram_user_id: int, switch: str) -> None:
    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
        if user is not None and user.filter is not None:
            setattr(user.filter, switch, True)
            session.commit()


async def _answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    choice = query.data.split(":", 1)[1]
    switch = next((s for name, _, s in FEATURES if name == choice), None)
    if switch is not None:
        await asyncio.to_thread(_require_sync, update.effective_user.id, switch)
    await query.answer("✅")
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:  # an old message can't be edited any more - the answer still counts
        pass


def build_many_matches_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(_answer, pattern=r"^mm:(balcony|parking|elevator|no)$")
