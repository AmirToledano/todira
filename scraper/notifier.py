"""Matches listings against active user filters and sends notifications — Telegram always, plus
(2026-10-02) a free-form WhatsApp message for users who linked WhatsApp, opted in AND whose 24h
customer-service window is open (see _whatsapp_eligible) — never a paid template. Two notification cases:

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
import datetime as dt
import logging
import os

import httpx

from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session
from telegram import Bot

from todira_common import whatsapp_client, whatsapp_guard, yad2_detail
from todira_common.access import access_state, has_full_access
from todira_common.bot_strings import bot_text
from todira_common.cards import (
    format_caption,
    format_caption_whatsapp,
        send_listing_card,
)
from todira_common.enums import NotificationReason, Source
from todira_common.language import DEFAULT_LANG
from todira_common.matching import evaluate
from todira_common.models import Filter, Listing, SentNotification, User
from todira_common.uid_token import signed_login_query
from todira_common.whatsapp_window import window_open
from todira_common.wid_token import generate_wid_token


logger = logging.getLogger(__name__)

# Mirrors website/main.py's WEBSITE_URL/_is_owner_id and bot/handlers/start.py's own copies — a
# proactive push notification needs both to build the same "🔒 upgrade to see this" lock line the
# bot's own on-demand handlers show (todira_common.cards.format_caption, 2026-09-05).
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://todira.app").rstrip("/")
OWNER_TELEGRAM_USER_ID = os.environ.get("OWNER_TELEGRAM_USER_ID")

# WhatsApp sends aren't subject to Telegram's same-chat flood control (SEND_DELAY_SECONDS exists
# specifically for that), but a short pause between API calls is still cheap insurance against
# tripping the Cloud API's own per-number rate limit during a burst of matches.
WHATSAPP_SEND_DELAY_SECONDS = 0.3
# A WhatsApp interactive message body is capped at 1024 characters.
WHATSAPP_INTERACTIVE_BODY_LIMIT = 1024


def _has_access_for(user: User) -> bool:
    is_owner = bool(OWNER_TELEGRAM_USER_ID) and str(user.telegram_user_id) == str(
        OWNER_TELEGRAM_USER_ID
    )
    return has_full_access(user, is_owner=is_owner)


def _access_state_for(user: User) -> str:
    """todira_common.access.access_state with the same owner override as _has_access_for — lets a card tell a user
    whose free trial ended from one whose paid subscription ended."""
    is_owner = bool(OWNER_TELEGRAM_USER_ID) and str(user.telegram_user_id) == str(
        OWNER_TELEGRAM_USER_ID
    )
    return access_state(user, is_owner=is_owner)

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
    before the full per-field Python evaluation in todira_common.matching.evaluate."""
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
    """Whether `user` may be sent a WhatsApp listing RIGHT NOW: a linked number, their own opt-in
    (see models.py's User.whatsapp_notifications_opted_in), AND an open 24h customer-service window
    (todira_common/whatsapp_window.py). The last condition is what keeps WhatsApp free: Meta bills
    template messages sent outside the window, so this project never sends one — a user whose window
    is closed simply gets nothing until they next reply (the hourly check-in in
    scraper/whatsapp_checkin.py asks for exactly that), and whatever they missed is summarized in one
    link by website/whatsapp_webhook.py when they do."""
    return bool(
        user.whatsapp_phone_number
        and user.whatsapp_notifications_opted_in
        and window_open(user.whatsapp_last_inbound_at)
    )


def _send_whatsapp_match_message(user: User, listing: Listing) -> bool:
    """The proactive "new match" WhatsApp push: one FREE-FORM message — the listing's real photo,
    every field format_caption_whatsapp shows, and a button to the listing page (signed ?wid= login
    link, since a WhatsApp-only user has no other way to land logged in; see website/main.py's
    _resolve_user). Free-form, so only valid inside the 24h window — callers gate on
    _whatsapp_eligible. Blocking (downloads/composites a photo, then two HTTP calls): the caller
    MUST run it via asyncio.to_thread, same contract as get_listing_photo_jpeg_bytes."""
    lang = user.language or DEFAULT_LANG
    has_access = _has_access_for(user)
    wid = generate_wid_token(user.whatsapp_phone_number)
    view_url = f"{WEBSITE_URL}/apartments?wid={wid}&listing={listing.id}"
    upgrade_url = f"{WEBSITE_URL}/upgrade?wid={wid}"
    body = format_caption_whatsapp(
        listing,
        has_access=has_access,
        upgrade_url=upgrade_url,
        view_url=view_url,
        link_in_body=False,
        limit=WHATSAPP_INTERACTIVE_BODY_LIMIT,
        lang=lang,
        access_state=_access_state_for(user),
    )
    # Meta needs the header photo as a public link, so the website serves the listing's photo/collage
    # (website/main.py's /media/listing/{id}.jpg). Requesting it here first builds and caches it, so
    # Meta's own fetch a moment later is instant instead of waiting on the collage download.
    photo_url = f"{WEBSITE_URL}/media/listing/{listing.id}.jpg"
    try:
        warm = httpx.get(photo_url, timeout=45.0)
        warm.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Could not prepare the WhatsApp photo for listing %s — skipping this send", listing.id)
        return False
    return whatsapp_client.send_image_cta_message(
        user.whatsapp_phone_number,
        image_url=photo_url,
        body=body,
        button_text=bot_text(
            "whatsapp.view_listing_button" if has_access else "whatsapp.upgrade_button", lang
        ),
        url=view_url if has_access else upgrade_url,
    )


async def _maybe_fetch_description(session: Session, listing: Listing, recipients: list[User]) -> None:
    """Just-in-time detail fetch (kept under its old name): called after matching is done and right before the cards go
    out, so a Yad2 listing whose details were never read (over the eager per-run cap, the earlier attempt failed, or it
    reached the retry pass) still carries its description, total floors, entry date and features on the card.

    2026-10-09: no longer limited to listings a paying user will see, and no longer Gemini-only. Details come from
    Yad2's own item JSON (free, todira_common/yad2_item_api.py) with Gemini as the backup — see todira_common/
    yad2_detail.py — so the old cost reason for fetching only when a paying recipient existed is gone, and the owner's
    rule is that every card is complete (the description is shown to every viewer regardless of subscription; only the
    original-listing link is gated). `listing.details_fetched_at` is the "already asked" marker: a listing is fetched at
    most once successfully, however many users it matches. Komo / Homeless / Facebook cards get their details from their
    own scrapers. `recipients` is kept for the existing call sites and is no longer consulted."""
    if not yad2_detail.is_enabled():
        return
    if listing.source != Source.YAD2 or listing.details_fetched_at is not None:
        return
    updates = await asyncio.to_thread(yad2_detail.fetch_updates, listing.url)
    if updates is None:
        return
    for column, value in updates.items():
        setattr(listing, column, value)
    listing.details_fetched_at = dt.datetime.now(dt.timezone.utc)
    session.commit()


async def _notify_new_matches(
    bot: Bot,
    session: Session,
    listing: Listing,
    *,
    only_telegram_user_id: str | None = None,
) -> tuple[int, int, set[int]]:
    """Send 'new match' notifications for one listing to every currently-matching active filter
    that hasn't already received one. Covers both genuinely new listings and existing listings
    that now match a filter they didn't before (e.g. a price drop brought them into budget).
    Returns (matched_count, sent_count, newly_notified_user_ids) — the third element lets a
    price-change run tell run_notifications' own _notify_price_change call apart a user who's
    brand new to this listing (just sent THIS notification, moments ago, in this exact call) from
    one who was genuinely already told about it on an earlier run (see that function's own
    docstring for the real double-card bug this fixes).

    `only_telegram_user_id`: see run_notifications' own docstring — when set, every OTHER user is
    silently skipped (never marked as notified, so they still get the real notification once this
    restriction is lifted on a later run).

    2026-09-27 through 2026-09-30: this used to cap WhatsApp to one send per user per run (a
    shared `whatsapp_sent_user_ids` set threaded through every call in the run), added after a
    real report that a broad filter flooded WhatsApp with one push per matching listing at once.
    Real owner report the other direction, 2026-09-30: the cap's own claim that the rest "get
    picked up on the next run instead" was false whenever the SAME user also had Telegram linked —
    Telegram sends uncapped and immediately writes the shared, channel-agnostic
    SentNotification(reason=NEW) row for every matching listing in this run, which is exactly the
    row `_already_notified` checks to decide whether a listing is even reconsidered on a future
    run. A user with both channels linked (the common case) never got a "next run" for the
    listings WhatsApp skipped — they were silently dropped from WhatsApp forever, not deferred.
    Explicit owner call: WhatsApp should be a full notification channel exactly like Telegram and
    the website, not a throttled one — cap removed, every match now sends on every eligible
    channel."""
    matched = 0
    sent = 0
    newly_notified_user_ids: set[int] = set()
    to_notify: list[tuple[Filter, User]] = []
    # Circuit breaker (todira_common/whatsapp_guard.py): fail-closed, read once per listing.
    wa_paused = whatsapp_guard.is_paused(session)
    for filter_row in _candidate_filters(session, listing):
        if not evaluate(filter_row, listing).matched:
            continue
        matched += 1
        if _already_notified(session, filter_row.user_id, listing.id, NotificationReason.NEW):
            continue
        user = session.get(User, filter_row.user_id)
        if user is None:
            continue
        if only_telegram_user_id is not None and str(user.telegram_user_id) != str(
            only_telegram_user_id
        ):
            continue
        if user.telegram_user_id is None and (wa_paused or not _whatsapp_eligible(user)):
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
            user_lang = user.language or DEFAULT_LANG
            caption = format_caption(
                listing,
                has_access=_has_access_for(user),
                upgrade_url=f"{WEBSITE_URL}/upgrade?{signed_login_query(user.telegram_user_id)}",
                view_url=f"{WEBSITE_URL}/apartments?{signed_login_query(user.telegram_user_id)}&listing={listing.id}",
                lang=user_lang,
                access_state=_access_state_for(user),
            )
            if await send_listing_card(bot, user.telegram_user_id, listing, caption, user_lang):
                sent_on_any_channel = True
            await asyncio.sleep(SEND_DELAY_SECONDS)
        if not wa_paused and _whatsapp_eligible(user):
            # asyncio.to_thread: _send_whatsapp_match_message downloads/composites a real photo and
            # makes HTTP calls — genuinely blocking work that must never run directly on this
            # event loop, same reasoning as send_listing_card's own asyncio.to_thread calls around
            # _build_collage_sync.
            if await asyncio.to_thread(_send_whatsapp_match_message, user, listing):
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
            newly_notified_user_ids.add(filter_row.user_id)
    return matched, sent, newly_notified_user_ids


async def _notify_price_change(
    bot: Bot,
    session: Session,
    listing: Listing,
    old_price: int,
    *,
    only_telegram_user_id: str | None = None,
    exclude_user_ids: set[int] = frozenset(),
) -> int:
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
    approved template to point at; revisit then.

    `only_telegram_user_id`: see run_notifications' own docstring.

    `exclude_user_ids` (2026-09-25 real bug fix): run_notifications calls _notify_new_matches for
    this SAME listing right before this function, in the very same price-change-event iteration —
    a user whose filter didn't match the OLD price but does the NEW one gets a genuine 'new match'
    notification there, and its own SentNotification(reason=NEW) row is committed immediately, in
    that same call. The query below (SELECT user_id WHERE reason=NEW) would then find that
    brand-new row an instant later and treat them as "previously notified," sending them a SECOND,
    redundant 'price dropped!' card for a listing they were only just told about for the first
    time — confirmed live via a real code-review pass, exactly matching the two-cards-in-one-run
    report. Callers pass the newly_notified_user_ids that same _notify_new_matches call just
    returned so this function can tell the two cases apart."""
    sent = 0
    reason = (
        NotificationReason.PRICE_DROP
        if old_price > listing.price
        else NotificationReason.PRICE_INCREASE
    )
    previously_notified_user_ids = [
        user_id
        for user_id in session.scalars(
            select(SentNotification.user_id).where(
                SentNotification.listing_id == listing.id,
                SentNotification.reason == NotificationReason.NEW,
            )
        )
        if user_id not in exclude_user_ids
    ]
    to_notify: list[User] = []
    for user_id in previously_notified_user_ids:
        if _already_notified(session, user_id, listing.id, reason):
            continue
        user = session.get(User, user_id)
        if user is None or not user.is_active or not user.notifications_enabled:
            continue
        if only_telegram_user_id is not None and str(user.telegram_user_id) != str(
            only_telegram_user_id
        ):
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
        user_lang = user.language or DEFAULT_LANG
        caption = format_caption(
            listing,
            has_access=_has_access_for(user),
            price_change_from=old_price,
            upgrade_url=f"{WEBSITE_URL}/upgrade?{signed_login_query(user.telegram_user_id)}",
            view_url=f"{WEBSITE_URL}/apartments?{signed_login_query(user.telegram_user_id)}&listing={listing.id}",
            lang=user_lang,
            access_state=_access_state_for(user),
        )
        if await send_listing_card(bot, user.telegram_user_id, listing, caption, user_lang):
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
    *,
    only_telegram_user_id: str | None = None,
) -> dict[str, int]:
    """`new_listings`: rows inserted for the first time this run. `price_change_events`:
    (listing, old_price) pairs for existing listings whose price just changed (either direction).
    Returns a summary dict for main.py's run-summary log line.

    2026-09-13: `only_telegram_user_id`, when set, restricts every actual send to that ONE
    Telegram user — every other otherwise-matching user is silently skipped this run (not marked
    as notified, so they get the real notification on a later run once this restriction is
    lifted). Added specifically for resuming the scraper after a long pause (see main.py's
    NOTIFICATIONS_SUSPENDED docstring for the fuller catch-up-burst reasoning this complements):
    the owner explicitly wants to keep verifying the pipeline actually works end to end (real
    Telegram pushes landing on their own phone) WITHOUT flooding every other real user during the
    catch-up period — a middle ground between "suspend all notifications" and "notify everyone,
    backlog and all." `matched`/`notifications_sent` etc. in the returned summary still count only
    the sends that actually went out (i.e. just this one user's), same contract as always."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    matched_count = 0
    new_sent_count = 0
    price_change_sent_count = 0

    async with Bot(token=token) as bot:
        for listing in new_listings:
            m, s, _newly_notified = await _notify_new_matches(
                bot,
                session,
                listing,
                only_telegram_user_id=only_telegram_user_id,
            )
            matched_count += m
            new_sent_count += s
        for listing, old_price in price_change_events:
            # a price change can also newly qualify filters that were previously priced out
            m, s, newly_notified = await _notify_new_matches(
                bot,
                session,
                listing,
                only_telegram_user_id=only_telegram_user_id,
            )
            matched_count += m
            new_sent_count += s
            price_change_sent_count += await _notify_price_change(
                bot,
                session,
                listing,
                old_price,
                only_telegram_user_id=only_telegram_user_id,
                exclude_user_ids=newly_notified,
            )

    return {
        "matched": matched_count,
        "notifications_sent": new_sent_count,
        "price_change_notifications_sent": price_change_sent_count,
    }
