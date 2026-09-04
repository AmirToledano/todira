"""Matches listings against active user filters and sends Telegram notifications. Two cases:

1. A brand-new listing (or an existing listing whose price just changed into someone's budget)
   gets the normal "new match" notification, once per user, ever (reason='new').
2. An existing listing whose price changed, for users who were ALREADY sent a 'new' notification
   about it, gets a distinct "📉 price drop" / "📈 price increase" notification
   (reason='price_drop'/'price_increase') — this is what the user showed me from the reference
   bot: the same listing re-appearing with "ירידת מחיר!" and the old price. Kept separate from
   case 1 so someone who's never heard of a listing isn't confusingly told its price "changed."
   Drop and increase are tracked as distinct reasons (not "one price-change re-notification per
   listing" — a listing whose price both drops and later rises again should be able to notify for
   each, symmetric to how drop always worked).

See plan Section 4 for the base matching/rate-limiting design; the price-drop path was added
after the user pointed out this feature wasn't in the original design, then generalized to also
cover increases 2026-09-02 per an explicit request that both directions get a re-notification.
"""
from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session
from telegram import Bot

import bright_data_client
from dorin_common.access import has_full_access
from dorin_common.cards import format_caption, send_listing_card
from dorin_common.enums import NotificationReason
from dorin_common.matching import evaluate
from dorin_common.models import Filter, Listing, SentNotification, User

logger = logging.getLogger(__name__)

# Mirrors website/main.py's WEBSITE_URL/_is_owner_id and bot/handlers/start.py's own copies — a
# proactive push notification needs both to build the same "🔒 upgrade to see this" lock line the
# bot's own on-demand handlers show (dorin_common.cards.format_caption, 2026-09-05).
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://todira.duckdns.org").rstrip("/")
OWNER_TELEGRAM_USER_ID = os.environ.get("OWNER_TELEGRAM_USER_ID")


def _has_access_for(user: User) -> bool:
    is_owner = bool(OWNER_TELEGRAM_USER_ID) and str(user.telegram_user_id) == str(
        OWNER_TELEGRAM_USER_ID
    )
    return has_full_access(user, is_owner=is_owner)

# Telegram's ~30 msgs/sec is a GLOBAL cap across different chats, not the same-chat limit that
# actually matters here: one user matching several listings in a row (routine — a burst of new
# listings, or exactly this backfill workflow's own real 2026-09-02 run, which matched 17 listings
# to one chat) sends repeatedly to the SAME chat_id, and Telegram enforces roughly 1 message/sec
# per chat there — tighter still for a real-photo send, which is 2 API calls (the media group, then
# the follow-up keyboard message), not 1. 0.05s was tuned for the old text/single-photo-only
# sending pattern and started hitting Telegram's flood control (429/RetryAfter) once real photo
# sending shipped — found live via that same backfill run (4 of 17 real match notifications
# silently dropped; see send_listing_card's own RetryAfter-retry, added alongside this).
SEND_DELAY_SECONDS = 1.1


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


async def _maybe_fetch_description(session: Session, listing: Listing, recipients: list[User]) -> None:
    """Bright Data on-demand enrichment (2026-09-05, scraper/bright_data_client.py) — fetches and
    caches the listing's real description, but ONLY when it's worth the cost: this is called after
    matching is already done, with the actual list of users about to be notified, and does nothing
    unless at least one of them is a PAYING user (has_access) who would actually see the result
    (format_caption strips the description entirely for anyone else). This is the exact sequencing
    difference the owner asked for — match first, then decide whether to spend a fetch — not
    fetching speculatively for every scraped listing regardless of who it matches."""
    if listing.description or not bright_data_client.is_configured():
        return
    if not any(_has_access_for(user) for user in recipients):
        return
    description = await asyncio.to_thread(bright_data_client.fetch_listing_description, listing.url)
    if description:
        listing.description = description
        session.commit()


async def _notify_new_matches(bot: Bot, session: Session, listing: Listing) -> tuple[int, int]:
    """Send 'new match' notifications for one listing to every currently-matching active filter
    that hasn't already received one. Covers both genuinely new listings and existing listings
    that now match a filter they didn't before (e.g. a price drop brought them into budget).
    Returns (matched_count, sent_count)."""
    matched = 0
    sent = 0
    to_notify: list[tuple[Filter, User]] = []
    for filter_row in _candidate_filters(session, listing):
        if not evaluate(filter_row, listing).matched:
            continue
        matched += 1
        if _already_notified(session, filter_row.user_id, listing.id, NotificationReason.NEW):
            continue
        user = session.get(User, filter_row.user_id)
        if user is None:
            continue
        if user.telegram_user_id is None:
            # Push notifications are Telegram-only today (see this module's own docstring — no
            # WhatsApp send path exists yet). A Google-only standalone account (2026-09-05) or a
            # WhatsApp-only account both legitimately have no telegram_user_id — they check the
            # website manually, or can link Telegram via /account for push, but there is
            # nothing to send to right now. Skipping here (rather than letting send_listing_card
            # fail on chat_id=None every single time) avoids repeated wasted API calls/log noise
            # for the exact same listing on every future scrape run, since a failed send never
            # writes a SentNotification row to remember "already tried."
            continue
        to_notify.append((filter_row, user))

    await _maybe_fetch_description(session, listing, [user for _f, user in to_notify])

    for filter_row, user in to_notify:
        caption = format_caption(
            listing,
            has_access=_has_access_for(user),
            upgrade_url=f"{WEBSITE_URL}/upgrade?uid={user.telegram_user_id}",
        )
        if await send_listing_card(bot, user.telegram_user_id, listing, caption):
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


async def _notify_price_change(bot: Bot, session: Session, listing: Listing, old_price: int) -> int:
    """Re-notify users who already received a 'new' notification for this exact listing that its
    price just changed — 📉 drop or 📈 increase, whichever `old_price` vs. `listing.price` says
    (see format_caption's _price_change_header). Drop and increase are separate
    NotificationReasons, so a listing that drops and later rises again can still notify for the
    increase even though its drop notification already went out — and vice versa. One
    notification per user per listing PER DIRECTION in v1 — if the same listing drops twice in a
    row, that's a documented simplification, not a bug (revisit if it matters)."""
    sent = 0
    reason = (
        NotificationReason.PRICE_DROP
        if old_price > listing.price
        else NotificationReason.PRICE_INCREASE
    )
    previously_notified_user_ids = list(
        session.scalars(
            select(SentNotification.user_id).where(
                SentNotification.listing_id == listing.id,
                SentNotification.reason == NotificationReason.NEW,
            )
        )
    )
    to_notify: list[User] = []
    for user_id in previously_notified_user_ids:
        if _already_notified(session, user_id, listing.id, reason):
            continue
        user = session.get(User, user_id)
        if user is None or not user.is_active or not user.notifications_enabled:
            continue
        if user.telegram_user_id is None:
            # See _notify_new_matches' own comment on why this is skipped, not attempted.
            continue
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user_id))
        if filter_row is None or not evaluate(filter_row, listing).matched:
            continue
        to_notify.append(user)

    await _maybe_fetch_description(session, listing, to_notify)

    for user in to_notify:
        caption = format_caption(
            listing,
            has_access=_has_access_for(user),
            price_change_from=old_price,
            upgrade_url=f"{WEBSITE_URL}/upgrade?uid={user.telegram_user_id}",
        )
        if await send_listing_card(bot, user.telegram_user_id, listing, caption):
            session.add(
                SentNotification(user_id=user.id, listing_id=listing.id, reason=reason)
            )
            session.commit()
            sent += 1
        await asyncio.sleep(SEND_DELAY_SECONDS)
    return sent


async def run_notifications(
    session: Session,
    new_listings: list[Listing],
    price_change_events: list[tuple[Listing, int]],
) -> dict[str, int]:
    """`new_listings`: rows inserted for the first time this run. `price_change_events`:
    (listing, old_price) pairs for existing listings whose price just changed (either direction).
    Returns a summary dict for main.py's run-summary log line."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    matched_count = 0
    new_sent_count = 0
    price_change_sent_count = 0

    async with Bot(token=token) as bot:
        for listing in new_listings:
            m, s = await _notify_new_matches(bot, session, listing)
            matched_count += m
            new_sent_count += s
        for listing, old_price in price_change_events:
            # a price change can also newly qualify filters that were previously priced out
            m, s = await _notify_new_matches(bot, session, listing)
            matched_count += m
            new_sent_count += s
            price_change_sent_count += await _notify_price_change(bot, session, listing, old_price)

    return {
        "matched": matched_count,
        "notifications_sent": new_sent_count,
        "price_change_notifications_sent": price_change_sent_count,
    }
