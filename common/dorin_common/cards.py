"""Telegram card rendering for a `Listing` — shared by the scraper's notifier (new-match push)
and the bot's /apartments and /liked handlers (on-demand listing), so both surfaces render a
listing identically. See plan Section 4 for the card format this implements.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from dorin_common.models import Listing

CAPTION_LIMIT = 1024

_AMENITY_EMOJI = (
    ("has_parking", "🅿️"),
    ("has_elevator", "🛗"),
    ("has_balcony", "🌳"),
    ("pets_allowed", "🐾"),
)


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
