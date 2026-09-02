"""Telegram card rendering for a `Listing` — shared by the scraper's notifier (new-match push)
and the bot's /apartments and /liked handlers (on-demand listing), so both surfaces render a
listing identically. See plan Section 4 for the card format this implements.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Callable

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError

from dorin_common.models import Listing

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024

# A listing with zero real photos gets a real photo of Todi — the user's own dachshund — instead
# (2026-09-02 request; briefly a CC0 cartoon illustration before that, see PROJECT_STATE.md for
# that history). 27 real photos, background (and any touching person) automatically removed —
# see scripts/prepare_todi_photos.py — curated from 50 submitted, picked deterministically from
# the listing id (not random) so a given listing shows the same photo everywhere/every time. Same
# treatment on the website — see website/templates/_listing_card.html.
_DACHSHUND_DIR = Path(__file__).resolve().parent / "assets" / "dachshunds"
_TODI_PHOTO_COUNT = 27
_NO_PHOTOS_SUFFIX_HE = "\n\n🐶 <i>דירה זו עלתה ללא תמונות, אבל הנה טודי בשבילכם</i>"


def _dachshund_photo_path(listing_id: int) -> Path:
    n = (listing_id % _TODI_PHOTO_COUNT) + 1
    return _DACHSHUND_DIR / f"todi_{n:02d}.png"


_DEAL_TYPE_LABELS = {"rent": "שכירות", "sale": "מכירה", "sublet": "סאבלט"}

# A compact, readable "מה יש בנכס" list — modeled after the reference bot's own "פיצ'רים:" line
# (2026-09-02), then folded into a single "|"-separated line as the sole amenity display (a
# separate emoji-only row used to sit above this one; dropped 2026-09-02 as redundant once every
# field here already carries its own label — see format_caption's docstring). Limited to fields
# this project actually models today (see dorin_common/models.py) — no air conditioning/boiler/
# accessibility columns exist yet, even though Yad2's detail-page data now carries them (see
# scraper/normalize.py's enrich_from_detail) - a real follow-up, not done here.
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


def _build_body_lines(listing: Listing) -> list[str]:
    """The field order/labels a real user asked for directly (2026-09-02, comparing screenshots
    against the reference bot dorin.app): deal type (+ "תיווך" when broker-listed) first, then
    location before anything else ("אני חושב שהמיקום צריך להיות ראשון"), then price/rooms/size/
    floor/move-in — each its own labeled line instead of the old single combined "X חדרים · Y מ"ר
    · קומה Z" line, deliberately using the SAME emoji the website's own card meta-row already uses
    for rooms/floor/size (🛏️/🏢/📐 — see website/templates/_listing_card.html) so the two surfaces
    read consistently. Currency is "ש"ח" (written form), not the ₪ sign, per the same request.

    Every line here now starts with a real Hebrew label word, which — as a side effect — also
    fully resolves the RTL-alignment bidi bug the old bare "💰 7,800 ₪"/emoji-only amenity row
    used to hit (a line with no strong-direction character fell back to LTR and rendered flush
    left in Telegram; see PROJECT_STATE.md). The explicit U+200F RLM workaround that used to guard
    against that is gone — no longer needed now that every line carries Hebrew text of its own."""
    lines = []

    deal_label = _DEAL_TYPE_LABELS.get(listing.deal_type, listing.deal_type)
    deal_line = f"🏠 {deal_label}"
    if listing.is_broker_listing:
        deal_line += " · תיווך"
    lines.append(deal_line)

    location = ", ".join(p for p in (listing.city, listing.neighborhood, listing.street) if p)
    if location:
        lines.append(f"📍 מיקום: {location}")

    if listing.price is not None:
        lines.append(f'💰 מחיר: {listing.price:,} ש"ח')

    lines.append(f"🛏️ חדרים: {listing.rooms or '?'}")

    if listing.size_sqm:
        lines.append(f'📐 שטח: {listing.size_sqm} מ"ר')

    if listing.floor is not None:
        floor_line = f"🏢 קומה: {listing.floor}"
        if listing.floor_total is not None:
            floor_line += f" מתוך {listing.floor_total}"
        lines.append(floor_line)

    if listing.move_in_date is not None:
        lines.append(f"📅 כניסה: {listing.move_in_date.isoformat()}")

    return lines


def _price_change_header(price_change_from: int | None, current_price: int | None, *, bold: Callable[[str], str]) -> str:
    """`price_change_from`: the previous price, when this card is a re-notification because the
    price changed (either direction — a drop gets 📉, an increase gets 📈; see
    scraper/notifier.py). None (the normal case) means no header at all, matching a real request
    that a brand-new listing not get any price-change banner."""
    if price_change_from is None or current_price is None or price_change_from == current_price:
        return ""
    if price_change_from > current_price:
        emoji, label = "📉", "ירידת מחיר!"
    else:
        emoji, label = "📈", "עליית מחיר!"
    return f'{emoji} {bold(label)} (היה {price_change_from:,} ש"ח)\n\n'


def format_caption(listing: Listing, *, price_change_from: int | None = None) -> str:
    """`price_change_from`: see _price_change_header. Left unset for a normal new-match card."""
    lines = _build_body_lines(listing)
    features = _feature_list(listing)
    if features:
        lines.append(f"<i>🔑 פיצ'רים: {' | '.join(features)}</i>")

    body = "\n".join(lines)
    header = _price_change_header(price_change_from, listing.price, bold=lambda s: f"<b>{s}</b>")
    footer = f'\n\n🔗 <a href="{listing.url}">לצפייה במודעה המלאה</a>\n🏷️ {listing.source}'
    remaining = CAPTION_LIMIT - len(header) - len(body) - len(footer)
    description = (listing.description or "").strip()
    if description and remaining > 20:
        if len(description) > remaining:
            description = description[: remaining - 1] + "…"
        body += f"\n\n{description}"

    return (header + body + footer)[:CAPTION_LIMIT]


WHATSAPP_MESSAGE_LIMIT = 4096


def format_caption_whatsapp(listing: Listing, *, price_change_from: int | None = None) -> str:
    """Same content as format_caption, but WhatsApp's own markdown (*bold*, no HTML tags — the
    Cloud API's text messages don't render HTML) and no inline keyboard equivalent; the listing
    URL at the end is the only action available (WhatsApp's like/hide/found buttons would need
    interactive "reply button" messages, a separate message type — not built yet, plain text
    with a link is the MVP)."""
    lines = _build_body_lines(listing)
    features = _feature_list(listing)
    if features:
        lines.append(f"_🔑 פיצ'רים: {' | '.join(features)}_")

    body = "\n".join(lines)
    header = _price_change_header(price_change_from, listing.price, bold=lambda s: f"*{s}*")
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

    ONE message per listing: the first real photo (or the Todi fallback — see
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
