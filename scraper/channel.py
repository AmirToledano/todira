"""Posts to the public Telegram channel t.me/todira_dirot (2026-10-31, owner: "post whatever you like there, don't make me
deal with it").

- Once: a welcome post, pinned, saying what the channel is.
- Every morning (POST_FROM_HOUR until POST_UNTIL_HOUR, Israel): an album of up to PICKS rentals first seen in the last
  24 hours whose price is lowest against flats with the same room count in the same city (median of the last 30 days,
  at least MIN_PEERS of them), private owners first, at most MAX_PER_CITY a city. Each links to the flat's public page
  on the site (todira_common.share), never to the original ad.
- Fridays: the 3-room median of the biggest cities, each linked to its city page (/rent/<city>).

Every post ends with a link into the bot. The owner dislikes the bot's @name, so it is never written out: the link is on
the words. Main scraper only; each post is remembered in app_flags so a later run the same day does not post again.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import html
import json
import logging
import os
import statistics
from collections import defaultdict
from urllib.parse import quote

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from telegram import Bot, InputMediaPhoto
from telegram.constants import ParseMode

from todira_common import alert_hours, app_flags, share
from todira_common.cards import _first_downloadable_photo_jpeg_bytes  # the cards' own tried photo download
from todira_common.models import Listing
from todira_common.non_home import not_non_home_sql

logger = logging.getLogger(__name__)

CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "@todira_dirot")
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://todira.app").rstrip("/")
BOT_URL = "https://t.me/AmirDirotBot?start=channel"
POST_FROM_HOUR = 9
POST_UNTIL_HOUR = 12
PICKS = 5
MAX_PER_CITY = 2
MIN_PEERS = 10
MIN_BELOW = 0.05
MAX_BELOW = 0.40  # cheaper than this is more often a wrong price (a room, a deposit) than a bargain
NEW_WINDOW = dt.timedelta(hours=24)
PEER_WINDOW = dt.timedelta(days=30)
WEEKLY_CITIES = 10
FRIDAY = 4
_FLAG = "telegram_channel_posts"  # JSON: {"intro": date, "daily": date, "weekly": date}


def _rentals(now: dt.datetime, since: dt.timedelta):
    return [
        Listing.deal_type == "rent",
        Listing.duplicate_of_id.is_(None),
        Listing.price.between(1000, 40000),
        Listing.city.is_not(None),
        or_(Listing.property_type.is_(None), Listing.property_type != "shared_room"),
        not_non_home_sql(Listing),
        Listing.first_seen_at >= now - since,
    ]


def _money(value) -> str:
    return f"₪{int(value):,}"


def _rooms(value) -> str:
    number = float(value)
    return "חדר אחד" if number == 1 else f"{number:g} חדרים"


def _link(url: str, text: str) -> str:
    return f'<a href="{html.escape(url)}">{html.escape(text, quote=False)}</a>'


def _bot_line() -> str:
    return _link(BOT_URL, "רוצים לקבל דירות לפי החיפוש שלכם ברגע שהן עולות? לחצו כאן")


def pick_flats(session: Session, now: dt.datetime) -> list[tuple[Listing, float]]:
    """(listing, how much cheaper than its peers, 0.05 to 0.40), best first, for the morning post. Photos not checked."""
    medians: dict[tuple[str, float], list[int]] = defaultdict(list)
    for city, rooms, price in session.execute(
        select(Listing.city, Listing.rooms, Listing.price).where(
            *_rentals(now, PEER_WINDOW), Listing.rooms.is_not(None)
        )
    ):
        medians[(city, float(rooms))].append(price)
    candidates = []
    for listing in session.scalars(
        select(Listing).where(
            *_rentals(now, NEW_WINDOW), Listing.rooms.is_not(None), Listing.is_delisted.is_(False),
            Listing.image_urls != [],
        )
    ):
        peers = medians.get((listing.city, float(listing.rooms)), [])
        if len(peers) < MIN_PEERS:
            continue
        below = 1 - listing.price / statistics.median(peers)
        if MIN_BELOW <= below <= MAX_BELOW:
            candidates.append((listing, below))
    candidates.sort(key=lambda pair: (bool(pair[0].is_broker_listing), -pair[1], -pair[0].id))
    return candidates


def daily_caption(picks: list[tuple[Listing, float]]) -> str:
    lines = ["<b>הדירות הכי משתלמות שעלו ב־24 השעות האחרונות</b>", ""]
    for number, (listing, below) in enumerate(picks, 1):
        place = listing.city + (f", {listing.neighborhood}" if listing.neighborhood and listing.neighborhood != "שאר העיר" else "")
        facts = [_rooms(listing.rooms)]
        if listing.size_sqm:
            facts.append(f'{listing.size_sqm} מ"ר')
        facts.append(f"{_money(listing.price)} לחודש")
        lines.append(f"{number}. {_link(WEBSITE_URL + share.share_path(listing.id), place)}")
        lines.append(f"{', '.join(facts)}. {round(below * 100)}% פחות מדירות דומות בעיר.")
        lines.append("")
    lines.append(_bot_line())
    return "\n".join(lines)


def weekly_text(session: Session, now: dt.datetime) -> str | None:
    prices: dict[str, list[int]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    for city, rooms, price in session.execute(
        select(Listing.city, Listing.rooms, Listing.price).where(*_rentals(now, PEER_WINDOW))
    ):
        counts[city] += 1
        if rooms is not None and 3 <= rooms <= 3.5:
            prices[city].append(price)
    cities = [city for city in sorted(counts, key=lambda c: (-counts[c], c)) if len(prices[city]) >= MIN_PEERS]
    if not cities:
        return None
    lines = ["<b>כמה עולה היום לשכור דירת 3 חדרים</b>", "המחיר האמצעי לפי הדירות שעלו ב־30 הימים האחרונים:", ""]
    for city in cities[:WEEKLY_CITIES]:
        median = int(round(statistics.median(prices[city]), -1))
        lines.append(f"{_link(f'{WEBSITE_URL}/rent/{quote(city)}', city)}: {_money(median)}")
    lines += ["", _link(f"{WEBSITE_URL}/rent", "כל הערים, לפי מספר חדרים ושכונות"), _bot_line()]
    return "\n".join(lines)


INTRO_TEXT = (
    "<b>ברוכים הבאים לערוץ של טודירה</b>\n\n"
    "כל בוקר נעלה לכאן את הדירות להשכרה הכי משתלמות שעלו ביממה האחרונה, ובימי שישי את המחירים בערים הגדולות.\n\n"
    "טודירה סורקת את שוק הדירות כל הזמן, ושולחת לכם הודעה בטלגרם ברגע שעולה דירה שמתאימה לחיפוש שלכם.\n\n"
)


async def _post(bot: Bot, kind: str, session: Session, now: dt.datetime) -> bool:
    if kind == "intro":
        message = await bot.send_message(
            CHANNEL, INTRO_TEXT + _bot_line(), parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )
        try:
            await bot.pin_chat_message(CHANNEL, message.message_id, disable_notification=True)
        except Exception:
            logger.warning("channel: could not pin the welcome post", exc_info=True)
        return True
    if kind == "weekly":
        text = weekly_text(session, now)
        if text is None:
            return False
        await bot.send_message(CHANNEL, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        return True
    picks: list[tuple[Listing, float]] = []
    photos: list[bytes] = []
    per_city: dict[str, int] = defaultdict(int)
    for listing, below in pick_flats(session, now):
        if len(picks) == PICKS:
            break
        if per_city[listing.city] >= MAX_PER_CITY:
            continue
        photo = await asyncio.to_thread(_first_downloadable_photo_jpeg_bytes, listing.image_urls)
        if photo is None:
            continue
        picks.append((listing, below))
        photos.append(photo)
        per_city[listing.city] += 1
    if not picks:
        return False
    caption = daily_caption(picks)
    if len(picks) == 1:
        await bot.send_photo(CHANNEL, photos[0], caption=caption, parse_mode=ParseMode.HTML)
    else:
        media = [InputMediaPhoto(photo) for photo in photos]
        media[0] = InputMediaPhoto(photos[0], caption=caption, parse_mode=ParseMode.HTML)
        await bot.send_media_group(CHANNEL, media)
    return True


def due_posts(state: dict, now: dt.datetime) -> list[str]:
    local = alert_hours.israel_now(now)
    today = local.date().isoformat()
    due = [] if state.get("intro") else ["intro"]
    if POST_FROM_HOUR <= local.hour < POST_UNTIL_HOUR:
        if state.get("daily") != today:
            due.append("daily")
        if local.weekday() == FRIDAY and state.get("weekly") != today:
            due.append("weekly")
    return due


async def _run(session: Session, now: dt.datetime) -> list[str]:
    state = json.loads(app_flags.get_flag(session, _FLAG) or "{}")
    due = due_posts(state, now)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not due or not token:
        return []
    posted = []
    bot = Bot(token=token)
    await bot.initialize()
    try:
        for kind in due:
            try:
                if await _post(bot, kind, session, now):
                    posted.append(kind)
                    state[kind] = alert_hours.israel_now(now).date().isoformat()
                    app_flags.set_flag(session, _FLAG, json.dumps(state))
            except Exception:
                session.rollback()
                logger.exception("channel: the %s post failed", kind)
    finally:
        await bot.shutdown()
    return posted


def run_channel_posts(session: Session, now: dt.datetime | None = None) -> dict[str, str]:
    posted = asyncio.run(_run(session, now or dt.datetime.now(dt.timezone.utc)))
    return {"channel_posts": ",".join(posted)}
