"""Menu-driven /filter conversation — see plan Section 5 for why a menu-driven design was chosen
over a strict linear ConversationHandler for ~20 fields.

The in-progress filter lives in `context.user_data["draft"]` (a plain dict) and is only written
to the database when the user taps "Save" — it never leaves partial garbage in the `filters`
table. `user_data` is persisted (PicklePersistence, see bot/main.py), so a mid-edit draft survives
a bot restart AND a user re-sending /filter later — `filter_start` resumes an existing draft
rather than reloading from the DB and discarding it, specifically so leaving the chat with the
menu still open and coming back later (or after a redeploy) continues from the same point instead
of silently losing whatever wasn't saved yet.

Scope note: neighborhoods_include/exclude and streets_include/exclude exist in the DB schema
(todira_common.models.Filter) but don't have a menu screen here yet — they weren't included in
this first pass to keep the conversation shippable; add a "neighborhoods"/"streets" category
following the exact same add/remove pattern as `loc` (cities) whenever that's wanted next.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import math

import keyboards as kb
from config import WEBSITE_URL
from todira_common import cities
from todira_common.bot_strings import bot_text
from todira_common.db import get_session
from todira_common.language import DEFAULT_LANG
from todira_common.models import Filter
from todira_common.schemas import FilterData
from todira_common.users import get_or_create_user
from handlers.apartments import find_new_matches_to_show
from handlers.support import escalate_to_owner, looks_like_a_sentence, looks_like_help_request
from pydantic import ValidationError
from sqlalchemy import select
from telegram import ForceReply, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
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

# 2026-09-15: every prompt a text-input field can show, now sent via _prompt_for_text (a freshly
# SENT message with a ForceReply) instead of edited into the existing inline-keyboard message —
# see _prompt_for_text's own docstring for why. Centralized here (was previously just an inline
# string literal at each menu_callback call site) so both menu_callback and the numeric picker's
# "✏️ ערך אחר..." fallback share the exact same wording per field.
#
# 2026-09-26: values are now bot_strings keys, not literal text — see _text_prompt below, which
# resolves the actual per-language string via bot_text(). Keeps this dict's own field->prompt
# mapping (the thing every call site actually needs) separate from the translations themselves.
_TEXT_PROMPT_KEYS = {
    "city": "filter.prompt_city",
    "price_min": "filter.prompt_price_min",
    "price_max": "filter.prompt_price_max",
    "rooms_min": "filter.prompt_rooms_min",
    "rooms_max": "filter.prompt_rooms_max",
    "floor_min": "filter.prompt_floor_min",
    "floor_max": "filter.prompt_floor_max",
    "min_area_sqm": "filter.prompt_min_area_sqm",
    "keywords": "filter.prompt_keywords",
    "move_in_earliest": "filter.prompt_move_in_earliest",
    "move_in_latest": "filter.prompt_move_in_latest",
}


def _text_prompt(field: str, lang: str) -> str:
    return bot_text(_TEXT_PROMPT_KEYS[field], lang)


def _lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    """This conversation's user_data already stashes per-session state (draft/awaiting) rather
    than threading it through every function signature — lang follows the same pattern, set once
    in filter_start (from the DB) and read everywhere else via this helper, instead of adding a
    lang parameter to every one of this module's many handler functions."""
    return context.user_data.get("lang", DEFAULT_LANG)

_NUMERIC_PICKER_LABEL_KEYS = {
    "price_min": "filter.numeric_picker_price_min",
    "price_max": "filter.numeric_picker_price_max",
    "rooms_min": "filter.numeric_picker_rooms_min",
    "rooms_max": "filter.numeric_picker_rooms_max",
    "floor_min": "filter.numeric_picker_floor_min",
    "floor_max": "filter.numeric_picker_floor_max",
}


def _default_draft() -> dict:
    return FilterData().model_dump()


def _draft_from_filter(filter_row: Filter | None) -> dict:
    if filter_row is None:
        return _default_draft()
    return {field: getattr(filter_row, field) for field in FILTER_FIELDS}


def _category_view(draft: dict, category: str, lang: str):
    """Pure function: (title, keyboard) for a given category — reused by both the
    CallbackQueryHandler (edits the existing message) and the text-input handler (sends a new
    message, since the original inline-keyboard message was already replaced by a text prompt)."""
    titles = kb.category_titles(lang)
    if category == "dt":
        return titles["dt"], kb.single_select_keyboard(
            kb.deal_type_labels(lang), draft["deal_type"], "dt", lang
        )
    if category == "pt":
        return titles["pt"], kb.multi_select_keyboard(
            kb.property_type_labels(lang), draft["property_types"], "pt", lang
        )
    if category == "loc":
        # 2026-09-15: made explicit right here, not just in the root summary's own "or 'all'"
        # fallback — see keyboards.location_keyboard's own comment for the real report this is
        # part of. A user staring at an empty list otherwise has no way to tell "no cities chosen
        # yet" apart from "deliberately unconstrained," which is exactly the ambiguity that led to
        # manually selecting all 42 bundled cities instead (a strictly narrower, worse state).
        note = bot_text("filter.all_cities_note", lang) if not draft["cities"] else ""
        return titles["loc"] + note, kb.location_keyboard(draft, lang)
    if category == "locpick":
        return titles["locpick"], kb.city_picker_keyboard(draft, lang)
    if category == "price":
        return titles["price"], kb.price_keyboard(draft, lang)
    if category == "rooms":
        return titles["rooms"], kb.rooms_keyboard(draft, lang)
    if category == "floor":
        return titles["floor"], kb.floor_keyboard(draft, lang)
    if category == "req":
        return titles["req"], kb.requirements_keyboard(draft, lang)
    if category == "safe":
        return titles["safe"], kb.single_select_keyboard(
            kb.safe_room_labels(lang), draft["safe_room_pref"], "safe", lang
        )
    if category == "furn":
        return titles["furn"], kb.single_select_keyboard(
            kb.furniture_labels(lang), draft["furniture_pref"], "furn", lang
        )
    if category == "area":
        return titles["area"], kb.area_keyboard(draft, lang)
    if category == "kw":
        return titles["kw"], kb.keywords_keyboard(draft, lang)
    if category == "move":
        return titles["move"], kb.move_in_keyboard(draft, lang)
    if category == "adv":
        return titles["adv"], kb.advanced_keyboard(draft, lang)
    return kb.render_root_summary(draft, lang), kb.root_keyboard(lang)


async def _show_category(query, draft: dict, category: str, lang: str) -> int:
    title, markup = _category_view(draft, category, lang)
    try:
        await query.edit_message_text(title, reply_markup=markup, parse_mode=ParseMode.HTML)
    except BadRequest as exc:
        # 2026-09-25 real bug fix: a completely harmless double-tap (tapping "נקה" on an already-
        # empty keywords/dates list, or double-tapping any category-open button before the first
        # tap's own re-render lands) re-renders byte-for-byte identical title/markup — Telegram's
        # own API rejects that specific edit with "Bad Request: message is not modified", which
        # bubbled up uncaught to bot/main.py's catch-all _error_handler, showing the user a scary
        # "😅 קרתה תקלה טכנית" for a no-op that isn't an error at all. Any OTHER BadRequest (a real
        # one) still propagates normally — this only swallows the exact "nothing to change" case.
        if "message is not modified" not in str(exc).lower():
            raise
    return MENU


async def _send_category(message, draft: dict, category: str, lang: str) -> None:
    title, markup = _category_view(draft, category, lang)
    await message.reply_text(title, reply_markup=markup, parse_mode=ParseMode.HTML)


async def _prompt_for_text(query, context, *, awaiting: str, prompt: str) -> int:
    """Sends the text prompt as a freshly SENT message with a ForceReply keyboard, instead of
    editing it into the existing inline-keyboard message like every call site here used to.
    editMessageText's own reply_markup only accepts an InlineKeyboardMarkup — never a ForceReply —
    so that older approach could never make the device keyboard open on its own; a real owner
    complaint 2026-09-15 ("המקלדת לא נפתחת אוטומטית"). ForceReply is the one reply_markup type
    that does auto-open it, but Telegram only allows attaching it to a newly sent message.
    Strips the old message's own inline keyboard first (edit_message_reply_markup, text
    untouched) so its buttons can't be tapped while AWAIT_TEXT is active — that state has no
    CallbackQueryHandler at all (see build_filter_conversation_handler), so a stray tap on a
    left-behind button would otherwise silently go nowhere.
    """
    context.user_data["awaiting"] = awaiting
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=prompt,
        reply_markup=ForceReply(selective=True, input_field_placeholder=prompt[:64]),
    )
    return AWAIT_TEXT


async def _show_numeric_picker(query, draft: dict, field: str, lang: str) -> int:
    category_title = kb.category_titles(lang)[FIELD_TO_CATEGORY[field]]
    field_label = bot_text(_NUMERIC_PICKER_LABEL_KEYS[field], lang)
    title = f"{category_title} — {field_label}"
    markup = kb.numeric_preset_keyboard(field, draft[field], FIELD_TO_CATEGORY[field], lang)
    await query.edit_message_text(title, reply_markup=markup, parse_mode=ParseMode.HTML)
    return MENU


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


def _toggle_city(draft: dict, idx: int) -> None:
    """`idx` indexes todira_common.cities.CITIES (the full bundled list), not draft["cities"]
    (the user's own selection) — see kb.city_picker_keyboard / kb.city_search_results_keyboard,
    both of which build their callback_data from CITIES positions for a short, stable
    callback_data payload rather than encoding the (longer, Hebrew) city string directly."""
    city = cities.CITIES[idx]
    if city in draft["cities"]:
        draft["cities"].remove(city)
    else:
        draft["cities"].append(city)


# 2026-09-25 real bug fix, found via a live code-review pass: price_min/price_max/floor_min/
# floor_max/min_area_sqm are all plain Postgres Integer columns (4-byte, roughly ±2.1 billion) —
# int(raw) alone gladly parses a much bigger number (Python ints are unbounded), which then failed
# at the DB layer as an unhandled numeric-overflow error the moment the filter was actually saved,
# not at input time where the user could see a normal "not a valid number" reply instead.
_POSTGRES_INTEGER_MAX = 2_147_483_647


def _parse_optional_int(raw: str) -> tuple[bool, int | None]:
    if raw in ("-", ""):
        return True, None
    try:
        value = int(raw)
    except ValueError:
        return False, None
    if not (-_POSTGRES_INTEGER_MAX - 1 <= value <= _POSTGRES_INTEGER_MAX):
        return False, None
    return True, value


def _parse_optional_float(raw: str) -> tuple[bool, float | None]:
    if raw in ("-", ""):
        return True, None
    try:
        value = float(raw)
    except ValueError:
        return False, None
    # rooms_min/rooms_max are NUMERIC(3,1) columns — at most 3 total digits, 1 after the decimal
    # point (max magnitude 99.9); a bigger value failed the same way as the int case above. Also
    # rejects NaN/±Infinity: float() parses both without raising (unlike int()), but a NaN rooms
    # value would silently fail every comparison in matching.py's own room-range check (IEEE 754:
    # any comparison against NaN is always False) — the filter would look saved and normal, yet
    # silently match nothing, ever, with no visible error anywhere.
    if not math.isfinite(value) or not (-99.9 <= value <= 99.9):
        return False, None
    return True, value


def _parse_optional_date(raw: str) -> tuple[bool, dt.date | None]:
    if raw in ("-", ""):
        return True, None
    try:
        return True, dt.date.fromisoformat(raw)
    except ValueError:
        return False, None


def _load_draft_and_lang_from_db_sync(tg_user) -> tuple[dict, str]:
    with get_session() as session:
        user = get_or_create_user(session, tg_user)
        existing = session.scalar(select(Filter).where(Filter.user_id == user.id))
        return _draft_from_filter(existing), (user.language or DEFAULT_LANG)


async def filter_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("/filter invoked by telegram_user_id=%s", update.effective_user.id)
    # Resume an in-progress draft if one exists (e.g. the user left the chat mid-edit with the
    # menu still open and is now sending /filter again, whether because they forgot to scroll
    # back to the old message or because allow_reentry is what got them unstuck) rather than
    # reloading from the DB and silently discarding whatever they hadn't saved yet. Only load
    # fresh from the DB (draft AND lang together) when there's truly no draft in progress (first
    # /filter ever, or after Save/Cancel/allow_reentry's own reset already cleared it) — a resumed
    # draft already has "lang" stashed in user_data from the /filter call that started it, so no
    # DB round-trip is needed just to keep editing.
    draft = context.user_data.get("draft")
    if draft is None:
        # asyncio.to_thread — see handlers/start.py's _upsert_user_sync comment: a synchronous DB
        # call directly on the event loop would freeze every other user's bot interaction too,
        # not just this one, since PTB processes updates one at a time by default.
        draft, lang = await asyncio.to_thread(
            _load_draft_and_lang_from_db_sync, update.effective_user
        )
        context.user_data["draft"] = draft
        context.user_data["lang"] = lang
    lang = _lang(context)
    context.user_data.pop("awaiting", None)
    await update.message.reply_text(
        kb.render_root_summary(draft, lang),
        reply_markup=kb.root_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )
    return MENU


FRIENDLY_VALIDATION_KEYS = {
    "price_max": "filter.validation_price_max",
    "rooms_max": "filter.validation_rooms_max",
    "floor_max": "filter.validation_floor_max",
    "move_in_latest": "filter.validation_move_in_latest",
}


def _describe_validation_error(exc: ValidationError, lang: str) -> str:
    messages = []
    for error in exc.errors():
        field = error["loc"][0] if error["loc"] else None
        key = FRIENDLY_VALIDATION_KEYS.get(field)
        messages.append(
            bot_text(key, lang) if key else bot_text("filter.validation_generic_field", lang, field=field)
        )
    return "\n".join(dict.fromkeys(messages))  # dedupe, keep order


def _save_and_match_sync(tg_user, values: dict) -> int:
    with get_session() as session:
        user = get_or_create_user(session, tg_user)
        existing = session.scalar(select(Filter).where(Filter.user_id == user.id))
        if existing is None:
            existing = Filter(user_id=user.id, **values)
            session.add(existing)
        else:
            for field, value in values.items():
                setattr(existing, field, value)
        session.commit()

        # 2026-09-15: no longer sends the matching listings themselves as Telegram cards (see
        # _handle_save's own comment) — only need the count now. Still goes through
        # find_new_matches_to_show, not find_matching_listings directly, purely for its bookkeeping
        # side effect: every currently-matching listing gets a SentNotification(reason=NEW) row, so
        # a FUTURE price change on one of them still reaches this user via the normal scraper/
        # notifier.py flow (which only re-notifies users who already have a NEW-reason row for that
        # listing) — without that, a listing only ever seen via the website link would never
        # qualify for a later price-drop alert. limit=None (the default) so this count/bookkeeping
        # covers EVERY current match, not an artificial subset — a real owner complaint 2026-09-15:
        # an almost-unconstrained filter reported "10 matches" when the true number (checked
        # directly against the DB) was 3,642. A second owner request the same day, after seeing that
        # real number: no cap at all, not even a bigger one — someone whose filter matches thousands
        # should see all of them via the link.
        total, _new_to_show = find_new_matches_to_show(session, user.id, existing)
        session.commit()
        return total


async def _handle_save(update: Update, context: ContextTypes.DEFAULT_TYPE, draft: dict) -> int:
    query = update.callback_query
    lang = _lang(context)
    try:
        validated = FilterData(**draft)
    except ValidationError as exc:
        # keep the draft — the user just needs to fix the offending field(s) via the root menu,
        # not lose everything and start /filter over from scratch. (menu_callback already
        # called query.answer() once for this callback — Telegram only allows one answer per
        # callback query, so the warning goes in the edited message, not a second answer() call.)
        warning = _describe_validation_error(exc, lang)
        text = bot_text(
            "filter.fix_before_save",
            lang,
            warning=warning,
            summary=kb.render_root_summary(draft, lang),
        )
        await query.edit_message_text(
            text, reply_markup=kb.root_keyboard(lang), parse_mode=ParseMode.HTML
        )
        return MENU

    # asyncio.to_thread — see handlers/start.py's _upsert_user_sync comment: a synchronous DB
    # call directly on the event loop would freeze every other user's bot interaction too, not
    # just this one, since PTB processes updates one at a time by default.
    total = await asyncio.to_thread(
        _save_and_match_sync, update.effective_user, validated.model_dump()
    )

    context.user_data.pop("draft", None)
    apartments_url = f"{WEBSITE_URL}/apartments?uid={update.effective_user.id}"
    await query.edit_message_text(bot_text("filter.saved_confirmation", lang))
    # 2026-09-15: used to send every NEW-to-this-user current match as its own Telegram card right
    # here — a real owner complaint the same day: a broad filter matching dozens/hundreds of
    # already-existing listings flooded the chat with cards immediately on save, AND (since the
    # count/send was capped at RESULT_LIMIT=10) silently misrepresented how many really matched.
    # Now ALWAYS just points at the website's own /apartments?uid=... view instead — no such cap,
    # properly paginated (website/main.py's own /apartments route) — whether this is a brand-new
    # filter or an update to an existing one. Real-time Telegram pushes are reserved for what
    # they're actually for: a listing that's genuinely NEW (or newly price-changed) from THIS point
    # on, via the normal scraper/notifier.py flow — completely untouched by this change, and it
    # still reaches this same website view next time the user opens it (no separate bookkeeping
    # needed there, /apartments always queries live DB state).
    if total:
        await query.message.reply_text(
            bot_text("onboarding.matches_found", lang, total=total, apartments_url=apartments_url)
        )
    else:
        await query.message.reply_text(
            bot_text("onboarding.no_matches_yet", lang, apartments_url=apartments_url)
        )
    return ConversationHandler.END


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    draft = context.user_data.setdefault("draft", _default_draft())
    lang = _lang(context)
    parts = query.data.split(":")
    action = parts[1]

    if action == "root":
        return await _show_category(query, draft, "root", lang)
    if action == "save":
        return await _handle_save(update, context, draft)
    if action == "cancel":
        context.user_data.pop("draft", None)
        await query.edit_message_text(bot_text("filter.cancelled", lang))
        return ConversationHandler.END
    if action == "cat":
        return await _show_category(query, draft, parts[2], lang)
    if action == "set":
        _apply_single_select(draft, parts[2], parts[3])
        return await _show_category(query, draft, "root", lang)
    if action == "tog":
        _apply_toggle(draft, parts[2], parts[3])
        return await _show_category(query, draft, parts[2], lang)
    if action == "loc":
        sub = parts[2]
        if sub == "addcity":
            return await _prompt_for_text(
                query, context, awaiting="city", prompt=_text_prompt("city", lang)
            )
        if sub == "full":
            return await _show_category(query, draft, "locpick", lang)
        if sub == "togc":
            _toggle_city(draft, int(parts[3]))
            return await _show_category(query, draft, "locpick", lang)
        if sub == "rmc":
            # 2026-09-25 real bug fix: see keyboards.location_keyboard's own comment on the
            # rmc button — this now removes by the city's own name (idempotent against a
            # double-tap/stale-render sending the same value twice), not a list index that goes
            # stale the instant one city is removed and silently deletes the WRONG city on a
            # second tap.
            city_name = parts[3]
            if city_name in draft["cities"]:
                draft["cities"].remove(city_name)
        if sub == "clearall":
            # See keyboards.location_keyboard's own 2026-09-15 comment — restores the TRUE "no
            # city restriction" state (matches every city/town, not just the 42 curated ones).
            draft["cities"] = []
        return await _show_category(query, draft, "loc", lang)
    if action == "price":
        sub = parts[2]
        if sub == "min":
            return await _show_numeric_picker(query, draft, "price_min", lang)
        if sub == "max":
            return await _show_numeric_picker(query, draft, "price_max", lang)
        if sub == "reqtoggle":
            draft["require_price"] = not draft["require_price"]
        return await _show_category(query, draft, "price", lang)
    if action == "rooms":
        sub = parts[2]
        if sub == "min":
            return await _show_numeric_picker(query, draft, "rooms_min", lang)
        if sub == "max":
            return await _show_numeric_picker(query, draft, "rooms_max", lang)
        return await _show_category(query, draft, "rooms", lang)
    if action == "floor":
        sub = parts[2]
        if sub == "min":
            return await _show_numeric_picker(query, draft, "floor_min", lang)
        if sub == "max":
            return await _show_numeric_picker(query, draft, "floor_max", lang)
        if sub == "ground":
            draft["ground_floor_only"] = not draft["ground_floor_only"]
        return await _show_category(query, draft, "floor", lang)
    if action == "pick":
        # Quick-pick preset tap / custom-value fallback / clear, from a numeric_preset_keyboard
        # screen (see kb.numeric_preset_keyboard and _show_numeric_picker above).
        field, sub = parts[2], parts[3]
        if sub == "custom":
            return await _prompt_for_text(
                query, context, awaiting=field, prompt=_text_prompt(field, lang)
            )
        if sub == "clear":
            draft[field] = None
        else:
            draft[field] = kb.NUMERIC_PRESETS[field][int(sub)]
        return await _show_category(query, draft, FIELD_TO_CATEGORY[field], lang)
    if action == "area":
        if parts[2] == "set":
            return await _prompt_for_text(
                query, context, awaiting="min_area_sqm", prompt=_text_prompt("min_area_sqm", lang)
            )
        return await _show_category(query, draft, "area", lang)
    if action == "kw":
        sub = parts[2]
        if sub == "set":
            return await _prompt_for_text(
                query, context, awaiting="keywords", prompt=_text_prompt("keywords", lang)
            )
        if sub == "clear":
            draft["keywords"] = []
        return await _show_category(query, draft, "kw", lang)
    if action == "move":
        sub = parts[2]
        if sub == "earliest":
            return await _prompt_for_text(
                query, context, awaiting="move_in_earliest",
                prompt=_text_prompt("move_in_earliest", lang),
            )
        if sub == "latest":
            return await _prompt_for_text(
                query, context, awaiting="move_in_latest",
                prompt=_text_prompt("move_in_latest", lang),
            )
        if sub == "clear":
            draft["move_in_earliest"] = None
            draft["move_in_latest"] = None
        return await _show_category(query, draft, "move", lang)

    logger.warning("Unhandled filter callback: %s", query.data)
    return MENU


async def _reply_parse_failure_or_escalate(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    raw: str,
    awaiting: str,
    retry_message: str,
    lang: str,
    escalate_on_sentence: bool = True,
) -> int:
    """Shared tail for every field that failed to parse `raw` as the value it asked for. There's
    no Gemini call here to ask semantically (unlike onboarding.py) — a genuine typo at a number/
    date prompt is almost always one token, so more than one word is treated as a real message
    worth forwarding, not a bad value worth just re-prompting for (see handlers/support.py's
    looks_like_a_sentence docstring). `escalate_on_sentence=False` (used for the city prompt) opts
    out of that heuristic: a real Israeli city name is routinely 2-3 words on its own (קריית
    מוצקין, תל אביב יפו, מודיעין מכבים רעות), so "≥2 words" is not a sentence signal there — it's
    the norm, and applying it anyway escalated ordinary city typos ("קרית מוצקין" — a spelling
    variant, not gibberish) to the owner as support requests (found 2026-09-02 via a real user's
    report)."""
    # ForceReply on the retry too (not just the original prompt) — 2026-09-15: without it, the
    # device keyboard that _prompt_for_text opened would close right back up on a bad first
    # attempt, the exact "keyboard doesn't stay open" annoyance this whole feature exists to fix.
    retry_markup = ForceReply(selective=True, input_field_placeholder=retry_message[:64])
    if escalate_on_sentence and looks_like_a_sentence(raw):
        await escalate_to_owner(update, context, raw)
        await update.message.reply_text(
            bot_text("filter.not_a_valid_value_escalated", lang, retry_message=retry_message),
            reply_markup=retry_markup,
        )
    else:
        await update.message.reply_text(retry_message, reply_markup=retry_markup)
    context.user_data["awaiting"] = awaiting
    return AWAIT_TEXT


async def menu_text_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """MENU only ever had a CallbackQueryHandler for the inline buttons — a user who types plain
    text while the menu is open (instead of tapping a button) matched nothing at all in the
    ConversationHandler's states dict, so the message was silently swallowed with zero reply,
    found live auditing this file 2026-09-07. A genuine support request typed at this point still
    escalates exactly like it does everywhere else in this conversation; anything else gets a
    friendly nudge back to the buttons rather than dead silence."""
    lang = _lang(context)
    raw = (update.message.text or "").strip()
    if looks_like_help_request(raw):
        await escalate_to_owner(update, context, raw)
        await update.message.reply_text(bot_text("filter.menu_help_escalated", lang))
    else:
        await update.message.reply_text(bot_text("filter.use_buttons_hint", lang))
    return MENU


async def text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    draft = context.user_data.setdefault("draft", _default_draft())
    awaiting = context.user_data.pop("awaiting", None)
    raw = (update.message.text or "").strip()

    if awaiting is None:
        await update.message.reply_text(bot_text("filter.not_awaiting_anything", lang))
        return ConversationHandler.END

    # A user who asks for a human/support instead of answering the specific value the menu just
    # prompted for (e.g. "הקלד/י מחיר מינימלי") would otherwise get "לא הצלחתי לפרש מספר, נסה/י
    # שוב" — the numeric/date parsers below have no concept of a support request. Restores
    # `awaiting` so she isn't kicked out of what she was doing; see handlers/support.py's
    # docstring for the real report this fixes (2026-09-01).
    if looks_like_help_request(raw):
        await escalate_to_owner(update, context, raw)
        context.user_data["awaiting"] = awaiting
        continue_msg = bot_text("filter.help_request_continue", lang)
        await update.message.reply_text(
            bot_text("filter.help_request_continue_escalated", lang, continue_msg=continue_msg),
            reply_markup=ForceReply(selective=True, input_field_placeholder=continue_msg[:64]),
        )
        return AWAIT_TEXT

    if awaiting == "city":
        matches = cities.find_matches(raw)
        if not matches:
            return await _reply_parse_failure_or_escalate(
                update,
                context,
                raw,
                "city",
                bot_text("filter.city_not_found", lang),
                lang,
                escalate_on_sentence=False,
            )
        # Show every candidate as a tappable button instead of silently adding matches[0] — a
        # search is a hint, not a pick; the user chooses explicitly which city they meant, same
        # as tapping a box in kb.city_picker_keyboard (2026-09-02: this used to auto-add the
        # first match, which is exactly the "ניחוש אוטומטי" a real user asked to remove).
        await update.message.reply_text(
            bot_text("filter.pick_city", lang),
            reply_markup=kb.city_search_results_keyboard(matches, lang),
        )
        return MENU

    if awaiting == "keywords":
        draft["keywords"] = [w.strip() for w in raw.split(",") if w.strip()]
        await _send_category(update.message, draft, "kw", lang)
        return MENU

    if awaiting in NUMERIC_INT_FIELDS:
        ok, value = _parse_optional_int(raw)
        if not ok:
            return await _reply_parse_failure_or_escalate(
                update, context, raw, awaiting, bot_text("filter.number_parse_failed", lang), lang
            )
        draft[awaiting] = value
        await _send_category(update.message, draft, FIELD_TO_CATEGORY[awaiting], lang)
        return MENU

    if awaiting in NUMERIC_FLOAT_FIELDS:
        ok, value = _parse_optional_float(raw)
        if not ok:
            return await _reply_parse_failure_or_escalate(
                update, context, raw, awaiting, bot_text("filter.number_parse_failed", lang), lang
            )
        draft[awaiting] = value
        await _send_category(update.message, draft, FIELD_TO_CATEGORY[awaiting], lang)
        return MENU

    if awaiting in DATE_FIELDS:
        ok, value = _parse_optional_date(raw)
        if not ok:
            return await _reply_parse_failure_or_escalate(
                update, context, raw, awaiting, bot_text("filter.date_parse_failed", lang), lang
            )
        draft[awaiting] = value
        await _send_category(update.message, draft, FIELD_TO_CATEGORY[awaiting], lang)
        return MENU

    logger.warning("Unhandled 'awaiting' key: %s", awaiting)
    return MENU


async def _cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    context.user_data.pop("draft", None)
    await update.message.reply_text(bot_text("filter.cancelled_command", lang))
    return ConversationHandler.END


def build_filter_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("filter", filter_start),
            CommandHandler("setfilter", filter_start),
        ],
        states={
            MENU: [
                CallbackQueryHandler(menu_callback, pattern=r"^f:"),
                MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, menu_text_fallback),
            ],
            AWAIT_TEXT: [MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, text_input)],
        },
        fallbacks=[CommandHandler("cancel", _cancel_command)],
        name="filter_conversation",
        persistent=True,
        # Without this, a user who ever abandons a /filter session mid-way (closes the chat with
        # the inline menu still open, never taps Save/Cancel) gets stuck in that state FOREVER —
        # python-telegram-bot's ConversationHandler.check_update only tries entry_points when
        # `state is None or allow_reentry` (see conversationhandler.py), so with the default
        # allow_reentry=False, every future /filter they send matches nothing at all (MENU's own
        # handler only accepts inline-button callback queries, not a text command; the only
        # fallback is /cancel, which they'd have no reason to know about) — total silence, not
        # even an error, since filter_start() itself is never invoked. This is the actual root
        # cause behind "/filter just doesn't respond" reports investigated 2026-08-31 (see
        # PROJECT_STATE.md) — allow_reentry=True makes a fresh /filter always work by re-entering
        # the conversation (which resets context.user_data["draft"] to a clean state anyway),
        # self-healing anyone already stuck the moment they try /filter again after this deploys.
        allow_reentry=True,
    )
