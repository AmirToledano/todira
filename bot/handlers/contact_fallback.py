"""Catch-all for free-text messages that don't match any active conversation or command.

Registered LAST in bot/main.py's default handler group (group=0) — python-telegram-bot tries
handlers within a group in registration order and stops at the first match, so this only fires
once every other handler (both ConversationHandlers, every CommandHandler) has already declined
the update.

Cases, in order:
1. Only ACTUAL support/help requests (handlers/support.py's looks_like_help_request — the same
   keyword check onboarding.py and filter_conversation.py use mid-conversation) get escalated to
   the owner. Plain small talk ("מה שלומך"), a stray apartment question, anything without a
   help/complaint keyword was WRONGLY being treated as a support ticket too before an earlier fix
   (2026-09-02) — that fix is unchanged here, still checked first.
2. 2026-10-18 (owner: "people write to the bot and it doesn't work, only /filter does"): an
   already-onboarded user's message is first read with the free rules (todira_common/search_text.py,
   the same reader onboarding uses) and, when it names a city, rooms, a budget, a deal type or a
   feature, the filter is updated right away and the new search is shown back. Before this, every
   such message depended on Gemini, and a Gemini error, its daily per-user limit or its pause after a
   failure all ended in "I couldn't read that message".
3. 2026-09-06: anything the rules can't read (small talk, a question) still gets a real chat reply
   from gemini_client.chat_with_existing_user while the AI is available, and otherwise a short reply
   with an example of what can be written.
4. No filter yet: a message the rules can read in full (deal type and a city) creates the search
   straight away, like onboarding would; anything else gets the plain redirect to /start (before
   2026-09-01 such a message silently vanished).
"""
from __future__ import annotations

import asyncio
import logging
import re

import ai_gate
from config import WEBSITE_URL
from todira_common import cities, gemini_client, search_text
from todira_common.bot_strings import bot_text
from todira_common.db import get_session
from todira_common.language import DEFAULT_LANG
from todira_common.listing_matches import find_new_matches_to_show
from todira_common.matching import safe_range_update
from todira_common.models import Filter
from todira_common.uid_token import signed_login_query
from todira_common.users import get_or_create_user
from handlers.onboarding import _EMPTY_STATE, _save_filter_sync
from handlers.testimonial import take_testimonial
from handlers.support import escalate_to_owner, looks_like_help_request
from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler
from telegram.ext import filters as tg_filters


def _load_filter_sync(tg_user) -> tuple[int, dict | None, str]:
    with get_session() as session:
        user = get_or_create_user(session, tg_user)
        lang = user.language or DEFAULT_LANG
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user.id))
        if filter_row is None:
            return user.id, None, lang
        current_filter = {
            "deal_type": filter_row.deal_type,
            "cities": filter_row.cities,
            "rooms_min": float(filter_row.rooms_min) if filter_row.rooms_min is not None else None,
            "rooms_max": float(filter_row.rooms_max) if filter_row.rooms_max is not None else None,
            "price_min": filter_row.price_min,
            "price_max": filter_row.price_max,
            "keywords": filter_row.keywords,
        }
        return user.id, current_filter, lang


def _apply_filter_change_sync(user_id: int, result: dict) -> None:
    with get_session() as session:
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user_id))
        if filter_row is None:
            return
        for key in ("deal_type", "cities", "keywords"):
            if key in result:
                setattr(filter_row, key, result[key])
        # safe_range_update refuses to write an inverted min>max range — Gemini decides both
        # sides here from freeform text, not a structured menu, so there's no re-prompt available
        # to catch a garbled range before it's saved (see that function's own docstring; found
        # live 2026-09-07 — an inverted range hard-fails every listing forever, silently).
        if "rooms_min" in result or "rooms_max" in result:
            filter_row.rooms_min, filter_row.rooms_max = safe_range_update(
                filter_row.rooms_min, filter_row.rooms_max,
                result.get("rooms_min"), result.get("rooms_max"),
            )
        if "price_min" in result or "price_max" in result:
            price_min = result.get("price_min")
            price_max = result.get("price_max")
            filter_row.price_min, filter_row.price_max = safe_range_update(
                filter_row.price_min, filter_row.price_max,
                int(price_min) if price_min is not None else None,
                int(price_max) if price_max is not None else None,
            )
        session.commit()


logger = logging.getLogger(__name__)

# "תוסיף גם רמת גן": the cities named are added to the search; without such a word they replace it.
_ADD_WORDS = re.compile(
    r"(?<![א-ת])(?:גם|וגם|ועוד|תוסיף|תוסיפי|להוסיף|הוסף|הוסיפי)(?![א-ת])|\b(?:add|also)\b", re.IGNORECASE
)
_NATIONWIDE = re.compile(r"(?<![א-ת])ב?כל\s+(?:הארץ|הערים|המדינה|מקום)(?![א-ת])|\b(?:nationwide|anywhere)\b", re.IGNORECASE)
_THANKS = re.compile(r"^\W*(?:תודה(?:\s+רבה)?|תודה\s+לך|thanks?(?:\s+you)?|thank\s+you|סבבה|מעולה|אחלה)\W*$", re.IGNORECASE)
# "יש דירות בחיפה?" asks, it doesn't ask to search Haifa instead. A question with no word asking for a change goes to
# the chat reply, not into the filter.
_QUESTION_START = re.compile(r"^\W*(?:יש|כמה|מה|איך|למה|האם|מתי|איפה|מי|is|are|how|what|why|when|where|do|does)(?![א-ת\w])", re.IGNORECASE)
_CHANGE_WORDS = re.compile(
    r"(?<![א-ת])(?:תשנה|תשני|לשנות|שנה|תעדכן|תעדכני|לעדכן|עדכן|תחליף|תחליפי|להחליף|תוסיף|תוסיפי|להוסיף|הוסף|רוצה|"
    r"מחפש|מחפשת|מחפשים|צריך|צריכה|אפשר)(?![א-ת])|\b(?:change|update|switch|want|looking)\b",
    re.IGNORECASE,
)


def _newest_range(old_min, old_max, new_min, new_max):
    """The sides a message names replace the old ones. An old side that would now be on the wrong side of the new one
    is dropped: "לפחות 4 חדרים" on a 2-3 room search means from 4, with no maximum (an inverted range would match
    nothing, ever)."""
    if new_min is not None and new_max is not None and new_min > new_max:
        new_min, new_max = new_max, new_min
    low = new_min if new_min is not None else old_min
    high = new_max if new_max is not None else old_max
    if low is not None and high is not None and low > high:
        return new_min, new_max
    return low, high


def _changes_search(found: dict, nationwide: bool) -> bool:
    """Only a message that names part of a search changes the filter. A plain keyword alone ("מחסן") does not: it
    would narrow the search to listings that mention it."""
    return bool(
        nationwide
        or found["deal_type"]
        or found["cities"]
        or found["fields"]
        or any(found[key] is not None for key in ("rooms_min", "rooms_max", "price_min", "price_max"))
    )


def _filter_state(filter_row: Filter, labels: list[str]) -> dict:
    return {
        "deal_type": filter_row.deal_type,
        "cities": list(filter_row.cities or []),
        "rooms_min": float(filter_row.rooms_min) if filter_row.rooms_min is not None else None,
        "rooms_max": float(filter_row.rooms_max) if filter_row.rooms_max is not None else None,
        "price_min": filter_row.price_min,
        "price_max": filter_row.price_max,
        "keywords": list(filter_row.keywords or []),
        "labels": labels,
    }


def _apply_search_text_sync(user_id: int, found: dict, add_cities: bool, nationwide: bool) -> tuple[dict, int] | None:
    """Writes what search_text.parse() read into the user's filter. Returns (the search now, how many listings match
    it), or None when the user has no filter."""
    with get_session() as session:
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user_id))
        if filter_row is None:
            return None
        price = found["price_max"] if found["price_max"] is not None else found["price_min"]
        deal_before = filter_row.deal_type
        if found["deal_type"]:
            filter_row.deal_type = found["deal_type"]
        elif price is not None:
            # same rule onboarding uses (search_text.infer_deal_type): a monthly rent is under NIS 50,000 and a
            # purchase NIS 300,000 or more, so "עד 2 מיליון" on a rent search means a purchase
            if price >= 300_000 and filter_row.deal_type != "sale":
                filter_row.deal_type = "sale"
            elif price < 50_000 and filter_row.deal_type == "sale":
                filter_row.deal_type = "rent"
        if nationwide and not found["cities"]:
            filter_row.cities = []
        elif found["cities"]:
            current = list(filter_row.cities or []) if add_cities else []
            filter_row.cities = current + [c for c in found["cities"] if c not in current]
        if found["rooms_min"] is not None or found["rooms_max"] is not None:
            filter_row.rooms_min, filter_row.rooms_max = _newest_range(
                filter_row.rooms_min, filter_row.rooms_max, found["rooms_min"], found["rooms_max"]
            )
        if found["price_min"] is not None or found["price_max"] is not None:
            new_min = int(found["price_min"]) if found["price_min"] is not None else None
            new_max = int(found["price_max"]) if found["price_max"] is not None else None
            if filter_row.deal_type != deal_before:
                # a rent budget means nothing on a purchase search (and the other way round): only the new one counts
                filter_row.price_min, filter_row.price_max = new_min, new_max
            else:
                filter_row.price_min, filter_row.price_max = _newest_range(
                    filter_row.price_min, filter_row.price_max, new_min, new_max
                )
        for field, value in (found["fields"] or {}).items():
            if field == "property_types":
                current = list(filter_row.property_types or []) if add_cities else []
                value = current + [v for v in value if v not in current]
            setattr(filter_row, field, value)
        if found["keywords"]:
            current = list(filter_row.keywords or [])
            filter_row.keywords = current + [k for k in found["keywords"] if k not in current]
        session.commit()
        # Same bookkeeping as saving in /filter: what matches now is recorded as shown, so the next scraper run sends
        # only genuinely new listings, not a backlog for the changed search.
        total, _new = find_new_matches_to_show(session, user_id, filter_row)
        session.commit()
        return _filter_state(filter_row, found["labels"]), total


def _record_matches_sync(user_id: int) -> None:
    """After the AI changed the filter: the same bookkeeping as _apply_search_text_sync."""
    with get_session() as session:
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user_id))
        if filter_row is not None:
            find_new_matches_to_show(session, user_id, filter_row)
            session.commit()


def _matches_text(tg_user_id: int, total: int, lang: str) -> str:
    apartments_url = f"{WEBSITE_URL}/apartments?{signed_login_query(tg_user_id)}"
    if total:
        return bot_text("onboarding.matches_found", lang, total=total, apartments_url=apartments_url)
    return bot_text("onboarding.no_matches_yet", lang, apartments_url=apartments_url)


async def _reply_with_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, user_id: int,
                         current_filter: dict, lang: str) -> None:
    # 2026-10-13: the AI only while it works and this user has AI calls left today (bot/ai_gate.py).
    if not ai_gate.allowed(context.user_data):
        await update.message.reply_text(bot_text("contact_fallback.not_understood", lang))
        return
    ai_gate.used(context.user_data)
    try:
        result = await asyncio.to_thread(
            gemini_client.chat_with_existing_user,
            text,
            current_filter,
            cities.CITIES,
            update.effective_user.first_name,
            lang,
        )
    except Exception:
        logger.exception("chat_with_existing_user raised")
        result = None
    if result is None:
        ai_gate.failed()
        await update.message.reply_text(bot_text("contact_fallback.not_understood", lang))
        return
    if result.get("filter_changed"):
        await asyncio.to_thread(_apply_filter_change_sync, user_id, result)
        try:
            await asyncio.to_thread(_record_matches_sync, user_id)
        except Exception:
            logger.exception("could not record the current matches as shown after an AI filter change")
    await update.message.reply_text(
        result.get("response_message") or bot_text("contact_fallback.default_ack", lang)
    )


async def handle_stray_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""

    # 2026-10-22: the reply to "write us one sentence about how it went" (handlers/testimonial.py).
    if await take_testimonial(update, context):
        return

    # looks_like_help_request stays checked FIRST, before touching this module's own get_session
    # at all — same precedence bot/handlers/support.py's own docstring already establishes,
    # deliberately kept independent of the filter-loading session below (so a broken DB session
    # here can never take the escalation path down with it). This one reply stays Hebrew-only for
    # now — getting its own language would mean a DB read this path is specifically meant to avoid.
    if looks_like_help_request(text):
        await escalate_to_owner(update, context, text)
        await update.message.reply_text(bot_text("contact_fallback.help_escalated", DEFAULT_LANG))
        return

    user_id, current_filter, lang = await asyncio.to_thread(_load_filter_sync, update.effective_user)
    found = search_text.parse(text)
    nationwide = bool(_NATIONWIDE.search(text))

    if current_filter is not None:
        just_asking = bool(_QUESTION_START.search(text)) and not _CHANGE_WORDS.search(text)
        if _changes_search(found, nationwide) and not just_asking:
            applied = await asyncio.to_thread(
                _apply_search_text_sync, user_id, found, bool(_ADD_WORDS.search(text)), nationwide
            )
            if applied is not None:
                state, total = applied
                await update.message.reply_text(
                    bot_text("contact_fallback.updated", lang, summary=search_text.summary(state, lang))
                    + "\n" + _matches_text(update.effective_user.id, total, lang)
                )
                return
        if _THANKS.match(text):
            await update.message.reply_text(bot_text("contact_fallback.thanks", lang))
            return
        await _reply_with_ai(update, context, text, user_id, current_filter, lang)
        return

    # No search yet (onboarding was left half way, or never started): a message that already says enough becomes the
    # search, exactly as onboarding would save it.
    state = {**_EMPTY_STATE, "cities": [], "keywords": [], "fields": {}, "labels": []}
    search_text.merge_into(state, found)
    search_text.infer_deal_type(state)
    if search_text.is_complete(state):
        total = await asyncio.to_thread(_save_filter_sync, update.effective_user, state)
        await update.message.reply_text(
            bot_text("onboarding.understood", lang, summary=search_text.summary(state, lang))
            + "\n" + _matches_text(update.effective_user.id, total, lang)
        )
        return
    await update.message.reply_text(bot_text("contact_fallback.new_user_prompt", lang))


def build_contact_fallback_handler() -> MessageHandler:
    return MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, handle_stray_message)
