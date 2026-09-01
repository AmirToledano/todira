"""Free-text onboarding for brand-new users — mirrors the reference bot's WhatsApp flow: the user
describes what they're looking for in their own words (one messy paragraph, or a few back-and-
forth turns), and Gemini (gemini_client.py) extracts structured filter fields each turn, merging
with whatever was already collected, until the required minimum (deal_type + at least one city)
is known. This replaced an earlier rigid step-by-step Q&A (deal type -> city -> rooms) that used
plain regex/keyword parsing — real user testing showed typos ("שגירות"), abbreviations
("ראשל\"צ"), and misspellings ("רמת גם") broke it too often, and patching each field's parser
individually was turning into whack-a-mole. This needs GEMINI_API_KEY set; if it's missing or the
API call fails, the user sees a "technical hiccup" message and can retry or fall back to /filter.

This does NOT replace the menu-driven `/filter` conversation (handlers/filter_conversation.py)
— it's a friendlier on-ramp that saves a first, simple Filter row; /filter remains available
afterwards for full control over every field.

`/start` is owned entirely by this ConversationHandler (see build_onboarding_handler): its entry
point calls handlers.start.start() to send the normal welcome and upsert/reactivate the user,
then only continues into the free-text state if the user doesn't have a filter yet — a returning
user just gets the plain welcome and the conversation ends immediately.
"""
from __future__ import annotations

import asyncio

from config import WEBSITE_URL
from dorin_common import cities, gemini_client
from dorin_common.cards import format_caption, listing_keyboard
from dorin_common.db import get_session
from dorin_common.models import Filter
from dorin_common.users import get_or_create_user
from handlers.apartments import RESULT_LIMIT, find_matching_listings
from handlers.start import start
from handlers.support import escalate_to_owner, looks_like_help_request
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

AWAIT_FREETEXT = 0

_EMPTY_STATE = {
    "deal_type": None,
    "cities": [],
    "rooms_min": None,
    "rooms_max": None,
    "price_min": None,
    "price_max": None,
    "keywords": [],
}


def _has_filter_sync(tg_user) -> bool:
    with get_session() as session:
        user = get_or_create_user(session, tg_user)
        return session.scalar(select(Filter.id).where(Filter.user_id == user.id)) is not None


async def onboarding_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await start(update, context)  # normal welcome + create/reactivate the user row

    # asyncio.to_thread — see start.py's _upsert_user_sync comment for why: a synchronous DB call
    # made directly on the event loop blocks every other user's interaction with the bot too.
    has_filter = await asyncio.to_thread(_has_filter_sync, update.effective_user)

    if has_filter:
        return ConversationHandler.END

    context.user_data["onboarding"] = dict(_EMPTY_STATE)
    await update.message.reply_text(
        "ספר/י לי בכמה מילים מה את/ה מחפש/ת — למשל עיר, שכירות/מכירה/סבלט, תקציב, כמה חדרים, "
        "וכל דבר נוסף שחשוב לך. אפשר לכתוב חופשי, אני אבין 🙂\n"
        "(או שאפשר לדלג ולהגדיר הכל ידנית עם /filter בכל שלב)"
    )
    return AWAIT_FREETEXT


def _save_filter_sync(tg_user, state: dict) -> list:
    with get_session() as session:
        user = get_or_create_user(session, tg_user)
        filter_row = Filter(
            user_id=user.id,
            deal_type=state["deal_type"],
            cities=state["cities"],
            rooms_min=state["rooms_min"],
            rooms_max=state["rooms_max"],
            price_min=int(state["price_min"]) if state["price_min"] is not None else None,
            price_max=int(state["price_max"]) if state["price_max"] is not None else None,
            keywords=state["keywords"],
        )
        session.add(filter_row)
        session.commit()
        # Also surfaces what already matches RIGHT NOW (not just future notifications) — a
        # brand-new user especially shouldn't have to wait for the next scrape to see anything.
        return find_matching_listings(session, user.id, filter_row, limit=RESULT_LIMIT)


async def _handle_freetext(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text or ""

    # A user mid-onboarding who asks for a human/support instead of answering "which city, rent
    # or buy?" would otherwise get that same question re-asked forever, since everything typed
    # here normally goes straight to Gemini as apartment-search criteria — see handlers/support.py's
    # docstring for the real report this fixes (2026-09-01). Doesn't end the conversation: she can
    # still keep describing what she's looking for right after this.
    if looks_like_help_request(text):
        await escalate_to_owner(update, context, text)
        await update.message.reply_text(
            "🙋 קיבלתי, העברתי את הפנייה שלך לצוות ותקבל/י מענה בהקדם.\n\n"
            "בינתיים, אם תרצה/י להמשיך לחפש דירה — ספר/י לי מה מחפשים (עיר, שכירות/מכירה/סבלט וכו')."
        )
        return AWAIT_FREETEXT

    # Gemini can take a few seconds (or, on a slow node, much longer) — an impatient real user
    # would otherwise stare at silence and assume the bot is broken/ignoring them.
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text("🔍 רגע, טודירה בודק את מה שכתבת...")

    state = context.user_data.setdefault("onboarding", dict(_EMPTY_STATE))
    result = gemini_client.parse_onboarding_message(text, state, cities.CITIES)

    if result is None:
        await update.message.reply_text(
            "מצטער, יש לי תקלה טכנית רגעית 😅 נסה/י לשלוח שוב בעוד רגע, או תמיד אפשר להגדיר ידנית "
            "עם /filter."
        )
        return AWAIT_FREETEXT

    for key in _EMPTY_STATE:
        if key in result:
            state[key] = result[key]

    # The keyword pre-check above only catches obvious explicit phrasings ("support"/"נציג") — this
    # catches everything else, since Gemini already reads the full message semantically as part of
    # the same call above (zero extra cost/latency, unlike adding a dedicated classification call).
    # Skips the normal response_message (which would just re-ask for whatever's still missing —
    # wrong reply to someone who wasn't answering that question).
    if result.get("needs_human_help"):
        await escalate_to_owner(update, context, text)
        await update.message.reply_text(
            "🙋 קיבלתי, זה נשמע כמו משהו שכדאי שבן אדם אמיתי יענה עליו — העברתי את ההודעה שלך "
            "לצוות ותקבל/י מענה בהקדם.\n\n"
            "אם תרצה/י להמשיך לחפש דירה בינתיים, אפשר לכתוב לי עוד פרטים 🙂"
        )
        return AWAIT_FREETEXT

    await update.message.reply_text(result.get("response_message") or "רשמתי, תודה!")

    if result.get("missing_required") or not state["deal_type"] or not state["cities"]:
        return AWAIT_FREETEXT

    matches = await asyncio.to_thread(_save_filter_sync, update.effective_user, state)

    context.user_data.pop("onboarding", None)
    await update.message.reply_text(
        "אפשר תמיד להרחיב את הסינון (מחיר, קומה, דרישות ועוד) עם /filter 🎛️"
    )

    # Sends every current match as a real card, not just a count/link (mirrors the reference
    # bot's behavior on both its guided-form and free-text paths, per the owner's screenshots
    # 2026-08-31) — a brand-new user especially shouldn't have to click through anywhere to see
    # what already matches right now.
    if matches:
        await update.message.reply_text(
            f"👀 יש כרגע {len(matches)}{'+' if len(matches) >= RESULT_LIMIT else ''} דירות שמתאימות:"
        )
        for listing in matches:
            await update.message.reply_text(
                format_caption(listing),
                reply_markup=listing_keyboard(listing.id),
                parse_mode=ParseMode.HTML,
            )
    else:
        apartments_url = f"{WEBSITE_URL}/apartments?uid={update.effective_user.id}"
        await update.message.reply_text(
            f"עדיין אין דירות תואמות כרגע — אני אמשיך לחפש ואודיע לך. אפשר גם לעקוב באתר: {apartments_url}"
        )

    return ConversationHandler.END


def build_onboarding_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", onboarding_entry)],
        states={
            AWAIT_FREETEXT: [MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, _handle_freetext)],
        },
        fallbacks=[CommandHandler("start", onboarding_entry)],
        name="onboarding_conversation",
        persistent=True,
        # /start is already both an entry point and a fallback here, so it was never actually
        # stuck-proof-dependent the way filter_conversation.py was (see the allow_reentry comment
        # there for the real bug this class of gap causes) - set for consistency/defense-in-depth
        # anyway, since it's a free, standard safeguard for any command-entry conversation.
        allow_reentry=True,
    )
