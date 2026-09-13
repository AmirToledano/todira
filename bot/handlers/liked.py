"""/liked and /hidden, plus the shared ❤️/🙈/🎉 inline-button handler attached to every listing
card — sent both by the scraper's new-match notifications and by this bot's /apartments, /liked,
and /hidden. The bot process (long-running, polling) is what receives the button press regardless
of which process originally sent the card.
"""
from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy import delete, select
from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from config import WEBSITE_URL
from dorin_common.access import has_full_access
from dorin_common.cards import format_caption, send_listing_card
from dorin_common.db import get_session
from dorin_common.models import Listing, UserListingAction
from dorin_common.users import get_or_create_user

logger = logging.getLogger(__name__)

LIKED_LIMIT = 10
HIDDEN_LIMIT = 10

# Mirrors website/main.py's _is_owner_id / bot/handlers/start.py's own copy — same secret, same
# "owner always has full access" override.
OWNER_TELEGRAM_USER_ID = os.environ.get("OWNER_TELEGRAM_USER_ID")


def _load_by_action_sync(tg_user, db_action: str, limit: int) -> tuple[bool, list[Listing]]:
    """(has_access, listings) — has_access (dorin_common.access.has_full_access) decides whether
    format_caption below shows the full card or the locked/teaser one, see that module's
    2026-09-05 comment."""
    with get_session() as session:
        user = get_or_create_user(session, tg_user)
        is_owner = bool(OWNER_TELEGRAM_USER_ID) and str(tg_user.id) == str(OWNER_TELEGRAM_USER_ID)
        access = has_full_access(user, is_owner=is_owner)
        stmt = (
            select(Listing)
            .join(UserListingAction, UserListingAction.listing_id == Listing.id)
            .where(UserListingAction.user_id == user.id)
            .where(UserListingAction.action == db_action)
            .where(Listing.is_delisted.is_(False))
            # 2026-09-13 cross-source dedup — shouldn't be reachable in practice (a duplicate row
            # is never shown as its own card to like in the first place, see apartments.py's own
            # same filter), kept here too for defense in depth / consistency with every other
            # "active listings" query. See models.py's Listing.duplicate_of_id docstring.
            .where(Listing.duplicate_of_id.is_(None))
            .order_by(UserListingAction.created_at.desc())
            .limit(limit)
        )
        return access, list(session.scalars(stmt))


async def liked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # asyncio.to_thread — see handlers/start.py's _upsert_user_sync comment: a synchronous DB
    # call directly on the event loop would freeze every other user's bot interaction too, not
    # just this one, since PTB processes updates one at a time by default.
    has_access, results = await asyncio.to_thread(
        _load_by_action_sync, update.effective_user, "liked", LIKED_LIMIT
    )

    if not results:
        await update.message.reply_text(
            "עדיין לא שמרת אף דירה. אפשר ללחוץ ❤️ שמור על כרטיס דירה כדי לשמור אותה כאן."
        )
        return

    upgrade_url = f"{WEBSITE_URL}/upgrade?uid={update.effective_user.id}"
    for listing in results:
        await send_listing_card(
            context.bot,
            update.effective_chat.id,
            listing,
            format_caption(listing, has_access=has_access, upgrade_url=upgrade_url),
        )


async def hidden(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # 2026-09-03, real user report: once a listing was hidden it disappeared for good — /apartments
    # excludes hidden listings on purpose (see apartments.py's find_matching_listings), but there
    # was no way to ever see a hidden listing again to change your mind. Mirrors /liked exactly,
    # just for action="hidden" — same toggle-capable ❤️/🙈 buttons on each card (see
    # _apply_reaction_sync below), so pressing 🙈 here un-hides it.
    has_access, results = await asyncio.to_thread(
        _load_by_action_sync, update.effective_user, "hidden", HIDDEN_LIMIT
    )

    if not results:
        await update.message.reply_text("אין לך כרגע דירות מוסתרות.")
        return

    upgrade_url = f"{WEBSITE_URL}/upgrade?uid={update.effective_user.id}"
    for listing in results:
        await send_listing_card(
            context.bot,
            update.effective_chat.id,
            listing,
            format_caption(listing, has_access=has_access, upgrade_url=upgrade_url),
        )


def _apply_reaction_sync(tg_user, action: str, listing_id: int) -> str:
    """Returns the toast text to show via query.answer(). "like"/"hide" TOGGLE (press again to
    undo) — 2026-09-03, real user report: pressing ❤️ on an already-liked listing (e.g. from
    inside /liked itself, which re-sends the same buttons) was a silent no-op, with no way to
    remove a listing from /liked or bring one back from /hidden. Previously pure-add (`if not
    exists: insert`); now removes the existing action instead of doing nothing when it's already
    there, mirroring the exact opposite of what /liked and /hidden are for."""
    with get_session() as session:
        user = get_or_create_user(session, tg_user)

        if action == "found":
            user.is_active = False
            session.commit()
            return "מזל טוב! השהיתי את החיפוש עבורך. שלח/י /start כדי לחזור."

        db_action = "liked" if action == "like" else "hidden"
        existing_id = session.scalar(
            select(UserListingAction.id).where(
                UserListingAction.user_id == user.id,
                UserListingAction.listing_id == listing_id,
                UserListingAction.action == db_action,
            )
        )
        if existing_id is not None:
            session.execute(delete(UserListingAction).where(UserListingAction.id == existing_id))
            session.commit()
            return "הוסר מהשמורים 💔" if action == "like" else "הוחזר לרשימה 👀"

        session.add(UserListingAction(user_id=user.id, listing_id=listing_id, action=db_action))
        session.commit()

    return "נשמר ❤️" if action == "like" else "הוסתר 🙈"


async def reaction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    action, _, raw_id = query.data.partition(":")
    listing_id = int(raw_id)

    try:
        # asyncio.to_thread — see handlers/start.py's _upsert_user_sync comment: a synchronous DB
        # call directly on the event loop would freeze every other user's bot interaction too, not
        # just this one, since PTB processes updates one at a time by default.
        toast = await asyncio.to_thread(
            _apply_reaction_sync, update.effective_user, action, listing_id
        )
    except Exception:
        # Found live 2026-09-07: on any DB error here, query.answer() was never reached, leaving
        # the tapped button's own "loading" spinner stuck on the user's screen until Telegram's
        # client-side timeout — a real error looked identical to the bot being frozen. Always
        # answer, even on failure, so the user gets immediate feedback either way.
        logger.exception(
            "Failed to apply reaction action=%s listing_id=%s for user %s",
            action,
            listing_id,
            update.effective_user.id,
        )
        await query.answer("משהו השתבש, נסה/י שוב 🙏")
        return

    await query.answer(toast)


def build_reaction_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(reaction_callback, pattern=r"^(like|hide|found):\d+$")


def build_liked_handler() -> CommandHandler:
    return CommandHandler("liked", liked)


def build_hidden_handler() -> CommandHandler:
    return CommandHandler("hidden", hidden)
