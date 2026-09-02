"""Telegram card rendering for a `Listing` — shared by the scraper's notifier (new-match push)
and the bot's /apartments and /liked handlers (on-demand listing), so both surfaces render a
listing identically. See plan Section 4 for the card format this implements.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError

from dorin_common.models import Listing

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024

# A line made up ONLY of digits/currency/emoji (no Hebrew letters) has no strong-direction
# character at all, so bidi-aware renderers (confirmed live in Telegram, 2026-09-02) fall back to
# LTR for that one line and left-align it — "💰 7,800 ₪" and a bare amenity-emoji row rendered on
# the LEFT edge while every other line (which starts with real Hebrew text) sat correctly on the
# right. A leading U+200F (Right-to-Left Mark, invisible, zero display width) forces RTL for that
# line without changing anything visible; harmless to add to a line that was already RTL.
_RLM = "\u200f"

# A listing with zero real photos gets a cute cartoon dachshund instead (2026-09-02 request) — see
# scripts/fetch_dachshund_art.py for where this art comes from (a real, public-domain internet
# illustration, recolored into 6 palettes — not hand-drawn here), and website/templates/
# _listing_card.html for the same treatment on the website. Picked deterministically from the
# listing id (not random) so a given listing shows the same dog everywhere/every time.
_DACHSHUND_DIR = Path(__file__).resolve().parent / "assets" / "dachshunds"
_DACHSHUND_PALETTES = ("chocolate", "golden", "cream", "black_tan", "reddish", "silver")
_NO_PHOTOS_SUFFIX_HE = "\n\n🐶 <i>דירה זו עלתה ללא תמונות, אבל הנה נקניקיה חמודה בשבילכם</i>"


def _dachshund_photo_path(listing_id: int) -> Path:
    name = _DACHSHUND_PALETTES[listing_id % len(_DACHSHUND_PALETTES)]
    return _DACHSHUND_DIR / f"{name}.png"

_AMENITY_EMOJI = (
    ("has_parking", "🅿️"),
    ("has_elevator", "🛗"),
    ("has_balcony", "🌳"),
    ("pets_allowed", "🐾"),
)

# A compact, readable "מה יש בנכס" line — the emoji row above is a quick glance, this is the
# itemized list the user asked for (2026-09-02), modeled after the reference bot's own "פיצ'רים:"
# line. Limited to fields this project actually models today (see dorin_common/models.py) — no
# air conditioning/boiler/accessibility columns exist yet, even though Yad2's detail-page data now
# carries them (see scraper/normalize.py's enrich_from_detail) - a real follow-up, not done here.
_FEATURE_LABELS = (
    ("has_parking", "חניה"),
    ("has_elevator", "מעלית"),
    ("has_balcony", "מרפסת"),
    ("pets_allowed", "חיות מחמד"),
    ("is_renovated", "משופצת"),
    ("is_roommate_friendly", "מתאימה לשותפים"),
)


def _feature_list(listing: Listing) -> list[str]:
    labels = [label for attr, label in _FEATURE_LABELS if getattr(listing, attr) is True]
    if listing.safe_room_type in ("safe_room", "building_shelter"):
        labels.append('ממ"ד')
    if listing.furniture == "furnished":
        labels.append("מרוהטת")
    return labels


def format_caption(listing: Listing, *, price_drop_from: int | None = None) -> str:
    """`price_drop_from`: when set, prepends a "📉 ירידת מחיר!" header showing the previous
    price — used for the price-drop re-notification path (see notifier.py), left unset for a
    normal new-match card."""
    amenities = " ".join(
        emoji for attr, emoji in _AMENITY_EMOJI if getattr(listing, attr) is True
    )
    if listing.safe_room_type in ("safe_room", "building_shelter"):
        amenities = f"{amenities} 🛡️".strip()

    floor_line = ""
    if listing.floor is not None:
        floor_line = f" · קומה {listing.floor}"
        if listing.floor_total is not None:
            floor_line += f" מתוך {listing.floor_total}"

    size_part = f" · {listing.size_sqm} מ\"ר" if listing.size_sqm else ""
    lines = [f"🏠 <b>{listing.rooms or '?'} חדרים</b>{size_part}{floor_line}"]

    if listing.price is not None:
        lines.append(f"{_RLM}💰 {listing.price:,} ₪")
    if listing.move_in_date is not None:
        lines.append(f"📅 כניסה: {listing.move_in_date.isoformat()}")
    if amenities:
        lines.append(f"{_RLM}{amenities}")
    location = ", ".join(p for p in (listing.neighborhood, listing.city) if p)
    if location:
        lines.append(f"📍 {location}")

    features = _feature_list(listing)
    if features:
        lines.append(f"<i>🔑 פיצ'רים: {', '.join(features)}</i>")

    body = "\n".join(lines)
    header = ""
    if price_drop_from is not None:
        header = f"📉 <b>ירידת מחיר!</b> (היה {price_drop_from:,} ₪)\n\n"
    footer = f'\n\n🔗 <a href="{listing.url}">לצפייה במודעה המלאה</a>\n🏷️ {listing.source}'
    remaining = CAPTION_LIMIT - len(header) - len(body) - len(footer)
    description = (listing.description or "").strip()
    if description and remaining > 20:
        if len(description) > remaining:
            description = description[: remaining - 1] + "…"
        body += f"\n\n{description}"

    return (header + body + footer)[:CAPTION_LIMIT]


WHATSAPP_MESSAGE_LIMIT = 4096


def format_caption_whatsapp(listing: Listing, *, price_drop_from: int | None = None) -> str:
    """Same content as format_caption, but WhatsApp's own markdown (*bold*, no HTML tags — the
    Cloud API's text messages don't render HTML) and no inline keyboard equivalent; the listing
    URL at the end is the only action available (WhatsApp's like/hide/found buttons would need
    interactive "reply button" messages, a separate message type — not built yet, plain text
    with a link is the MVP)."""
    amenities = " ".join(
        emoji for attr, emoji in _AMENITY_EMOJI if getattr(listing, attr) is True
    )
    if listing.safe_room_type in ("safe_room", "building_shelter"):
        amenities = f"{amenities} 🛡️".strip()

    floor_line = ""
    if listing.floor is not None:
        floor_line = f" · קומה {listing.floor}"
        if listing.floor_total is not None:
            floor_line += f" מתוך {listing.floor_total}"

    size_part = f" · {listing.size_sqm} מ\"ר" if listing.size_sqm else ""
    lines = [f"🏠 *{listing.rooms or '?'} חדרים*{size_part}{floor_line}"]

    if listing.price is not None:
        lines.append(f"{_RLM}💰 {listing.price:,} ₪")
    if listing.move_in_date is not None:
        lines.append(f"📅 כניסה: {listing.move_in_date.isoformat()}")
    if amenities:
        lines.append(f"{_RLM}{amenities}")
    location = ", ".join(p for p in (listing.neighborhood, listing.city) if p)
    if location:
        lines.append(f"📍 {location}")

    features = _feature_list(listing)
    if features:
        lines.append(f"_🔑 פיצ'רים: {', '.join(features)}_")

    body = "\n".join(lines)
    header = ""
    if price_drop_from is not None:
        header = f"📉 *ירידת מחיר!* (היה {price_drop_from:,} ₪)\n\n"
    footer = f"\n\n🔗 {listing.url}\n🏷️ {listing.source}"
    remaining = WHATSAPP_MESSAGE_LIMIT - len(header) - len(body) - len(footer)
    description = (listing.description or "").strip()
    if description and remaining > 20:
        if len(description) > remaining:
            description = description[: remaining - 1] + "…"
        body += f"\n\n{description}"

    return (header + body + footer)[:WHATSAPP_MESSAGE_LIMIT]


async def send_listing_card(bot: Bot, chat_id: int, listing: Listing, caption: str) -> bool:
    """Sends one listing to one Telegram chat — the ONE place this project actually puts a
    listing on screen, used by the scraper's notifier and every bot handler that shows a listing,
    so real photos (added 2026-09-02 — see scraper/normalize.py's enrich_from_detail) render
    identically everywhere instead of each call site reinventing send_photo/send_message.

    ONE message per listing: the first real photo (or the dachshund fallback — see
    _dachshund_photo_path above) with the caption and the ❤️/🙈/🎉 keyboard all on it via a plain
    send_photo. Deliberately NOT a multi-photo sendMediaGroup gallery anymore (2026-09-02, real
    user report + a direct ask to match the reference bot dorin.app's own cleaner single-message
    style): sendMediaGroup can't carry an inline keyboard at all, so showing 2+ photos meant a
    second, separate "⬆️ הדירה למעלה" message just to carry the buttons — confusing once several
    listings arrive in a burst (Telegram's own per-chat rate limit spaces the sends out, so by the
    time the keyboard message lands it's no longer obviously "the one right above"). The listing's
    other photos aren't lost — the caption's own "🔗 לצפייה במודעה המלאה" link already goes to the
    full Yad2 listing, where all of them are visible.

    Retries ONCE on Telegram's own flood-control response (RetryAfter) — found live 2026-09-02: a
    real backfill run matched 17 listings to one user in a burst and hit Telegram's per-chat rate
    limit partway through, silently dropping several real match notifications with no retry at
    all. A single wait-and-retry (honoring Telegram's own `retry_after` seconds) is enough for a
    burst that size; still gives up and returns False if the second attempt also fails, exactly
    like any other permanent failure (blocked bot, dead chat, bad photo URL)."""
    keyboard = listing_keyboard(listing.id)
    image_url = listing.image_urls[0] if listing.image_urls else None

    async def _do_send() -> None:
        if image_url is not None:
            await bot.send_photo(
                chat_id=chat_id,
                photo=image_url,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        else:
            no_photo_caption = (caption + _NO_PHOTOS_SUFFIX_HE)[:CAPTION_LIMIT]
            await bot.send_photo(
                chat_id=chat_id,
                photo=_dachshund_photo_path(listing.id),
                caption=no_photo_caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )

    for attempt in range(2):
        try:
            await _do_send()
            return True
        except RetryAfter as exc:
            if attempt == 0:
                logger.warning(
                    "Hit Telegram flood control sending listing %s to chat %s — retrying in %ss",
                    listing.id,
                    chat_id,
                    exc.retry_after,
                )
                await asyncio.sleep(exc.retry_after + 0.5)
                continue
            logger.exception(
                "Still flood-limited after one retry sending listing %s to chat %s",
                listing.id,
                chat_id,
            )
            return False
        except TelegramError:
            logger.exception(
                "Failed to send listing card to chat %s for listing %s", chat_id, listing.id
            )
            return False
    return False


def listing_keyboard(listing_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("❤️ שמור", callback_data=f"like:{listing_id}"),
                InlineKeyboardButton("🙈 הסתר", callback_data=f"hide:{listing_id}"),
                InlineKeyboardButton("🎉 מצאתי דירה!", callback_data=f"found:{listing_id}"),
            ]
        ]
    )
