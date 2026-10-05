"""Telegram card rendering for a `Listing` — shared by the scraper's notifier (new-match push)
and the bot's /apartments and /liked handlers (on-demand listing), so both surfaces render a
listing identically. See plan Section 4 for the card format this implements.
"""
from __future__ import annotations

import asyncio
import html
import io
import logging
import re
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import httpx
from PIL import Image
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError

from todira_common.bot_strings import bot_text
from todira_common.language import DEFAULT_LANG
from todira_common.models import Listing

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024

# A 2+ real-photo listing gets ONE composite collage image instead of just its first photo — 2026-
# 09-03 request, matching the reference bot's own style (a real user screenshot showed
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


def _download_photo_sync(url: str) -> Image.Image | None:
    """Downloads and decodes one photo URL, returning None on ANY failure — a dead link, a
    timeout, a non-image response, a corrupt file. Shared by _build_collage_sync (which needs
    several) and _first_downloadable_photo_jpeg_bytes below (which just needs the first working
    one) so both paths agree on what counts as "this photo actually works," instead of one of
    them trusting a URL the other already proved was dead."""
    try:
        response = httpx.get(url, timeout=_COLLAGE_DOWNLOAD_TIMEOUT_S)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")
    except Exception:
        logger.warning("Photo failed to download/decode: %s", url)
        return None


def _first_downloadable_photo_jpeg_bytes(image_urls: list[str]) -> bytes | None:
    """2026-09-21: real bug, live screenshot — a listing with exactly one photo (or 2+ that all
    failed to collage) used to hand that photo's raw URL straight to bot.send_photo without ever
    checking it actually loads. Telegram's own send_photo doesn't validate a URL synchronously —
    it accepts the message and tries to fetch it server-side afterward, so a dead URL (confirmed
    here: Komo's own showPic endpoint intermittently 404s/times out — the exact same URLs this
    module's own collage step already logs as "failed to download/decode") renders as a generic
    broken-image placeholder instead of falling back to the Todi mascot, which only ever
    triggered for a listing with ZERO photo URLs, not one where every URL is simply unreachable.
    Tries each of up to _COLLAGE_MAX_PHOTOS candidate URLs in order and returns the first one that
    actually downloads, re-encoded as JPEG bytes (never the raw URL) so Telegram is never hand a
    link it might fail to fetch itself. None means every candidate failed — caller falls back to
    the mascot, same contract as _build_collage_sync."""
    for url in image_urls[:_COLLAGE_MAX_PHOTOS]:
        photo = _download_photo_sync(url)
        if photo is not None:
            buffer = io.BytesIO()
            photo.save(buffer, format="JPEG", quality=90)
            return buffer.getvalue()
    return None


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
        photo = _download_photo_sync(url)
        if photo is None:
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
# — italic reads as an aside, easy to skim past). 2026-09-03 it was placed FIRST because a real user
# missed it at the end; 2026-10-05 it moved to the END on the owner's request: a Telegram push shows only
# the START of the caption, and a banner there replaced the details that decide whether to open the
# notification (location, price, rooms — dorin.app shows those first too).
# See bot_strings.py's "card.no_photos_banner" — sent as plain text in send_listing_card itself,
# same as every other line in this file (see _build_body_lines' own module comment for why this
# file no longer adds any bidi marks at all).


def _dachshund_photo_path() -> Path:
    return _MASCOT_PATH


def get_listing_photo_jpeg_bytes(image_urls: list[str]) -> bytes:
    """Real listing photo(s) as JPEG bytes, for any surface that needs to attach ONE image
    somewhere other than Telegram's own send_photo (which already inlines this exact fallback
    chain directly in send_listing_card below, since python-telegram-bot's send_photo also accepts
    a local Path for the mascot fallback) — currently WhatsApp's rich match-template send
    (scraper/notifier.py), which needs actual bytes to upload via the Cloud API's /media endpoint.

    A 2+ photo collage when possible, else the first downloadable single photo, else the same
    Todi-detective mascot image send_listing_card falls back to when a listing has no usable photo
    at all — always returns real bytes, never None, so callers never need their own no-photo
    branch. Synchronous/blocking (network downloads + image resizing) — callers MUST run this via
    asyncio.to_thread, same contract as _build_collage_sync/_first_downloadable_photo_jpeg_bytes."""
    photo = None
    if len(image_urls) > 1:
        photo = _build_collage_sync(image_urls)
    if photo is None:
        photo = _first_downloadable_photo_jpeg_bytes(image_urls)
    if photo is None:
        photo = _MASCOT_PATH.read_bytes()
    return photo


# 2026-09-03 rewrite: field order/labels/emphasis matching the reference bot 1:1, per a
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
_FEATURE_EMOJI_LABEL_KEYS = (
    ("has_parking", "🚗", "card.feature_parking"),
    ("has_elevator", "🛗", "card.feature_elevator"),
    ("has_balcony", "🌿", "card.feature_balcony"),
    ("pets_allowed", "🐾", "card.feature_pets_allowed"),
    ("is_renovated", "✨", "card.feature_renovated"),
    ("is_roommate_friendly", "🤝", "card.feature_roommate_friendly"),
)


def feature_list(listing: Listing, lang: str) -> list[str]:
    """Each feature prefixed with its own emoji — the SAME ones the website's own amenity row
    uses (website/static/style.css's .amenity-row / _listing_card.html) for has_parking through
    furniture, so the two surfaces read consistently. is_roommate_friendly has no website
    equivalent to match (not shown there today) — 🤝 chosen fresh.

    Public (renamed from _feature_list 2026-09-27) — scraper/notifier.py's WhatsApp rich
    match-template send needs this same amenity list flattened into one template body parameter,
    not just this module's own multi-line _build_body_lines."""
    items = [
        f"{emoji}{bot_text(key, lang)}"
        for attr, emoji, key in _FEATURE_EMOJI_LABEL_KEYS
        if getattr(listing, attr) is True
    ]
    if listing.safe_room_type in ("safe_room", "building_shelter"):
        items.append(f"🛡️{bot_text('card.feature_safe_room', lang)}")
    if listing.furniture == "furnished":
        items.append(f"🛋️{bot_text('card.feature_furnished', lang)}")
    return items


def _google_maps_url(listing: Listing) -> str | None:
    """A plain Google Maps search-URL — no API key needed, works for any address string. None
    when there's no street to point at (a bare city/neighborhood isn't precise enough to be worth
    a map link)."""
    if not listing.street:
        return None
    parts = [p for p in (listing.street, listing.neighborhood, listing.city) if p]
    return f"https://www.google.com/maps/search/?api=1&query={quote(', '.join(parts))}"


def _deal_type_prefix_word(listing: Listing, lang: str) -> str | None:
    """"card.broker" takes priority over "card.sublet" when both would somehow apply — a
    plain rent or sale listing gets None (no prefix line at all)."""
    if listing.is_broker_listing:
        return bot_text("card.broker", lang)
    if listing.deal_type == "sublet":
        return bot_text("card.sublet", lang)
    return None


_MOVE_IN_NOTE_KEYS = {"מיידית": "card.move_in_immediate", "גמיש": "card.move_in_flexible"}


def _build_body_lines(
    listing: Listing,
    *,
    bold: Callable[[str], str],
    street_link: Callable[[str, str], str],
    escape: Callable[[str], str],
    lang: str,
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

    prefix_word = _deal_type_prefix_word(listing, lang)
    if prefix_word is not None:
        lines.append(f"🏢 {bold(prefix_word)}")

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
        lines.append(f"💰 {bold(bot_text('card.price_label', lang))} {listing.price:,}₪")

    lines.append(f"🛏️ {bold(bot_text('card.rooms_label', lang))} {listing.rooms or '?'}")

    if listing.size_sqm:
        area_value = bot_text("kb.sqm_value", lang, value=listing.size_sqm)
        lines.append(f"📐 {bold(bot_text('card.area_label', lang))} {area_value}")

    if listing.floor is not None:
        floor_line = f"🏢 {bold(bot_text('card.floor_label', lang))} {listing.floor}"
        if listing.floor_total is not None:
            floor_line += f" {bot_text('card.floor_of', lang)} {listing.floor_total}"
        lines.append(floor_line)

    move_in_label = bold(bot_text("card.move_in_label", lang))
    if listing.move_in_date is not None:
        lines.append(f"📅 {move_in_label} {listing.move_in_date.strftime('%d.%m.%Y')}")
    elif getattr(listing, "move_in_note", None):
        # A source that gives text, not a date (Komo: "מיידית" / "גמיש"). Known words are translated;
        # anything else is shown as the source wrote it.
        note = listing.move_in_note
        note_key = _MOVE_IN_NOTE_KEYS.get(note)
        shown = bot_text(note_key, lang) if note_key else escape(note)
        lines.append(f"📅 {move_in_label} {shown}")

    features = feature_list(listing, lang)
    if features:
        features_label = bold(bot_text("card.features_label", lang))
        lines.append("")  # a visual gap before the features line — a real request, 2026-09-03
        lines.append(f"🔑 {features_label} {' | '.join(features)}")

    return lines


def _price_change_header(
    price_change_from: int | None,
    current_price: int | None,
    *,
    bold: Callable[[str], str],
    lang: str,
) -> str:
    """`price_change_from`: the previous price, when this card is a re-notification because the
    price changed (either direction — a drop gets 📉, an increase gets 📈; see
    scraper/notifier.py). None (the normal case) means no header at all, matching a real request
    that a brand-new listing not get any price-change banner."""
    if price_change_from is None or current_price is None or price_change_from == current_price:
        return ""
    if price_change_from > current_price:
        emoji, label_key = "📉", "card.price_dropped"
    else:
        emoji, label_key = "📈", "card.price_increased"
    label = bold(bot_text(label_key, lang))
    was_price = bot_text("card.was_price", lang, price=f"{price_change_from:,}")
    return f"{emoji} {label} {was_price}\n\n"


# 2026-09-14 through 2026-09-30: this file went through a long series of increasingly elaborate
# attempts to FORCE correct right-alignment for Hebrew/Arabic captions with explicit Unicode bidi
# control characters — a bare RLM mark, then a full RLE...PDF embedding around every line, then
# RLI/PDI isolates with a leading RLM+ZWNJ on every icon, then a trailing RLM+LRM "absorber" line.
# Each attempt fixed some real, live-confirmed symptom and broke or left another — see this file's
# git history and PROJECT_STATE.md for the full trail (diagnose-rtl-*-live-test-v3 through v21).
#
# 2026-09-30, the actual resolution: the owner copied a real message from a working reference bot
# (Dorin's) directly out of Telegram Desktop for a side-by-side comparison. It contains ZERO
# invisible bidi marks of any kind and no manual line pre-wrapping — completely plain Hebrew text,
# bold and links included — and renders flush right. A live test sending our own real listing
# content the same way (v21) confirmed it: dropping every mark and every pre-wrap this file used
# to add fixed the alignment, while every mark-based attempt before it left a persistent gap on the
# right that no further tuning closed. Telegram's own native bidi handling of a real RTL message
# needs no help from this project — every mark added here was apparently confusing Telegram's own
# client-side text-block positioning rather than fixing anything. This file now builds every
# caption as plain text: real `<b>`/`<a>` HTML entities, real line breaks, no bidi characters.


# 2026-10-01 (owner's screenshot of a short Bat Yam card, final request): Telegram lays a media
# caption's text out in a block exactly as wide as its LONGEST line, anchored to the bubble's left
# edge, and right-aligns RTL lines inside that block. A short caption (no description, or one made of
# short lines) therefore ends in the middle of the bubble with a big empty gap on the right, while a
# caption with any long line spans the whole bubble and is flush right. Bidi marks cannot influence
# this (it is block width, not direction). The fix is to make the block as wide as the bubble: one
# final line of Braille-blank characters (U+2800, not whitespace, so Telegram does not trim it),
# added ONLY when no line is already long, and long enough that it wraps rather than falling short -
# at worst it adds a blank line or two at the very bottom.
_WIDTH_PAD = "\u2800" * 34
_LONG_LINE_VISIBLE_CHARS = 36
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _visible_length(line: str) -> int:
    return len(html.unescape(_HTML_TAG_RE.sub("", line)))


def _with_width_pad_if_short(caption: str, limit: int) -> str:
    """See _WIDTH_PAD. Never pushes the caption past `limit`."""
    if len(caption) + 1 + len(_WIDTH_PAD) > limit:
        return caption
    if any(_visible_length(line) >= _LONG_LINE_VISIBLE_CHARS for line in caption.split("\n")):
        return caption
    return f"{caption}\n{_WIDTH_PAD}"


def _normalize_line_breaks(text: str) -> str:
    """Homeless's own scraped descriptions sometimes use a bare "\\r" as their line separator
    (found live 2026-09-21, diagnose-homeless-description-raw-chars.yaml) — Telegram/WhatsApp only
    treat a literal "\\n" as a line break, so a bare \\r (or \\r\\n) needs normalizing first or it
    renders as no line break at all. splitlines() handles \\r, \\r\\n, \\n and the other
    line-boundary characters Python recognizes."""
    return "\n".join(text.splitlines())


def _truncated_description_block(raw: str, budget: int, escape: Callable[[str], str]) -> str:
    """The "\\n\\n📝 <description>" block, cut to fit `budget` characters of the caption's total
    length (counted AFTER escaping, since Telegram's limit applies to the final HTML text), or ""
    when there's no description or too little room left to be worth adding one.

    Real bug, found 2026-09-30 in a code-review pass: the old inline version budgeted only the
    description's own length and forgot the 4-character "\\n\\n📝 " prefix — so a description long
    enough to need truncating always landed a few characters over the limit, and _fit_to_limit's
    drop-trailing-body-lines safety net then removed the whole description as one "line," leaving a
    caption with no description at all for exactly the listings that had the most to say. It also
    truncated AFTER escaping, which could cut an HTML entity in half ("&amp;" -> "&am…"); escaping
    one character at a time while counting avoids both."""
    text = _normalize_line_breaks(raw.strip())
    prefix = "\n\n📝 "
    room = budget - len(prefix)
    if not text or room <= 20:
        return ""
    escaped_whole = escape(text)
    if len(escaped_whole) <= room:
        return prefix + escaped_whole
    pieces: list[str] = []
    used = 0
    for char in text:
        piece = escape(char)
        if used + len(piece) > room - 1:
            break
        pieces.append(piece)
        used += len(piece)
    return prefix + "".join(pieces).rstrip() + "…"


def _fit_to_limit(header: str, body: str, footer: str, limit: int) -> str:
    """Real production bug, found 2026-09-14 while chasing an unrelated RTL report: the owner's
    own live run logged 18+ failed sends, `telegram.error.BadRequest: Can't parse entities: can't
    find end tag corresponding to start tag "a"` / `unclosed start tag at byte offset ...`.
    `header + body + footer` was being blindly sliced to `limit` characters — but the caption's
    length budget only ever accounted for how much DESCRIPTION text to add (see the `remaining`
    calculation at each caller), not for header+body+footer alone already exceeding `limit` on a
    listing with enough content (a price-change header, a long location/street with its own
    <a href=...> Google Maps link, several features, ...) — no description involved at all. When
    that happens, the blind slice can land inside ANY of this caption's several <a>...</a> tags
    (the street's maps link mid-body, or the footer's own listing link at the very end), and
    Telegram's HTML parser rejects the WHOLE message rather than rendering a truncated tag — a
    hard send failure, not a cosmetic one.

    Every real <a>...</a> in this file opens and closes within a single line (never split across
    lines), so dropping whole trailing BODY lines — instead of slicing characters — can never
    itself produce an unclosed tag. The header and footer are never touched: the footer in
    particular carries the one link every caption must keep (the listing's own source link, or the
    upgrade lock line), so it must survive intact even when the body has to give up content."""
    if len(header) + len(body) + len(footer) <= limit:
        return header + body + footer
    lines = body.split("\n")
    while lines and len(header) + len("\n".join(lines)) + len(footer) > limit:
        lines.pop()
    return header + "\n".join(lines) + footer


def format_caption(
    listing: Listing,
    *,
    has_access: bool,
    price_change_from: int | None = None,
    upgrade_url: str | None = None,
    view_url: str | None = None,
    lang: str = DEFAULT_LANG,
) -> str:
    """`price_change_from`: see _price_change_header. Left unset for a normal new-match card.

    `has_access` is required, not defaulted. **Policy changed 2026-09-12**: originally (2026-09-05
    request, "אני רוצה שזה יהיה סגור למשתמש... כל האינטרס של מנוי פרימיום זה שהפרטים יהיו מוחבאים
    ללא המנוי") a lite/expired user got the description AND the listing link both hidden. The
    owner's later, explicit call reverses this: the description (and every other scraped field —
    price, rooms, amenities, photos) is shown to EVERY viewer regardless of subscription now; only
    the outbound link to the listing's actual source (Yad2/Komo/Homeless/Facebook/whatever it came
    from) stays gated — replaced by a lock line pointing at `upgrade_url` for a lite/expired user.
    This project never stores the poster's own contact info (agent name/phone/agency — see
    normalize.py's enrich_from_detail, only a derived is_broker_listing boolean is kept), so
    showing the description to everyone can't leak that regardless. `has_access` stays a required,
    not-defaulted argument: every call site must still explicitly decide, so gating a new one is
    never something a future caller can forget to do by just not passing the argument — even
    though today it only controls the link, not the description.

    2026-09-30: real bug, confirmed live via a long battery of diagnostic sends to the owner's own
    Telegram (see the module comment above _normalize_line_breaks for the full history). Every
    line is plain HTML text now — no bidi marks, `<b>{s}</b>` same as always."""
    bold = lambda s: f"<b>{s}</b>"  # noqa: E731
    lines = _build_body_lines(
        listing,
        bold=bold,
        street_link=lambda text, url: f'<a href="{url}">{text}</a>',
        # quote=False: this text lands as HTML element CONTENT (a city/street name, never inside an
        # attribute), where only &, <, > are meaningful to Telegram's own HTML parser. html.escape's
        # own default (quote=True) also turns a literal " into "&quot;" - real bug, found live
        # 2026-09-30 via an owner screenshot of a street containing Hebrew gershayim ("הפלמ"ח"):
        # Telegram doesn't treat &quot; as a recognized named entity outside an attribute, so it
        # rendered as literal, garbled text instead of a plain " character.
        escape=lambda s: html.escape(s, quote=False),
        lang=lang,
    )

    body = "\n".join(lines)
    header = _price_change_header(price_change_from, listing.price, bold=bold, lang=lang)
    if has_access:
        # 2026-09-27 real owner request, matching dorin.app: the outbound link should land on
        # THIS project's own listing page (todira.app), not send the viewer straight to the raw
        # external source — callers now pass view_url for that (scraper/notifier.py builds
        # /apartments?uid=...&listing={id}). Falls back to the raw scraped listing.url when no
        # view_url is given (existing callers, e.g. bot/handlers/liked.py, untouched). listing.url
        # itself is scraped from Yad2, not written by this project — escaped defensively either
        # way so a stray `"` could never break out of the href attribute.
        safe_url = html.escape(view_url or listing.url)
        link_text = bot_text("card.full_details_link_html", lang)
        footer_text = f'🔗 <a href="{safe_url}">{link_text}</a>'
    elif upgrade_url:
        link_text = bot_text("card.upgrade_to_see_link", lang)
        footer_text = f'🔒 <a href="{upgrade_url}">{link_text}</a>'
    else:
        footer_text = f"🔒 {bot_text('card.upgrade_required_plain', lang)}"
    footer = f"\n\n{footer_text}"
    remaining = CAPTION_LIMIT - len(header) - len(body) - len(footer)
    # quote=False here too — same reasoning as _build_body_lines' own escape= above, this is
    # message text, never an attribute value.
    body += _truncated_description_block(
        listing.description or "", remaining, lambda s: html.escape(s, quote=False)
    )

    return _with_width_pad_if_short(_fit_to_limit(header, body, footer, CAPTION_LIMIT), CAPTION_LIMIT)


WHATSAPP_MESSAGE_LIMIT = 4096


def format_caption_whatsapp(
    listing: Listing,
    *,
    has_access: bool,
    price_change_from: int | None = None,
    upgrade_url: str | None = None,
    view_url: str | None = None,
    link_in_body: bool = True,
    limit: int = WHATSAPP_MESSAGE_LIMIT,
    lang: str = DEFAULT_LANG,
) -> str:
    """`view_url`: the link for a user with access (falls back to the raw listing.url).
    `link_in_body=False` drops that link line — for a message that carries the link as its own
    button (whatsapp_client.send_image_cta_message). `limit`: 1024 for an interactive body.

    Same content/order as format_caption, WhatsApp's own markdown (*bold*, no HTML tags — the
    Cloud API's text messages don't render HTML) and no inline keyboard equivalent; the listing
    URL at the end is the only action available (WhatsApp's like/hide/found buttons would need
    interactive "reply button" messages, a separate message type — not built yet, plain text with
    a link is the MVP). The street can't be a custom-text link the way Telegram's can (WhatsApp
    only auto-links raw URLs, never arbitrary anchor text) — the plain street name stays inline
    and the same Google Maps URL is appended as its own tappable line instead.

    `has_access`/`upgrade_url`: see format_caption's own docstring — same gating (description
    always shown, only the link stays access-gated as of 2026-09-12), same required-not-defaulted
    argument."""
    bold = lambda s: f"*{s}*"  # noqa: E731
    lines = _build_body_lines(
        listing, bold=bold, street_link=lambda text, url: text, escape=lambda s: s, lang=lang
    )
    # 2026-10-02 owner decision: no Google Maps link on WhatsApp. A WhatsApp text can't turn the street
    # into a link (only a raw, very long URL auto-links), so the full address stays as plain text.
    body = "\n".join(lines)
    header = _price_change_header(price_change_from, listing.price, bold=bold, lang=lang)
    if has_access:
        link_text = bot_text("card.full_details_link_plain", lang)
        footer = f"\n\n🔗 {link_text}\n{view_url or listing.url}" if link_in_body else ""
    elif upgrade_url:
        upgrade_text = f"{bot_text('card.upgrade_to_see_link', lang)}:"
        footer = f"\n\n🔒 {upgrade_text}\n{upgrade_url}"
    else:
        upgrade_text = bot_text("card.upgrade_required_plain", lang)
        footer = f"\n\n🔒 {upgrade_text}"
    remaining = limit - len(header) - len(body) - len(footer)
    body += _truncated_description_block(listing.description or "", remaining, lambda s: s)

    return _fit_to_limit(header, body, footer, limit)


async def send_listing_card(
    bot: Bot, chat_id: int, listing: Listing, caption: str, lang: str = DEFAULT_LANG
) -> bool:
    """Sends one listing to one Telegram chat — the ONE place this project actually puts a
    listing on screen, used by the scraper's notifier and every bot handler that shows a listing,
    so real photos (added 2026-09-02 — see scraper/normalize.py's enrich_from_detail) render
    identically everywhere instead of each call site reinventing send_photo/send_message.

    ONE message per listing: a generated photo collage (2+ real photos — see
    _build_collage_sync above), the single real photo (exactly 1, or 2+ that couldn't collage —
    see _first_downloadable_photo_jpeg_bytes above), or the Todi fallback (0 photo URLs, OR 1+
    that all failed to download — 2026-09-21 real bug, a dead photo URL used to render as
    Telegram's own generic broken-image placeholder instead of falling back here) — with the
    caption and the ❤️/🙈/🎉 keyboard all on it via a plain send_photo. Deliberately NOT a
    multi-photo sendMediaGroup gallery anymore (2026-09-02, real
    user report + a direct ask to match the reference bot's own cleaner single-message
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
    keyboard = listing_keyboard(listing.id, lang)
    image_url = listing.image_urls[0] if listing.image_urls else None

    async def _do_send() -> None:
        photo: str | bytes | None = None
        if image_url is not None:
            # asyncio.to_thread for both — real network downloads + CPU-bound resizing/encoding;
            # see _build_collage_sync's own docstring for why this must never run directly on the
            # event loop.
            if len(listing.image_urls) > 1:
                photo = await asyncio.to_thread(_build_collage_sync, listing.image_urls)
            if photo is None:
                # Either exactly 1 photo, or 2+ that all failed to collage — try each candidate
                # URL in turn and send back real, already-validated bytes, never a URL that might
                # still be dead (2026-09-21: this is the real bug fix — previously this branch
                # just trusted image_url as a string with no download attempt at all).
                photo = await asyncio.to_thread(
                    _first_downloadable_photo_jpeg_bytes, listing.image_urls
                )
        if photo is None:
            banner_text = bot_text("card.no_photos_banner", lang).rstrip("\n")
            banner = f"\n\n{banner_text}"
            # 2026-09-28 real bug found via a fresh code-review pass: a raw [:CAPTION_LIMIT]
            # character slice can cut anywhere at all — including mid-HTML-tag, straight through
            # the footer's <a href="...">...</a> link, exactly the bug class _fit_to_limit exists
            # to prevent (see its own docstring for the real "Can't parse entities" failure this
            # produces). `caption` on its own is already safely fit to CAPTION_LIMIT by its own
            # caller (format_caption's _fit_to_limit call, footer/link always kept intact) — so on
            # the rare listing where prepending the banner would push the total over the limit,
            # drop the banner entirely rather than risk truncating caption's own content. Losing a
            # friendly "no photos, try asking" note costs far less than losing the whole
            # notification to a send that Telegram rejects outright.
            no_photo_caption = caption + banner if len(banner) + len(caption) <= CAPTION_LIMIT else caption
            await bot.send_photo(
                chat_id=chat_id,
                photo=_dachshund_photo_path(),
                caption=no_photo_caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        else:
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
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


def listing_keyboard(listing_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    bot_text("card.like_button", lang), callback_data=f"like:{listing_id}"
                ),
                InlineKeyboardButton(
                    bot_text("card.hide_button", lang), callback_data=f"hide:{listing_id}"
                ),
                InlineKeyboardButton(
                    bot_text("card.found_button", lang), callback_data=f"found:{listing_id}"
                ),
            ]
        ]
    )
