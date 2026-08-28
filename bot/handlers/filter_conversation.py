"""Menu-driven /filter conversation — see plan Section 5 for why a menu-driven design was chosen
over a strict linear ConversationHandler for ~20 fields.

The in-progress filter lives in `context.user_data["draft"]` (a plain dict) and is only written
to the database when the user taps "Save" — a mid-edit /start or bot restart just discards the
draft, it never leaves partial garbage in the `filters` table. Conversation/user_data state is
in-memory (the PTB default) for Phase 1 — a bot restart mid-edit loses progress, a documented
limitation, not a bug (see plan Section 5).

Scope note: neighborhoods_include/exclude and streets_include/exclude exist in the DB schema
(dorin_common.models.Filter) but don't have a menu screen here yet — they weren't included in
this first pass to keep the conversation shippable; add a "neighborhoods"/"streets" category
following the exact same add/remove pattern as `loc` (cities) whenever that's wanted next.
"""
from __future__ import annotations

import datetime as dt
import logging

import cities
import keyboards as kb
from dorin_common.cards import format_caption, listing_keyboard
from dorin_common.db import get_session
from dorin_common.models import Filter, User
from dorin_common.schemas import FilterData
from dorin_common.users import get_or_create_user
from handlers.apartments import find_matching_listings
from pydantic import ValidationError
from sqlalchemy import select
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters as tg_filters,
)

logger = logging.getLogger(__name__)

MENU, AWAIT_TEXT = range(2)

FILTER_FIELDS = list(FilterData.model_fields.keys())

NUMERIC_INT_FIELDS = {"price_min", "price_max", "floor_min", "floor_max", "min_area_sqm"}
NUMERIC_FLOAT_FIELDS = {"rooms_min", "rooms_max"}
DATE_FIELDS = {"move_in_earliest", "move_in_latest"}
FIELD_TO_CATEGORY = {
    "price_min": "price",
    "price_max": "price",
    "rooms_min": "rooms",
    "rooms_max": "rooms",
    "floor_min": "floor",
    "floor_max": "floor",
    "min_area_sqm": "area",
    "move_in_earliest": "move",
    "move_in_latest": "move",
}


def _default_draft() -> dict:
    return FilterData().model_dump()


def _draft_from_filter(filter_row: Filter | None) -> dict:
    if filter_row is None:
        return _default_draft()
    return {field: getattr(filter_row, field) for field in FILTER_FIELDS}


def _category_view(draft: dict, category: str):
    """Pure function: (title, keyboard) for a given category — reused by both the
    CallbackQueryHandler (edits the existing message) and the text-input handler (sends a new
    message, since the original inline-keyboard message was already replaced by a text prompt)."""
    if category == "dt":
        return kb.CATEGORY_TITLES["dt"], kb.single_select_keyboard(
            kb.DEAL_TYPE_LABELS, draft["deal_type"], "dt"
        )
    if category == "pt":
        return kb.CATEGORY_TITLES["pt"], kb.multi_select_keyboard(
            kb.PROPERTY_TYPE_LABELS, draft["property_types"], "pt"
        )
    if category == "loc":
        return kb.CATEGORY_TITLES["loc"], kb.location_keyboard(draft)
    if category == "price":
        return kb.CATEGORY_TITLES["price"], kb.price_keyboard(draft)
    if category == "rooms":
        return kb.CATEGORY_TITLES["rooms"], kb.rooms_keyboard(draft)
    if category == "floor":
        return kb.CATEGORY_TITLES["floor"], kb.floor_keyboard(draft)
    if category == "req":
        return kb.CATEGORY_TITLES["req"], kb.requirements_keyboard(draft)
    if category == "safe":
        return kb.CATEGORY_TITLES["safe"], kb.single_select_keyboard(
            kb.SAFE_ROOM_LABELS, draft["safe_room_pref"], "safe"
        )
    if category == "furn":
        return kb.CATEGORY_TITLES["furn"], kb.single_select_keyboard(
            kb.FURNITURE_LABELS, draft["furniture_pref"], "furn"
        )
    if category == "area":
        return kb.CATEGORY_TITLES["area"], kb.area_keyboard(draft)
    if category == "kw":
        return kb.CATEGORY_TITLES["kw"], kb.keywords_keyboard(draft)
    if category == "move":
        return kb.CATEGORY_TITLES["move"], kb.move_in_keyboard(draft)
    if category == "adv":
        return kb.CATEGORY_TITLES["adv"], kb.advanced_keyboard(draft)
    return kb.render_root_summary(draft), kb.root_keyboard()


async def _show_category(query, draft: dict, category: str) -> int:
    title, markup = _category_view(draft, category)
    await query.edit_message_text(title, reply_markup=markup, parse_mode=ParseMode.HTML)
    return MENU


async def _send_category(message, draft: dict, category: str) -> None:
    title, markup = _category_view(draft, category)
    await message.reply_text(title, reply_markup=markup, parse_mode=ParseMode.HTML)


def _apply_single_select(draft: dict, ns: str, value: str) -> None:
    if ns == "dt":
        draft["deal_type"] = value
    elif ns == "safe":
        draft["safe_room_pref"] = value
    elif ns == "furn":
        draft["furniture_pref"] = value


def _apply_toggle(draft: dict, ns: str, value: str) -> None:
    if ns == "pt":
        lst = draft["property_types"]
        if value in lst:
            lst.remove(value)
        else:
            lst.append(value)
    elif ns in ("req", "adv"):
        draft[value] = not draft[value]


def _parse_optional_int(raw: str) -> tuple[bool, int | None]:
    if raw in ("-", ""):
        return True, None
    try:
        return True, int(raw)
    except ValueError:
        return False, None


def _parse_optional_float(raw: str) -> tuple[bool, float | None]:
    if raw in ("-", ""):
        return True, None
    try:
        return True, float(raw)
    except ValueError:
        return False, None


def _parse_optional_date(raw: str) -> tuple[bool, dt.date | None]:
    if raw in ("-", ""):
        return True, None
    try:
        return True, dt.date.fromisoformat(raw)
    except ValueError:
        return False, None


async def filter_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    with get_session() as session:
        user = get_or_create_user(session, update.effective_user)
        existing = session.scalar(select(Filter).where(Filter.user_id == user.id))
        draft = _draft_from_filter(existing)
    context.user_data["draft"] = draft
    context.user_data.pop("awaiting", None)
    await update.message.reply_text(
        kb.render_root_summary(draft), reply_markup=kb.root_keyboard(), parse_mode=ParseMode.HTML
    )
    return MENU


FRIENDLY_VALIDATION_MESSAGES = {
    "price_max": "💰 מחיר מקסימלי חייב להיות גדול או שווה למחיר מינימלי.",
    "rooms_max": "🛏️ מספר חדרים מקסימלי חייב להיות גדול או שווה למינימלי.",
    "floor_max": "🏢 קומה מקסימלית חייבת להיות גדולה או שווה למינימלית.",
    "move_in_latest": "📅 תאריך הכניסה המאוחר ביותר חייב להיות אחרי המוקדם ביותר.",
}


def _describe_validation_error(exc: ValidationError) -> str:
    messages = []
    for error in exc.errors():
        field = error["loc"][0] if error["loc"] else None
        messages.append(FRIENDLY_VALIDATION_MESSAGES.get(field, f"שדה לא תקין: {field}"))
    return "\n".join(dict.fromkeys(messages))  # dedupe, keep order


async def _handle_save(update: Update, context: ContextTypes.DEFAULT_TYPE, draft: dict) -> int:
    query = update.callback_query
    try:
        validated = FilterData(**draft)
    except ValidationError as exc:
        # keep the draft — the user just needs to fix the offending field(s) via the root menu,
        # not lose everything and start /filter over from scratch. (menu_callback already
        # called query.answer() once for this callback — Telegram only allows one answer per
        # callback query, so the warning goes in the edited message, not a second answer() call.)
        warning = _describe_validation_error(exc)
        text = f"⚠️ <b>לפני השמירה, תקן/י:</b>\n{warning}\n\n" + kb.render_root_summary(draft)
        await query.edit_message_text(text, reply_markup=kb.root_keyboard(), parse_mode=ParseMode.HTML)
        return MENU

    with get_session() as session:
        user = get_or_create_user(session, update.effective_user)
        existing = session.scalar(select(Filter).where(Filter.user_id == user.id))
        values = validated.model_dump()
        if existing is None:
            existing = Filter(user_id=user.id, **values)
            session.add(existing)
        else:
            for field, value in values.items():
                setattr(existing, field, value)
        session.commit()

        # mirrors the reference bot's "👀 הראי לי דוגמה" prompt — shown automatically here
        # rather than behind an extra button tap, since we're already inside the save flow
        example = find_matching_listings(session, user.id, existing, limit=1)

    context.user_data.pop("draft", None)
    await query.edit_message_text("✅ הסינון נשמר! תתחיל/י לקבל התראות על דירות מתאימות.")
    if example:
        await query.message.reply_text(
            "👀 הנה דוגמה לדירה שתואמת את הסינון שלך:",
        )
        await query.message.reply_text(
            format_caption(example[0]),
            reply_markup=listing_keyboard(example[0].id),
            parse_mode=ParseMode.HTML,
        )
    return ConversationHandler.END


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    draft = context.user_data.setdefault("draft", _default_draft())
    parts = query.data.split(":")
    action = parts[1]

    if action == "root":
        return await _show_category(query, draft, "root")
    if action == "save":
        return await _handle_save(update, context, draft)
    if action == "cancel":
        context.user_data.pop("draft", None)
        await query.edit_message_text("הסינון בוטל, לא נשמרו שינויים.")
        return ConversationHandler.END
    if action == "cat":
        return await _show_category(query, draft, parts[2])
    if action == "set":
        _apply_single_select(draft, parts[2], parts[3])
        return await _show_category(query, draft, "root")
    if action == "tog":
        _apply_toggle(draft, parts[2], parts[3])
        return await _show_category(query, draft, parts[2])
    if action == "loc":
        sub = parts[2]
        if sub == "addcity":
            context.user_data["awaiting"] = "city"
            await query.edit_message_text("הקלד/י שם עיר לחיפוש:")
            return AWAIT_TEXT
        if sub == "rmc":
            idx = int(parts[3])
            if 0 <= idx < len(draft["cities"]):
                draft["cities"].pop(idx)
        return await _show_category(query, draft, "loc")
    if action == "price":
        sub = parts[2]
        if sub == "min":
            context.user_data["awaiting"] = "price_min"
            await query.edit_message_text("הקלד/י מחיר מינימלי (או '-' לביטול הגבלה):")
            return AWAIT_TEXT
        if sub == "max":
            context.user_data["awaiting"] = "price_max"
            await query.edit_message_text("הקלד/י מחיר מקסימלי (או '-' לביטול הגבלה):")
            return AWAIT_TEXT
        if sub == "reqtoggle":
            draft["require_price"] = not draft["require_price"]
        return await _show_category(query, draft, "price")
    if action == "rooms":
        sub = parts[2]
        if sub == "min":
            context.user_data["awaiting"] = "rooms_min"
            await query.edit_message_text("הקלד/י מספר חדרים מינימלי (למשל 2.5), או '-' לביטול:")
            return AWAIT_TEXT
        if sub == "max":
            context.user_data["awaiting"] = "rooms_max"
            await query.edit_message_text("הקלד/י מספר חדרים מקסימלי, או '-' לביטול:")
            return AWAIT_TEXT
        return await _show_category(query, draft, "rooms")
    if action == "floor":
        sub = parts[2]
        if sub == "min":
            context.user_data["awaiting"] = "floor_min"
            await query.edit_message_text("הקלד/י קומה מינימלית, או '-' לביטול:")
            return AWAIT_TEXT
        if sub == "max":
            context.user_data["awaiting"] = "floor_max"
            await query.edit_message_text("הקלד/י קומה מקסימלית, או '-' לביטול:")
            return AWAIT_TEXT
        if sub == "ground":
            draft["ground_floor_only"] = not draft["ground_floor_only"]
        return await _show_category(query, draft, "floor")
    if action == "area":
        if parts[2] == "set":
            context.user_data["awaiting"] = "min_area_sqm"
            await query.edit_message_text('הקלד/י שטח מינימלי במ"ר, או \'-\' לביטול:')
            return AWAIT_TEXT
        return await _show_category(query, draft, "area")
    if action == "kw":
        sub = parts[2]
        if sub == "set":
            context.user_data["awaiting"] = "keywords"
            await query.edit_message_text("הקלד/י מילות מפתח מופרדות בפסיקים:")
            return AWAIT_TEXT
        if sub == "clear":
            draft["keywords"] = []
        return await _show_category(query, draft, "kw")
    if action == "move":
        sub = parts[2]
        if sub == "earliest":
            context.user_data["awaiting"] = "move_in_earliest"
            await query.edit_message_text("הקלד/י תאריך מוקדם ביותר (YYYY-MM-DD), או '-' לביטול:")
            return AWAIT_TEXT
        if sub == "latest":
            context.user_data["awaiting"] = "move_in_latest"
            await query.edit_message_text("הקלד/י תאריך מאוחר ביותר (YYYY-MM-DD), או '-' לביטול:")
            return AWAIT_TEXT
        if sub == "clear":
            draft["move_in_earliest"] = None
            draft["move_in_latest"] = None
        return await _show_category(query, draft, "move")

    logger.warning("Unhandled filter callback: %s", query.data)
    return MENU


async def text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = context.user_data.setdefault("draft", _default_draft())
    awaiting = context.user_data.pop("awaiting", None)
    raw = (update.message.text or "").strip()

    if awaiting is None:
        await update.message.reply_text("שלח/י /filter כדי להתחיל לערוך את הסינון.")
        return ConversationHandler.END

    if awaiting == "city":
        matches = cities.find_matches(raw)
        if not matches:
            await update.message.reply_text("לא נמצאה עיר תואמת, נסה/י שוב:")
            context.user_data["awaiting"] = "city"
            return AWAIT_TEXT
        chosen = matches[0]
        if chosen not in draft["cities"]:
            draft["cities"].append(chosen)
        await update.message.reply_text(f"✅ נוספה עיר: {chosen}")
        await _send_category(update.message, draft, "loc")
        return MENU

    if awaiting == "keywords":
        draft["keywords"] = [w.strip() for w in raw.split(",") if w.strip()]
        await _send_category(update.message, draft, "kw")
        return MENU

    if awaiting in NUMERIC_INT_FIELDS:
        ok, value = _parse_optional_int(raw)
        if not ok:
            await update.message.reply_text("לא הצלחתי לפרש מספר, נסה/י שוב (או '-'):")
            context.user_data["awaiting"] = awaiting
            return AWAIT_TEXT
        draft[awaiting] = value
        await _send_category(update.message, draft, FIELD_TO_CATEGORY[awaiting])
        return MENU

    if awaiting in NUMERIC_FLOAT_FIELDS:
        ok, value = _parse_optional_float(raw)
        if not ok:
            await update.message.reply_text("לא הצלחתי לפרש מספר, נסה/י שוב (או '-'):")
            context.user_data["awaiting"] = awaiting
            return AWAIT_TEXT
        draft[awaiting] = value
        await _send_category(update.message, draft, FIELD_TO_CATEGORY[awaiting])
        return MENU

    if awaiting in DATE_FIELDS:
        ok, value = _parse_optional_date(raw)
        if not ok:
            await update.message.reply_text("פורמט תאריך לא תקין, נסה/י YYYY-MM-DD (או '-'):")
            context.user_data["awaiting"] = awaiting
            return AWAIT_TEXT
        draft[awaiting] = value
        await _send_category(update.message, draft, FIELD_TO_CATEGORY[awaiting])
        return MENU

    logger.warning("Unhandled 'awaiting' key: %s", awaiting)
    return MENU


async def _cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("draft", None)
    await update.message.reply_text("הסינון בוטל.")
    return ConversationHandler.END


def build_filter_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("filter", filter_start),
            CommandHandler("setfilter", filter_start),
        ],
        states={
            MENU: [CallbackQueryHandler(menu_callback, pattern=r"^f:")],
            AWAIT_TEXT: [MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, text_input)],
        },
        fallbacks=[CommandHandler("cancel", _cancel_command)],
        name="filter_conversation",
    )
