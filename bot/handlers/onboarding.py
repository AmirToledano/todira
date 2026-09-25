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
user just gets the plain welcome and the conversation ends immediately. When `/start` carries a
`ref_xxxxxx` channel-linking payload (see todira_common/channel_link.py), start() attaches this
Telegram account to the existing user the code belongs to BEFORE this function's own
`_has_filter_sync` check runs — so a linked account that already has a filter (the normal case:
someone connecting Telegram to a WhatsApp/Google account they already onboarded with elsewhere)
still ends the conversation immediately instead of re-onboarding them.
"""
from __future__ import annotations

import asyncio

from config import WEBSITE_URL
from todira_common import cities, gemini_client
from todira_common.db import get_session
from todira_common.matching import safe_range_update
from todira_common.models import Filter
from todira_common.users import get_or_create_user
from handlers.apartments import find_new_matches_to_show
from handlers.start import start
from handlers.support import escalate_to_owner, looks_like_help_request
from sqlalchemy import select
from telegram import Update
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


async def _cancel_for_other_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """2026-09-25 real bug fix: a user mid-onboarding (AWAIT_FREETEXT) who runs /filter instead of
    finishing the free-text flow used to get silently stuck. /filter isn't in this
    ConversationHandler's own states/fallbacks, so PTB correctly falls through and lets
    filter_conversation.py's own handler start normally for THAT one command — but this
    conversation's own per-user state (tracked independently by PTB, one dict per
    ConversationHandler) was never cleared, since it never actually "handled" that update. Every
    later plain-text message still matched AWAIT_FREETEXT's own catch-all MessageHandler (this
    handler is checked FIRST — registered before filter_conversation in bot/main.py), so anything
    the user then typed into /filter's own prompts (a city, a price, a date) got silently routed
    into Gemini as onboarding free text instead, and a real Filter row already existed for most of
    these users, so _save_filter_sync's insert kept hitting the unique constraint on
    Filter.user_id and showing an error on every subsequent message — exactly the real report this
    fixes.

    A ConversationHandler can only let ONE handler (in one registration group) actually process a
    given update, so this can't also transparently start /filter's own conversation in the SAME
    update — instead it cleanly ends onboarding's own state and asks the user to resend the
    command they meant, so IT correctly starts fresh, un-hijacked, from the very next message."""
    context.user_data.pop("onboarding", None)
    await update.message.reply_text(
        "ביטלתי את תהליך ההרשמה החופשי — שלח/י שוב את הפקודה כדי להמשיך 👍"
    )
    return ConversationHandler.END


def _save_filter_sync(tg_user, state: dict) -> int:
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
        # 2026-09-15: no longer sends the matching listings themselves as Telegram cards here (see
        # _handle_freetext's own comment) — only need the count now. find_new_matches_to_show is
        # still used (not find_matching_listings directly) purely for its bookkeeping side effect:
        # every currently-matching listing gets a SentNotification(reason=NEW) row, so a later
        # /filter re-save (filter_conversation.py) doesn't re-count it, AND a future price change on
        # it still reaches this user via the normal scraper/notifier.py flow. limit=None (the
        # default) so this count/bookkeeping covers EVERY current match, not an artificial subset —
        # a real owner complaint 2026-09-15: an almost-unconstrained filter reported "10 matches"
        # when the true number (checked directly against the DB) was 3,642. A second owner request
        # the same day, after seeing that real number: no cap at all, not even a bigger one —
        # someone whose filter matches thousands should see all of them via the link.
        total, _new_to_show = find_new_matches_to_show(session, user.id, filter_row)
        session.commit()
        return total


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
    # asyncio.to_thread — parse_onboarding_message is a synchronous, blocking Gemini API call
    # (a real network round-trip that can take seconds, longer under load) that was being awaited
    # directly on the event loop. With max_concurrent_updates=1 (see start.py/tests/
    # test_bot_async_db_calls.py's module docstring for the same bug already fixed for blocking DB
    # calls), that froze every other user's interaction with the bot for the full duration of this
    # one call — found live 2026-09-07 auditing every gemini_client call site; contact_fallback.py's
    # equivalent call already did this correctly.
    result = await asyncio.to_thread(
        gemini_client.parse_onboarding_message, text, state, cities.CITIES
    )

    if result is None:
        await update.message.reply_text(
            "מצטער, יש לי תקלה טכנית רגעית 😅 נסה/י לשלוח שוב בעוד רגע, או תמיד אפשר להגדיר ידנית "
            "עם /filter."
        )
        return AWAIT_FREETEXT

    # rooms_min/rooms_max and price_min/price_max go through safe_range_update, not the plain
    # per-key overwrite every other field uses — found live-code-review 2026-09-22: a multi-turn
    # onboarding conversation ("up to 3000" then later "actually not less than 5000") could merge
    # into price_min=5000, price_max=3000 with nothing catching it before _save_filter_sync writes
    # it. Same bug class (and same fix) already caught and applied to the identical Gemini-driven
    # merge in contact_fallback.py/whatsapp_webhook.py's own filter-editing paths — an inverted
    # range isn't cosmetic, it hard-fails every listing forever, indistinguishable from "no
    # current matches" (see safe_range_update's own docstring).
    for key in _EMPTY_STATE:
        if key in ("rooms_min", "rooms_max", "price_min", "price_max"):
            continue
        if key in result:
            state[key] = result[key]

    if "rooms_min" in result or "rooms_max" in result:
        state["rooms_min"], state["rooms_max"] = safe_range_update(
            state["rooms_min"], state["rooms_max"],
            result.get("rooms_min"), result.get("rooms_max"),
        )
    if "price_min" in result or "price_max" in result:
        state["price_min"], state["price_max"] = safe_range_update(
            state["price_min"], state["price_max"],
            result.get("price_min"), result.get("price_max"),
        )

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

    total = await asyncio.to_thread(_save_filter_sync, update.effective_user, state)

    context.user_data.pop("onboarding", None)
    await update.message.reply_text(
        "אפשר תמיד להרחיב את הסינון (מחיר, קומה, דרישות ועוד) עם /filter ⚙️"
    )

    # 2026-09-15: used to send every current match as its own Telegram card right here — see
    # filter_conversation.py's _handle_save, which had the exact same pattern and the exact same
    # real owner complaint the same day (a broad filter flooded the chat immediately, and the
    # count/send was silently capped at RESULT_LIMIT=10 regardless of the true number matching).
    # Now always just points at the website's own /apartments?uid=... view instead, same as there.
    apartments_url = f"{WEBSITE_URL}/apartments?uid={update.effective_user.id}"
    if total:
        await update.message.reply_text(f"👀 יש כרגע {total} דירות שמתאימות — כולן כאן: {apartments_url}")
    else:
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
        fallbacks=[
            CommandHandler("start", onboarding_entry),
            # 2026-09-25 real bug fix — see _cancel_for_other_command's own docstring: any other
            # real bot command must cleanly end this conversation's own dangling state, not leave
            # it silently hijacking every later plain-text message meant for a different flow.
            CommandHandler(
                ["filter", "setfilter", "apartments", "liked", "hidden", "profile"],
                _cancel_for_other_command,
            ),
        ],
        name="onboarding_conversation",
        persistent=True,
        # /start is already both an entry point and a fallback here, so it was never actually
        # stuck-proof-dependent the way filter_conversation.py was (see the allow_reentry comment
        # there for the real bug this class of gap causes) - set for consistency/defense-in-depth
        # anyway, since it's a free, standard safeguard for any command-entry conversation.
        allow_reentry=True,
    )
