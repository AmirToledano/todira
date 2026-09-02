"""Telegram card rendering for a `Listing` — shared by the scraper's notifier (new-match push)
and the bot's /apartments and /liked handlers (on-demand listing), so both surfaces render a
listing identically. See plan Section 4 for the card format this implements.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError

from dorin_common.models import Listing

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024

# A listing with zero real photos gets a cute cartoon dachshund instead (2026-09-02 request) — see
# scripts/generate_dachshund_art.py for how these were drawn, and website/templates/
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
        lines.append(f"💰 {listing.price:,} ₪")
    if listing.move_in_date is not None:
        lines.append(f"📅 כניסה: {listing.move_in_date.isoformat()}")
    if amenities:
        lines.append(amenities)
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
        lines.append(f"💰 {listing.price:,} ₪")
    if listing.move_in_date is not None:
        lines.append(f"📅 כניסה: {listing.move_in_date.isoformat()}")
    if amenities:
        lines.append(amenities)
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


# Telegram's own sendMediaGroup limit — irrelevant in practice (Yad2 listings rarely carry this
# many photos), but the API call itself rejects a longer list outright.
MAX_MEDIA_GROUP_PHOTOS = 10


async def send_listing_card(bot: Bot, chat_id: int, listing: Listing, caption: str) -> bool:
    """Sends one listing to one Telegram chat — the ONE place this project actually puts a
    listing on screen, used by the scraper's notifier and every bot handler that shows a listing,
    so real photos (added 2026-09-02 — see scraper/normalize.py's enrich_from_detail) render
    identically everywhere instead of each call site reinventing send_photo/send_message.

    Real photos when the listing has them (a media group for 2+, a single photo for exactly 1);
    when it has none, a cute cartoon dachshund photo instead of a bare text message (2026-09-02
    request — see _dachshund_photo_path above). Telegram's sendMediaGroup can't carry an inline
    keyboard at all (a real API limitation, not a bug here), so for 2+ photos the ❤️/🙈/🎉 action
    buttons go out as a short separate follow-up message instead of silently disappearing.

    Retries ONCE on Telegram's own flood-control response (RetryAfter) — found live 2026-09-02: a
    real backfill run matched 17 listings to one user in a burst, and media-group sends (2 Telegram
    API calls each — the group itself, then the follow-up keyboard message) hit Telegram's per-chat
    rate limit after a handful of sends, silently dropping 4 of the 17 real match notifications
    with no retry at all. A single wait-and-retry (honoring Telegram's own `retry_after` seconds)
    is enough for a burst that size; still gives up and returns False if the second attempt also
    fails, exactly like any other permanent failure (blocked bot, dead chat, bad photo URL)."""
    keyboard = listing_keyboard(listing.id)
    images = listing.image_urls[:MAX_MEDIA_GROUP_PHOTOS] if listing.image_urls else []

    async def _do_send() -> None:
        if len(images) >= 2:
            media = [InputMediaPhoto(images[0], caption=caption, parse_mode=ParseMode.HTML)] + [
                InputMediaPhoto(url) for url in images[1:]
            ]
            await bot.send_media_group(chat_id=chat_id, media=media)
            # Telegram renders a message containing ONLY 1-3 emoji as one giant "jumbo" emoji with
            # no normal bubble background - real words alongside it avoid that (found live
            # 2026-09-02: a bare "⬆️" was taking over the whole screen).
            await bot.send_message(chat_id=chat_id, text="⬆️ הדירה למעלה", reply_markup=keyboard)
        elif len(images) == 1:
            await bot.send_photo(
                chat_id=chat_id,
                photo=images[0],
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
