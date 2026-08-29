"""Free-text onboarding for brand-new users — mirrors the reference bot's casual Q&A flow
(deal type -> city -> rooms). Tries simple keyword/regex parsing first (fast, free, no external
dependency), and only falls back to a Gemini call (gemini_client.py) when that comes up empty —
covers typos ("שגירות"), abbreviations ("ראשל\"צ"), and misspellings ("רמת גם") that plain
substring matching can't, without paying for an API call on every message. If GEMINI_API_KEY
isn't set, the fallback is a no-op and behavior is identical to the old regex-only version.
(We skip asking for the user's name, unlike the reference bot — Telegram already gives us
`first_name`, which /start's own welcome message already uses.)

This does NOT replace the menu-driven `/filter` conversation (handlers/filter_conversation.py)
— it's a friendlier on-ramp that saves a first, simple Filter row; /filter remains available
afterwards for full control over every field.

`/start` is owned entirely by this ConversationHandler (see build_onboarding_handler): its entry
point calls handlers.start.start() to send the normal welcome and upsert/reactivate the user,
then only continues into the Q&A states if the user doesn't have a filter yet — a returning user
just gets the plain welcome and the conversation ends immediately.
"""
from __future__ import annotations

import re

import cities
import gemini_client
import keyboards as kb
from dorin_common.cards import format_caption, listing_keyboard
from dorin_common.db import get_session
from dorin_common.models import Filter
from dorin_common.users import get_or_create_user
from handlers.apartments import find_matching_listings
from handlers.start import start
from sqlalchemy import select
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters as tg_filters,
)

AWAIT_DEAL_TYPE, AWAIT_CITIES, AWAIT_ROOMS = range(3)

DEAL_TYPE_KEYWORDS = (
    ("sublet", ("סבלט", "סאבלט")),
    ("sale", ("מכיר", "קני", "לקנות", "רכיש")),
    ("rent", ("שכיר", "להשכיר", "שכר")),
)


def _parse_deal_type(text: str) -> str | None:
    for value, keywords in DEAL_TYPE_KEYWORDS:
        if any(kw in text for kw in keywords):
            return value
    return None


def _parse_cities(text: str) -> list[str]:
    matched: list[str] = []
    for segment in re.split(r"[,\n]", text):
        segment = segment.strip()
        if not segment:
            continue
        found = cities.find_matches(segment, limit=1)
        if found and found[0] not in matched:
            matched.append(found[0])
    return matched


def _parse_rooms(text: str) -> tuple[float, float] | None:
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None
    return min(numbers), max(numbers)


async def onboarding_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await start(update, context)  # normal welcome + create/reactivate the user row

    with get_session() as session:
        user = get_or_create_user(session, update.effective_user)
        has_filter = session.scalar(select(Filter.id).where(Filter.user_id == user.id)) is not None

    if has_filter:
        return ConversationHandler.END

    context.user_data["onboarding"] = {}
    await update.message.reply_text(
        "אני יכול לעזור לך למצוא דירה בכמה שאלות קצרות (או שאפשר לדלג ולהגדיר הכל ידנית "
        "עם /filter בכל שלב) 🙂\n\nמה את/ה מחפש/ת — שכירות, מכירה או סבלט?"
    )
    return AWAIT_DEAL_TYPE


async def _handle_deal_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text or ""
    deal_type = _parse_deal_type(text) or gemini_client.parse_deal_type(text)
    if deal_type is None:
        await update.message.reply_text(
            "לא הצלחתי להבין 😅 את/ה מחפש/ת שכירות, מכירה או סבלט?"
        )
        return AWAIT_DEAL_TYPE

    context.user_data["onboarding"]["deal_type"] = deal_type
    await update.message.reply_text(
        "מעולה! ואיזה עיר או אזור מעניינים אותך? (אפשר כמה, מופרדות בפסיקים)"
    )
    return AWAIT_CITIES


async def _handle_cities(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text or ""
    matched = _parse_cities(text) or gemini_client.parse_cities(text, cities.CITIES)
    if not matched:
        await update.message.reply_text(
            "לא זיהיתי אף עיר מהרשימה שלי 🤔 נסה/י שוב (למשל: תל אביב יפו, ירושלים):"
        )
        return AWAIT_CITIES

    context.user_data["onboarding"]["cities"] = matched
    await update.message.reply_text(
        f"נרשם: {', '.join(matched)} ✅\nוכמה חדרים בערך את/ה מחפש/ת?"
    )
    return AWAIT_ROOMS


async def _handle_rooms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text or ""
    rooms = _parse_rooms(text) or gemini_client.parse_rooms(text)
    if rooms is None:
        await update.message.reply_text("לא הצלחתי למצוא מספר 😅 כמה חדרים בערך? (למשל 3, או 2.5)")
        return AWAIT_ROOMS

    data = context.user_data.pop("onboarding")
    rooms_min, rooms_max = rooms

    with get_session() as session:
        user = get_or_create_user(session, update.effective_user)
        filter_row = Filter(
            user_id=user.id,
            deal_type=data["deal_type"],
            cities=data["cities"],
            rooms_min=rooms_min,
            rooms_max=rooms_max,
        )
        session.add(filter_row)
        session.commit()
        example = find_matching_listings(session, user.id, filter_row, limit=1)

    rooms_line = (
        f"🛏️ חדרים: {rooms_min:g}"
        if rooms_min == rooms_max
        else f"🛏️ חדרים: {rooms_min:g}–{rooms_max:g}"
    )
    summary = (
        "✅ <b>הסינון החדש שלך:</b>\n"
        f"🏷️ סוג עסקה: {kb.DEAL_TYPE_LABELS.get(data['deal_type'], data['deal_type'])}\n"
        f"📍 ערים: {', '.join(data['cities'])}\n"
        f"{rooms_line}"
    )
    await update.message.reply_text(summary, parse_mode=ParseMode.HTML)
    await update.message.reply_text(
        "אפשר תמיד להרחיב את הסינון (מחיר, קומה, דרישות ועוד) עם /filter 🎛️"
    )

    if example:
        await update.message.reply_text("👀 הנה דוגמה לדירה שתואמת:")
        await update.message.reply_text(
            format_caption(example[0]),
            reply_markup=listing_keyboard(example[0].id),
            parse_mode=ParseMode.HTML,
        )

    return ConversationHandler.END


def build_onboarding_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", onboarding_entry)],
        states={
            AWAIT_DEAL_TYPE: [MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, _handle_deal_type)],
            AWAIT_CITIES: [MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, _handle_cities)],
            AWAIT_ROOMS: [MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, _handle_rooms)],
        },
        fallbacks=[CommandHandler("start", onboarding_entry)],
        name="onboarding_conversation",
    )
