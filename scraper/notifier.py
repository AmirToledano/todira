"""Matches listings against active user filters and sends Telegram notifications. Two cases:

1. A brand-new listing (or an existing listing whose price just dropped into someone's budget)
   gets the normal "new match" notification, once per user, ever (reason='new').
2. An existing listing whose price dropped, for users who were ALREADY sent a 'new' notification
   about it, gets a distinct "📉 price drop" notification (reason='price_drop') — this is what
   the user showed me from the reference bot: the same listing re-appearing with "ירידת מחיר!"
   and the old price. Kept separate from case 1 so someone who's never heard of a listing isn't
   confusingly told its price "dropped."

See plan Section 4 for the base matching/rate-limiting design; the price-drop path was added
after the user pointed out this feature wasn't in the original design.
"""
from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session
from telegram import Bot

from dorin_common.cards import format_caption, send_listing_card
from dorin_common.enums import NotificationReason
from dorin_common.matching import evaluate
from dorin_common.models import Filter, Listing, SentNotification, User

logger = logging.getLogger(__name__)

SEND_DELAY_SECONDS = 0.05  # stays well under Telegram's ~30 msgs/sec global cap


def _candidate_filters(session: Session, listing: Listing) -> list[Filter]:
    """Cheap SQL pre-filter (deal_type + city overlap via the GIN index on filters.cities)
    before the full per-field Python evaluation in dorin_common.matching.evaluate."""
    stmt = (
        select(Filter)
        .join(User, User.id == Filter.user_id)
        .where(User.is_active.is_(True))
        .where(User.notifications_enabled.is_(True))
        .where(Filter.deal_type == listing.deal_type)
    )
    if listing.city:
        # `::text[]` cast is required — `filters.cities` is `text[]`, and Postgres' `&&` array
        # overlap operator does NOT implicitly cast `text[]` against the driver's default
        # `varchar[]` inference for a bare string bind param inside ARRAY[...] (confirmed against
        # a real Postgres 2026-09-02: `bindparam(..., type_=Text)` alone does NOT fix this —
        # verified live, not guessed — only an explicit cast on the array literal does). This was
        # a latent bug never triggered before: it only runs when a fetched listing actually has a
        # matching active filter, which never happened until the ZenRows Fetch API migration
        # (see yad2_client.py) produced the first real successful fetch.
        city_clause = text(
            "(filters.cities = '{}' OR filters.cities && ARRAY[:city]::text[])"
        ).bindparams(bindparam("city", value=listing.city))
    else:
        city_clause = text("filters.cities = '{}'")
    return list(session.scalars(stmt.where(city_clause)))


def _already_notified(session: Session, user_id: int, listing_id: int, reason: str) -> bool:
    return (
        session.execute(
            select(SentNotification.id).where(
                SentNotification.user_id == user_id,
                SentNotification.listing_id == listing_id,
                SentNotification.reason == reason,
            )
        ).first()
        is not None
    )


async def _notify_new_matches(bot: Bot, session: Session, listing: Listing) -> tuple[int, int]:
    """Send 'new match' notifications for one listing to every currently-matching active filter
    that hasn't already received one. Covers both genuinely new listings and existing listings
    that now match a filter they didn't before (e.g. a price drop brought them into budget).
    Returns (matched_count, sent_count)."""
    matched = 0
    sent = 0
    for filter_row in _candidate_filters(session, listing):
        if not evaluate(filter_row, listing).matched:
            continue
        matched += 1
        if _already_notified(session, filter_row.user_id, listing.id, NotificationReason.NEW):
            continue
        user = session.get(User, filter_row.user_id)
        if user is None:
            continue
        if await send_listing_card(bot, user.telegram_user_id, listing, format_caption(listing)):
            session.add(
                SentNotification(
                    user_id=filter_row.user_id,
                    listing_id=listing.id,
                    reason=NotificationReason.NEW,
                )
            )
            session.commit()
            sent += 1
        await asyncio.sleep(SEND_DELAY_SECONDS)
    return matched, sent


async def _notify_price_drop(bot: Bot, session: Session, listing: Listing, old_price: int) -> int:
    """Re-notify users who already received a 'new' notification for this exact listing that its
    price just dropped. One price-drop notification per user per listing in v1 — if the price
    drops again later, that's a documented simplification, not a bug (revisit if it matters)."""
    sent = 0
    previously_notified_user_ids = list(
        session.scalars(
            select(SentNotification.user_id).where(
                SentNotification.listing_id == listing.id,
                SentNotification.reason == NotificationReason.NEW,
            )
        )
    )
    for user_id in previously_notified_user_ids:
        if _already_notified(session, user_id, listing.id, NotificationReason.PRICE_DROP):
            continue
        user = session.get(User, user_id)
        if user is None or not user.is_active or not user.notifications_enabled:
            continue
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user_id))
        if filter_row is None or not evaluate(filter_row, listing).matched:
            continue

        caption = format_caption(listing, price_drop_from=old_price)
        if await send_listing_card(bot, user.telegram_user_id, listing, caption):
            session.add(
                SentNotification(
                    user_id=user_id,
                    listing_id=listing.id,
                    reason=NotificationReason.PRICE_DROP,
                )
            )
            session.commit()
            sent += 1
        await asyncio.sleep(SEND_DELAY_SECONDS)
    return sent


async def run_notifications(
    session: Session,
    new_listings: list[Listing],
    price_drop_events: list[tuple[Listing, int]],
) -> dict[str, int]:
    """`new_listings`: rows inserted for the first time this run. `price_drop_events`:
    (listing, old_price) pairs for existing listings whose price just went down. Returns a
    summary dict for main.py's run-summary log line."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    matched_count = 0
    new_sent_count = 0
    price_drop_sent_count = 0

    async with Bot(token=token) as bot:
        for listing in new_listings:
            m, s = await _notify_new_matches(bot, session, listing)
            matched_count += m
            new_sent_count += s
        for listing, old_price in price_drop_events:
            # a price drop can also newly qualify filters that were previously priced out
            m, s = await _notify_new_matches(bot, session, listing)
            matched_count += m
            new_sent_count += s
            price_drop_sent_count += await _notify_price_drop(bot, session, listing, old_price)

    return {
        "matched": matched_count,
        "notifications_sent": new_sent_count,
        "price_drop_notifications_sent": price_drop_sent_count,
    }
