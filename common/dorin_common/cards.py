"""Telegram card rendering for a `Listing` — shared by the scraper's notifier (new-match push)
and the bot's /apartments and /liked handlers (on-demand listing), so both surfaces render a
listing identically. See plan Section 4 for the card format this implements.
"""
from __future__ import annotations

import asyncio
import html
import io
import logging
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import httpx
from PIL import Image
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError

from dorin_common.models import Listing

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024

# A 2+ real-photo listing gets ONE composite collage image instead of just its first photo — 2026-
# 09-03 request, matching the reference bot dorin.app's own style (a real user screenshot showed
# its cards leading with a photo grid, not a single image). Deliberately still ONE send_photo call
# with ONE image, not Telegram's sendMediaGroup — see send_listing_card's own docstring on why
# that was already rejected once (2026-09-02): it can't carry an inline keyboard, so 2+ photos
# meant a confusing second message just for the ❤️/🙈/🎉 buttons. A generated collage keeps the
# "one message, one photo, one keyboard" design while still showing more than one real photo — the
# website doesn't need this at all (website/templates/_listing_card.html already lets a visitor
# scroll/swipe between every real photo directly, no compositing needed there).
_COLLAGE_MAX_PHOTOS = 4
_COLLAGE_TILE_PX = 400
_COLLAGE_DOWNLOAD_TIMEOUT_S = 10.0


def _build_collage_sync(image_urls: list[str]) -> bytes | None:
    """Downloads up to _COLLAGE_MAX_PHOTOS listing photos and composites them into a single JPEG
    grid image (2 columns, as many rows as needed). Returns None on ANY failure — a bad photo URL,
    a timeout, a corrupt image — so the caller can fall back to sending just the first real photo
    as before; a collage is a nice-to-have, never something that should block a listing from being
    sent at all. Returns None outright for fewer than 2 usable photos (nothing to collage).

    Synchronous and blocking (real network downloads + CPU-bound image resizing) — callers MUST
    run this via asyncio.to_thread, never awaited directly on the event loop. See
    tests/test_bot_async_db_calls.py's module docstring for why: this project already hit, and
    fixed, the exact same class of bug for blocking DB calls (2026-08-31) — a bot with
    max_concurrent_updates=1 processing every update on one event loop means ANY blocking call
    made directly on it freezes every other user's interaction too, not just this one."""
    tiles: list[Image.Image] = []
    for url in image_urls[:_COLLAGE_MAX_PHOTOS]:
        try:
            response = httpx.get(url, timeout=_COLLAGE_DOWNLOAD_TIMEOUT_S)
            response.raise_for_status()
            photo = Image.open(io.BytesIO(response.content)).convert("RGB")
        except Exception:
            logger.warning("Skipping one collage photo that failed to download/decode: %s", url)
            continue
        # Center-crop to square first so tiles line up in a clean grid regardless of each source
        # photo's own aspect ratio, then resize every tile to the same fixed size.
        side = min(photo.size)
        left = (photo.width - side) // 2
        top = (photo.height - side) // 2
        photo = photo.crop((left, top, left + side, top + side)).resize(
            (_COLLAGE_TILE_PX, _COLLAGE_TILE_PX)
        )
        tiles.append(photo)

    if len(tiles) < 2:
        return None

    columns = 2
    rows = (len(tiles) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * _COLLAGE_TILE_PX, rows * _COLLAGE_TILE_PX), "white")
    for index, tile in enumerate(tiles):
        x = (index % columns) * _COLLAGE_TILE_PX
        y = (index // columns) * _COLLAGE_TILE_PX
        canvas.paste(tile, (x, y))

    buffer = io.BytesIO()
    canvas.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()

# A listing with zero real photos gets a single branded illustration instead — Todi as a detective
# (deerstalker hat), standing on a laptop pointing at a map of matching listings next to his happy
# owner, with real-estate UI icons (a "for rent" sign, a key, a floor plan, a bot, a calculator)
# floating around them. 2026-09-02 request, replacing the earlier flat-vector crowned-dachshund
# mascot (which itself replaced several earlier photo-based attempts — CC0 illustration, background
# /person removal, emoji-over-face, 18 AI-generated "nano banana" photos; see PROJECT_STATE.md for
# that full history) — the user supplied this specific illustration directly and asked for it by
# name, unlike every earlier round which was iterated on inside this session. Cropped from the
# original portrait-oriented image (896x1195) down to its lower ~60% (896x715, Todi/laptop/owner —
# the part that reads at small card size; the floating icon row above it wouldn't) to roughly match
# the card's own 4:3 cover aspect ratio; the original full image isn't kept in the repo, only this
# crop. A single static asset, not a rotating pool — same reasoning as the mascot it replaces: a
# designed illustration doesn't need per-listing variety the way a stand-in for a missing real
# photo would. Same treatment on the website — see website/templates/_listing_card.html.
_DACHSHUND_DIR = Path(__file__).resolve().parent / "assets" / "dachshunds"
_MASCOT_PATH = _DACHSHUND_DIR / "todi_detective.jpg"
# On the website (website/templates/_listing_card.html + .no-image-caption in style.css) this same
# notice is a full-width bold banner directly under the cover photo — impossible to miss. Telegram
# captions can't do background colors or font-size, so the closest equivalent is BOLD (not italic
# — italic reads as an aside, easy to skim past) and placed FIRST, before the listing's own details,
# instead of tacked on at the very end where a real user reported missing it entirely (2026-09-03).
_NO_PHOTOS_PREFIX_HE = "‏🕵️ <b>דירה זו עלתה ללא תמונות, אך שווה לפנות למפרסם ולבקש כמה!</b>\n\n"


def _dachshund_photo_path() -> Path:
    return _MASCOT_PATH


# 2026-09-03 rewrite: field order/labels/emphasis matching the reference bot dorin.app 1:1, per a
# real side-by-side comparison against its own screenshots. Deal-type/broker prefix, then location
# (city bold, street a clickable Google-Maps link on Telegram — see _google_maps_url), then price/
# rooms/size/floor/move-in each on its own BOLD-labeled line (previously plain labels; italicized
# features; ISO move-in dates; "ש"ח" currency — all superseded here), a per-feature-emoji list
# instead of a generic "🔑" line, and a 📝-prefixed description. The old deal-type line ("🏠
# שכירות"/"מכירה") is GONE — replaced by a bold "🏢תיווך"/"🏢סאבלט" prefix shown only when relevant
# (a plain rent or sale listing gets no prefix line at all; broker status is independent of deal
# type, so it takes priority over the sublet label if somehow both apply). The old "🏷️ {source}"
# footer line is also gone — a real request that Telegram/WhatsApp readers don't need to know which
# source site a listing came from (the website's own card still shows a source badge — see
# website/templates/_listing_card.html).
_FEATURE_EMOJI_LABELS = (
    ("has_parking", "🚗", "חניה"),
    ("has_elevator", "🛗", "מעלית"),
    ("has_balcony", "🌿", "מרפסת"),
    ("pets_allowed", "🐾", "חיות מחמד"),
    ("is_renovated", "✨", "משופצת"),
    ("is_roommate_friendly", "🤝", "מתאימה לשותפים"),
)


def _feature_list(listing: Listing) -> list[str]:
    """Each feature prefixed with its own emoji — the SAME ones the website's own amenity row
    uses (website/static/style.css's .amenity-row / _listing_card.html) for has_parking through
    furniture, so the two surfaces read consistently. is_roommate_friendly has no website
    equivalent to match (not shown there today) — 🤝 chosen fresh."""
    items = [
        f"{emoji}{label}" for attr, emoji, label in _FEATURE_EMOJI_LABELS if getattr(listing, attr) is True
    ]
    if listing.safe_room_type in ("safe_room", "building_shelter"):
        items.append('🛡️ממ"ד')
    if listing.furniture == "furnished":
        items.append("🛋️מרוהטת")
    return items


def _google_maps_url(listing: Listing) -> str | None:
    """A plain Google Maps search-URL — no API key needed, works for any address string. None
    when there's no street to point at (a bare city/neighborhood isn't precise enough to be worth
    a map link)."""
    if not listing.street:
        return None
    parts = [p for p in (listing.street, listing.neighborhood, listing.city) if p]
    return f"https://www.google.com/maps/search/?api=1&query={quote(', '.join(parts))}"


def _deal_type_prefix_word(listing: Listing) -> str | None:
    """"תיווך" (broker) takes priority over "סאבלט" (sublet) when both would somehow apply — a
    plain rent or sale listing gets None (no prefix line at all)."""
    if listing.is_broker_listing:
        return "תיווך"
    if listing.deal_type == "sublet":
        return "סאבלט"
    return None


def _build_body_lines(
    listing: Listing,
    *,
    bold: Callable[[str], str],
    street_link: Callable[[str, str], str],
    escape: Callable[[str], str],
) -> list[str]:
    """`bold` wraps label text in each platform's own emphasis syntax (<b> on Telegram, *asterisks*
    on WhatsApp). `street_link(text, url)` wraps the street name as a tappable link where the
    platform supports custom link text (Telegram); WhatsApp can't do that (its text messages only
    auto-link raw URLs, never custom anchor text) — its own caller passes an identity function and
    appends the raw maps URL as a separate line instead, see format_caption_whatsapp. `escape`
    is applied to every field that comes from the listing itself (city/neighborhood/street) rather
    than a hardcoded label — these are scraped from Yad2, not written by this project, so on
    Telegram (parse_mode=HTML) a city/street name that happens to contain `<`/`&`/`>` would
    otherwise either break the caption's HTML parsing or, worse, let scraped text inject an
    arbitrary tag into a message rendered with real formatting. WhatsApp's caller passes an
    identity function since its captions are plain text, not HTML."""
    lines = []

    prefix_word = _deal_type_prefix_word(listing)
    if prefix_word is not None:
        lines.append(f"🏢{bold(prefix_word)}")

    location_bits = []
    if listing.city:
        location_bits.append(bold(escape(listing.city)))
    if listing.neighborhood:
        location_bits.append(escape(listing.neighborhood))
    location = " - ".join(location_bits)
    if listing.street:
        street_display = escape(listing.street)
        maps_url = _google_maps_url(listing)
        street_text = street_link(street_display, maps_url) if maps_url else street_display
        location = f"{location} {street_text}" if location else street_text
    if location:
        lines.append(f"📍{location}")

    if listing.price is not None:
        lines.append(f"💰 {bold('מחיר:')} {listing.price:,}₪")

    lines.append(f"🛏️ {bold('חדרים:')} {listing.rooms or '?'}")

    if listing.size_sqm:
        lines.append(f'📐 {bold("שטח:")} {listing.size_sqm} מ"ר')

    if listing.floor is not None:
        floor_line = f"🏢 {bold('קומה:')} {listing.floor}"
        if listing.floor_total is not None:
            floor_line += f" מתוך {listing.floor_total}"
        lines.append(floor_line)

    if listing.move_in_date is not None:
        lines.append(f"📅 {bold('כניסה:')} {listing.move_in_date.strftime('%d.%m.%Y')}")

    features = _feature_list(listing)
    if features:
        features_label = bold("פיצ'רים:")
        lines.append("")  # a visual gap before the features line — a real request, 2026-09-03
        lines.append(f"🔑 {features_label} {' | '.join(features)}")

    # Every line gets its OWN leading RTL mark, not just the caption as a whole — a real user
    # report (screenshot) showed the block drifting further left line by line. A single mark up
    # front (the previous fix, 2026-09-03) only anchors the first line; each of these lines still
    # starts with an emoji (no strong bidi direction of its own), so a renderer that computes
    # alignment per line — not just once for the whole message — needs the mark on every one.
    # Skip it on the blank spacer line: a lone RTL mark isn't actually invisible-and-blank, it can
    # render as a faint stray mark on an otherwise empty line in some clients.
    return [(_RTL_MARK + line if line else line) for line in lines]


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
    return f"{_RTL_MARK}{emoji} {bold(label)} (היה {price_change_from:,}₪)\n\n"


# U+200F (Right-to-Left Mark, invisible) forces Telegram/WhatsApp to treat the WHOLE caption as an
# RTL paragraph regardless of which character comes first. Needed again because nearly every line
# above deliberately starts with an emoji (📍, 💰, 🛏️, ...) — emoji have no strong bidi direction
# of their own, so without this mark the caption's rendered alignment can fall back to LTR (a real
# user report + screenshot, 2026-09-03: their own card's text visibly started from the middle/left
# instead of the right, unlike the reference bot dorin.app's). An earlier version of this file used
# the same mark and removed it (2026-09-02) on the assumption that every line starting with real
# Hebrew TEXT (not emoji-first) would be enough on its own — that assumption didn't hold once the
# emoji-first, bold-label format above replaced it.
_RTL_MARK = "‏"


def format_caption(
    listing: Listing,
    *,
    has_access: bool,
    price_change_from: int | None = None,
    upgrade_url: str | None = None,
) -> str:
    """`price_change_from`: see _price_change_header. Left unset for a normal new-match card.

    `has_access` is required, not defaulted — 2026-09-05 request ("אני רוצה שזה יהיה סגור
    למשתמש... כל האינטרס של מנוי פרימיום זה שהפרטים יהיו מוחבאים ללא המנוי"): a lite/expired user
    (has_full_access() == False) gets everything a paying user gets EXCEPT the description and the
    actual listing link — the two things that let someone act on a match (read more, go apply) —
    replaced by a lock line pointing at `upgrade_url`. No default value on purpose: every call site
    must explicitly decide, so gating a new one is never something a future caller can forget to
    do by just not passing the argument."""
    bold = lambda s: f"<b>{s}</b>"  # noqa: E731
    lines = _build_body_lines(
        listing,
        bold=bold,
        street_link=lambda text, url: f'<a href="{url}">{text}</a>',
        escape=html.escape,
    )

    body = "\n".join(lines)
    header = _price_change_header(price_change_from, listing.price, bold=bold)
    if has_access:
        # listing.url is scraped from Yad2, not written by this project — escaped defensively so
        # a stray `"` in it could never break out of the href attribute.
        footer = f'\n\n{_RTL_MARK}🔗 <a href="{html.escape(listing.url)}">לפרטי הדירה המלאים &gt;&gt;</a>'
    elif upgrade_url:
        footer = f'\n\n{_RTL_MARK}🔒 <a href="{upgrade_url}">לפרטים המלאים וקישור ישיר — שדרג/י את המנוי</a>'
    else:
        footer = f"\n\n{_RTL_MARK}🔒 לפרטים המלאים וקישור ישיר יש לשדרג את המנוי"
    remaining = CAPTION_LIMIT - len(header) - len(body) - len(footer)
    description = html.escape((listing.description or "").strip()) if has_access else ""
    if description and remaining > 20:
        if len(description) > remaining:
            description = description[: remaining - 1] + "…"
        body += f"\n\n{_RTL_MARK}📝 {description}"

    return (header + body + footer)[:CAPTION_LIMIT]


WHATSAPP_MESSAGE_LIMIT = 4096


def format_caption_whatsapp(
    listing: Listing,
    *,
    has_access: bool,
    price_change_from: int | None = None,
    upgrade_url: str | None = None,
) -> str:
    """Same content/order as format_caption, WhatsApp's own markdown (*bold*, no HTML tags — the
    Cloud API's text messages don't render HTML) and no inline keyboard equivalent; the listing
    URL at the end is the only action available (WhatsApp's like/hide/found buttons would need
    interactive "reply button" messages, a separate message type — not built yet, plain text with
    a link is the MVP). The street can't be a custom-text link the way Telegram's can (WhatsApp
    only auto-links raw URLs, never arbitrary anchor text) — the plain street name stays inline
    and the same Google Maps URL is appended as its own tappable line instead.

    `has_access`/`upgrade_url`: see format_caption's own docstring — same gating, same required-
    not-defaulted argument."""
    bold = lambda s: f"*{s}*"  # noqa: E731
    lines = _build_body_lines(
        listing, bold=bold, street_link=lambda text, url: text, escape=lambda s: s
    )
    maps_url = _google_maps_url(listing)
    if maps_url:
        # Placed right after the location line, matching where it visually sits on Telegram. A
        # maps_url only exists when listing.street is set, which always makes _build_body_lines
        # add a "📍..." line too — but found defensively (default -1, appends at the end) rather
        # than assumed, so this can never raise even if that correlation ever changes. "in", not
        # "startswith" — every line now carries its own leading RTL mark (see _build_body_lines),
        # so the location line no longer literally starts with "📍" itself.
        location_index = next(
            (i for i, line in enumerate(lines) if "📍" in line), len(lines) - 1
        )
        lines.insert(location_index + 1, f"🗺️ {maps_url}")

    body = "\n".join(lines)
    header = _price_change_header(price_change_from, listing.price, bold=bold)
    if has_access:
        footer = f"\n\n{_RTL_MARK}🔗 לפרטי הדירה המלאים >>\n{listing.url}"
    elif upgrade_url:
        footer = f"\n\n{_RTL_MARK}🔒 לפרטים המלאים וקישור ישיר — שדרג/י את המנוי:\n{upgrade_url}"
    else:
        footer = f"\n\n{_RTL_MARK}🔒 לפרטים המלאים וקישור ישיר יש לשדרג את המנוי"
    remaining = WHATSAPP_MESSAGE_LIMIT - len(header) - len(body) - len(footer)
    description = (listing.description or "").strip() if has_access else ""
    if description and remaining > 20:
        if len(description) > remaining:
            description = description[: remaining - 1] + "…"
        body += f"\n\n{_RTL_MARK}📝 {description}"

    return (header + body + footer)[:WHATSAPP_MESSAGE_LIMIT]


async def send_listing_card(bot: Bot, chat_id: int, listing: Listing, caption: str) -> bool:
    """Sends one listing to one Telegram chat — the ONE place this project actually puts a
    listing on screen, used by the scraper's notifier and every bot handler that shows a listing,
    so real photos (added 2026-09-02 — see scraper/normalize.py's enrich_from_detail) render
    identically everywhere instead of each call site reinventing send_photo/send_message.

    ONE message per listing: a generated photo collage (2+ real photos — see
    _build_collage_sync above), the single real photo (exactly 1), or the Todi fallback (0) — with
    the caption and the ❤️/🙈/🎉 keyboard all on it via a plain send_photo. Deliberately NOT a
    multi-photo sendMediaGroup gallery anymore (2026-09-02, real
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
            photo: str | bytes = image_url
            if len(listing.image_urls) > 1:
                # asyncio.to_thread — _build_collage_sync does real network downloads + CPU-bound
                # resizing; see its own docstring for why this must never run directly on the
                # event loop.
                collage = await asyncio.to_thread(_build_collage_sync, listing.image_urls)
                if collage is not None:
                    photo = collage
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        else:
            no_photo_caption = (_NO_PHOTOS_PREFIX_HE + caption)[:CAPTION_LIMIT]
            await bot.send_photo(
                chat_id=chat_id,
                photo=_dachshund_photo_path(),
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
