"""/apartments — how many of the user's saved filter's current matches exist right now, with a
link to see them all on the website. `find_matching_listings`/`find_new_matches_to_show` now live
in todira_common.listing_matches (2026-09-27, no longer bot-only — website/whatsapp_webhook.py
needs the same query+bookkeeping) and are re-exported here unchanged for this module's own
existing callers/tests (filter_conversation.py imports find_new_matches_to_show from here)."""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from config import WEBSITE_URL
from todira_common.bot_strings import bot_text
from todira_common.db import get_session
from todira_common.language import DEFAULT_LANG
from todira_common.listing_matches import find_matching_listings, find_new_matches_to_show
from todira_common.models import Filter, User
from todira_common.uid_token import signed_login_query

__all__ = ["find_matching_listings", "find_new_matches_to_show", "apartments", "build_apartments_handler"]


def _count_matches_sync(tg_user) -> tuple[int | None, str]:
    """Returns (count, lang) — count is None to signal "no saved filter yet" (vs. 0 = a real
    filter with no current matches), the caller needs to tell the two apart to show a different
    message. Otherwise the TRUE total number of current matches, no cap (see
    find_matching_listings' own 2026-09-15 comment). lang is DEFAULT_LANG when there's no user row
    yet to read a language preference off of.

    2026-09-15: this used to load up to RESULT_LIMIT=10 Listing rows and send each as its own
    Telegram card directly in the chat. Real owner complaint the same day: for a broad filter
    (thousands of matches) that both flooded the chat with an arbitrary, uninformative subset of
    only 10 AND never told the user how many really matched. Same fix direction as
    filter_conversation._handle_save's own 2026-09-15 change: just the count, plus a link to the
    website's own full, paginated /apartments view — which already applies its own
    has_access/locked-card gating (see website/main.py's own /apartments route), so this command
    doesn't need to know or care about access level at all anymore."""
    with get_session() as session:
        user = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
        if user is None:
            return None, DEFAULT_LANG
        lang = user.language or DEFAULT_LANG
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user.id))
        if filter_row is None:
            return None, lang
        return len(find_matching_listings(session, user.id, filter_row)), lang


async def apartments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # asyncio.to_thread — see handlers/start.py's _upsert_user_sync comment: PTB processes
    # updates one at a time by default, so a blocking DB call on the event loop freezes every
    # other user's interaction with the bot too, not just this one.
    total, lang = await asyncio.to_thread(_count_matches_sync, update.effective_user)
    if total is None:
        await update.message.reply_text(bot_text("apartments.no_filter_yet", lang))
        return

    apartments_url = f"{WEBSITE_URL}/apartments?{signed_login_query(update.effective_user.id)}"
    if total:
        await update.message.reply_text(
            bot_text("onboarding.matches_found", lang, total=total, apartments_url=apartments_url)
        )
    else:
        await update.message.reply_text(
            bot_text("apartments.no_matches", lang, apartments_url=apartments_url)
        )


def build_apartments_handler() -> CommandHandler:
    return CommandHandler("apartments", apartments)
