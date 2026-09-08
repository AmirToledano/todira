"""Matches listings against active user filters and sends notifications — Telegram always, plus
(2026-09-08) a proactive WhatsApp Message Template push for users who linked WhatsApp AND opted
in (see _whatsapp_eligible, User.whatsapp_notifications_opted_in). Two notification cases:

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

from dorin_common import bright_data_client, whatsapp_client
from dorin_common.access import has_full_access
from dorin_common.cards import format_caption, send_listing_card
from dorin_common.enums import NotificationReason
from dorin_common.matching import evaluate
from dorin_common.models import Filter, Listing, SentNotification, User

logger = logging.getLogger(__name__)

# Mirrors website/main.py's WEBSITE_URL/_is_owner_id and bot/handlers/start.py's own copies — a
# proactive push notification needs both to build the same "🔒 upgrade to see this" lock line the
# bot's own on-demand handlers show (dorin_common.cards.format_caption, 2026-09-05).
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://todira.app").rstrip("/")
OWNER_TELEGRAM_USER_ID = os.environ.get("OWNER_TELEGRAM_USER_ID")

# Proactive WhatsApp Message Template push (2026-09-08) — see dorin_common/whatsapp_client.py's
# module docstring for why a template (not free-form text) is required outside the 24h window.
# Both unset by default, matching this project's "optional secret, safe until set" convention
# (bot-secret.yaml): with no template name configured, _whatsapp_eligible below is never true and
# this whole code path stays fully dormant — no WhatsApp send is even attempted — until the owner
# has a real Meta-APPROVED template to point at. See PROJECT_STATE.md for the exact copy
# submitted for review; the name/language here must match it exactly.
WHATSAPP_MATCH_TEMPLATE_NAME = os.environ.get("WHATSAPP_MATCH_TEMPLATE_NAME")
WHATSAPP_MATCH_TEMPLATE_LANGUAGE = os.environ.get("WHATSAPP_MATCH_TEMPLATE_LANGUAGE", "he")

# WhatsApp sends aren't subject to Telegram's same-chat flood control (SEND_DELAY_SECONDS exists
# specifically for that), but a short pause between API calls is still cheap insurance against
# tripping the Cloud API's own per-number rate limit during a burst of matches.
WHATSAPP_SEND_DELAY_SECONDS = 0.3


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


def _whatsapp_eligible(user: User) -> bool:
    """Whether `user` should get the proactive WhatsApp Message Template send below — needs a
    linked number, the user's own explicit opt-in (see models.py's User.whatsapp_notifications_
    opted_in docstring for why that's separate from notifications_enabled), AND an actually-
    configured/approved template name. All three, every time — this is deliberately NOT cached
    per-run, since it's cheap and a mid-run env change should never matter (it can't happen in
    practice; a pod's env is fixed at start, this is just not assuming that)."""
    return bool(
        WHATSAPP_MATCH_TEMPLATE_NAME
        and user.whatsapp_phone_number
        and user.whatsapp_notifications_opted_in
    )


def _whatsapp_template_param(value: str, *, max_length: int = 300) -> str:
    """WhatsApp template params can't contain a newline or 4+ consecutive spaces (Meta rejects
    the whole send if one does) — collapse whitespace defensively since this runs on scraped
    listing data this project didn't write itself, not a hardcoded string. Also length-capped:
    Meta's own per-parameter limit is generous, but a listing field is never expected to need it,
    so a long one is far more likely mis-scraped junk than genuine content worth showing in full."""
    collapsed = " ".join(value.split())
    if len(collapsed) > max_length:
        return collapsed[: max_length - 1] + "…"
    return collapsed


def _send_whatsapp_match_template(user: User, listing: Listing) -> bool:
    """The proactive "new match" WhatsApp push — see WHATSAPP_MATCH_TEMPLATE_NAME's own comment
    and PROJECT_STATE.md for the exact template copy this must match. Only 3 body variables
    (location, rooms, price), each flanked by static text on both sides — no URL variable in the
    body. The "view listings" link is instead a fully STATIC website button baked into the
    template itself at creation time in Meta's WhatsApp Manager (https://todira.app/apartments,
    no per-user query string), which needs no runtime parameter here at all. Two deliberate
    reasons: (1) Meta has historically been stricter about a variable sitting at the very start or
    end of a template body — keeping every variable mid-sentence sidesteps that risk entirely
    rather than betting on current behavior; (2) unlike format_caption's Telegram card, this can't
    do real access-gating (has_access + upgrade_url) on the content anyway — a static link to
    /apartments (whose own access gating already hides full details behind the paywall
    server-side) is exactly as useful as a per-user one here, so there's nothing to gain from a
    dynamic URL variable that would only add rejection risk."""
    location = listing.street or listing.neighborhood or listing.city or "דירה"
    rooms = f"{float(listing.rooms):g}" if listing.rooms is not None else "-"
    price = f"{listing.price:,}" if listing.price is not None else "-"
    return whatsapp_client.send_template_message(
        user.whatsapp_phone_number,
        template_name=WHATSAPP_MATCH_TEMPLATE_NAME,
        language_code=WHATSAPP_MATCH_TEMPLATE_LANGUAGE,
        body_params=[
            _whatsapp_template_param(location),
            _whatsapp_template_param(rooms),
            _whatsapp_template_param(price),
        ],
    )


async def _maybe_fetch_description(session: Session, listing: Listing, recipients: list[User]) -> None:
    """Bright Data on-demand enrichment (2026-09-05, common/dorin_common/bright_data_client.py) —
    fetches and caches the listing's real description, but ONLY when it's worth the cost: this is
    called after matching is already done, with the actual list of users about to be notified, and
    does nothing unless at least one of them is a PAYING user (has_access) who would actually see
    the result (format_caption strips the description entirely for anyone else). This is the exact
    sequencing difference the owner asked for — match first, then decide whether to spend a fetch —
    not fetching speculatively for every scraped listing regardless of who it matches. website/
    main.py's _fill_missing_descriptions_in_background (2026-09-07) covers the complementary case
    this discovery-time-only trigger can't: a listing whose paying match happens AFTER discovery."""
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
        if user.telegram_user_id is None and not _whatsapp_eligible(user):
            # No channel to actually push through. A Google-only standalone account (2026-09-05)
            # legitimately has neither; a WhatsApp-only or -linked account has a channel to send
            # to but hasn't opted in yet (see _whatsapp_eligible). Either way they can still check
            # the website manually, or link Telegram / opt in via /account for a push. Skipping
            # here (rather than letting a send fail on a missing/ineligible destination every
            # single time) avoids repeated wasted API calls/log noise for the exact same listing
            # on every future scrape run, since a failed send never writes a SentNotification row
            # to remember "already tried."
            continue
        to_notify.append((filter_row, user))

    await _maybe_fetch_description(session, listing, [user for _f, user in to_notify])

    for filter_row, user in to_notify:
        sent_on_any_channel = False
        if user.telegram_user_id is not None:
            caption = format_caption(
                listing,
                has_access=_has_access_for(user),
                upgrade_url=f"{WEBSITE_URL}/upgrade?uid={user.telegram_user_id}",
            )
            if await send_listing_card(bot, user.telegram_user_id, listing, caption):
                sent_on_any_channel = True
            await asyncio.sleep(SEND_DELAY_SECONDS)
        if _whatsapp_eligible(user):
            if _send_whatsapp_match_template(user, listing):
                sent_on_any_channel = True
            await asyncio.sleep(WHATSAPP_SEND_DELAY_SECONDS)
        if sent_on_any_channel:
            # One row per user per listing regardless of how many channels it went out on — this
            # only ever means "has this user already been told about this listing," matching
            # _already_notified's own reason-only (not channel-specific) lookup key. A user linked
            # on both channels who's opted into WhatsApp alerts gets both pushes the first time a
            # listing matches, but is never re-notified on a later run either way.
            session.add(
                SentNotification(
                    user_id=filter_row.user_id,
                    listing_id=listing.id,
                    reason=NotificationReason.NEW,
                )
            )
            session.commit()
            sent += 1
    return matched, sent


async def _notify_price_change(bot: Bot, session: Session, listing: Listing, old_price: int) -> int:
    """Re-notify users who already received a 'new' notification for this exact listing that its
    price just changed — 📉 drop or 📈 increase, whichever `old_price` vs. `listing.price` says
    (see format_caption's _price_change_header). Drop and increase are separate
    NotificationReasons, so a listing that drops and later rises again can still notify for the
    increase even though its drop notification already went out — and vice versa. One
    notification per user per listing PER DIRECTION in v1 — if the same listing drops twice in a
    row, that's a documented simplification, not a bug (revisit if it matters).

    Telegram-only, deliberately, unlike _notify_new_matches (2026-09-08): a price-change WhatsApp
    push would need its own separate Meta-approved template — "your saved search matched" and
    "the price on a listing you were already shown just changed" are different enough content
    that the same template copy can't honestly cover both. Not built until there's a second
    approved template to point at; revisit then."""
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
            # Price-change re-notifications are Telegram-only — see this function's own
            # docstring for why (no WhatsApp template covers this content yet).
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
