"""Maps a raw Yad2 listing payload (one item from yad2_client.fetch_search_results) into a
NormalizedListing. Field names below are UNVERIFIED best guesses — see YAD2_NOTES.md. Update
once the real payload shape is known from the research spike.

Deliberately defensive: a malformed/missing field degrades to `None` rather than raising, so one
bad item doesn't abort a whole scrape run. `normalize()` itself never raises — it logs and
returns None for anything it can't make sense of, and main.py just skips None results.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from todira_common import cities
from todira_common.enums import DealType, Source
from todira_common.schemas import NormalizedListing
from todira_common.yad2_item_api import HEBREW_PROPERTY_TYPE_MAP, detail_updates_from_item

logger = logging.getLogger(__name__)


def _get(item: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Try several possible key names in order — a hedge against not yet knowing the exact
    field name until the research spike is done."""
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return default


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_price(value: Any) -> int | None:
    """Like _to_int, but a real 0 is treated the same as missing — unlike floor (0 = a genuine,
    meaningful ground floor) or size_sqm, a price of exactly ₪0 is never a real asking price; it's
    how a source represents "price on request"/not listed. Found live via a code-review pass:
    Yad2's own map API sends a bare `price: 0` for exactly this case, and _to_int's normal
    "0 is a real value" contract let it flow straight through as though ₪0 were a real price —
    showing as "₪0" on a card, bypassing any filter's own price_min, and capable of firing a real
    "price dropped to ₪0!" notification the moment a listing's real price briefly went missing."""
    n = _to_int(value)
    return None if n == 0 else n


def _to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return None  # don't guess-cast strings/ints to bool — leave as "unknown" rather than wrong


def _parse_datetime(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        logger.debug("Could not parse Yad2 timestamp %r, leaving posted_at as None", value)
        return None


# Yad2's own free-text `tags` (feature badges shown per search-results listing, see
# yad2_client._extract_feed_records) -> this project's amenity fields. Only tag names actually
# confirmed against real fetched listings (see
# .github/workflows/diagnose-search-page-feed-shape.yaml) are mapped — an unconfirmed/never-seen
# tag is simply ignored (no effect), never guessed. Extend as more tag names are observed live.
# Only ever SETS a field (True, or a specific value) — a tag's absence is never treated as
# "confirmed false/none", same benefit-of-the-doubt policy as everywhere else in this project.
_FEED_TAG_TO_FIELD: dict[str, tuple[str, Any]] = {
    "חניה": ("has_parking", True),
    'ממ"ד': ("safe_room_type", "safe_room"),
}

# (Yad2's Hebrew `additionalDetails.property.text` -> property type map lives in todira_common.yad2_item_api.)


def _enrich_from_feed_record(item: NormalizedListing, record: dict[str, Any]) -> NormalizedListing:
    """Fills in real photos, a confirmed broker/private status, and confirmed amenity tags from
    the search-results page's own embedded feed record for this listing (see
    yad2_client._extract_feed_records) — a free bonus enrichment layered on top of the card-text
    fields already parsed above, since this data rides along in the same request already being
    paid for. Purely additive and defensive, same contract as enrich_from_detail below.

    Does NOT include a free-text description, or amenities the detail page's `inProperty` has but
    the feed's `tags` don't confirm (e.g. elevator) — those genuinely aren't in this data source;
    use enrich_from_detail (a real, separate ZenRows cost) if that's ever wanted for a listing."""
    updates: dict[str, Any] = {}

    meta = record.get("metaData")
    meta = meta if isinstance(meta, dict) else {}
    images = meta.get("images")
    if isinstance(images, list):
        real_images = [u for u in images if isinstance(u, str) and u.strip()]
        if real_images:
            updates["image_urls"] = real_images

    additional = record.get("additionalDetails")
    additional = additional if isinstance(additional, dict) else {}
    property_field = additional.get("property")
    property_text = (
        (property_field.get("text") or "").strip() if isinstance(property_field, dict) else ""
    )
    if property_text in HEBREW_PROPERTY_TYPE_MAP:
        updates["property_type"] = HEBREW_PROPERTY_TYPE_MAP[property_text]

    tags = record.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            name = tag.get("name")
            if name in _FEED_TAG_TO_FIELD:
                field, value = _FEED_TAG_TO_FIELD[name]
                updates[field] = value
            elif isinstance(name, str) and "מרפס" in name:
                # "מרפס" (not "מרפסת") deliberately - the plural "מרפסות" (e.g. "2 מרפסות") does
                # NOT contain "מרפסת" as a substring (מרפס+ות vs מרפס+ת), caught by this file's
                # own test against the real confirmed "2 מרפסות" tag.
                updates["has_balcony"] = True

    # A synthetic flag _extract_feed_records adds based on which feed category
    # (private/agency/platinum/booster) this record came from — a confirmed signal in BOTH
    # directions (unlike enrich_from_detail's agencyName-only check below), since Yad2 itself
    # already sorts listings into those categories.
    is_broker = record.get("_is_broker_listing")
    if isinstance(is_broker, bool):
        updates["is_broker_listing"] = is_broker

    if not updates:
        return item
    return item.model_copy(update=updates)


def normalize(
    raw_item: dict[str, Any], *, source: str = Source.YAD2, deal_type: str = DealType.RENT
) -> NormalizedListing | None:
    """Returns None (and logs) only if the item is missing fields we can't function without
    (a usable id). Everything else degrades gracefully to None rather than aborting.

    2026-09-13: generalized from Yad2-only to accept any `source` (komo_client.py and
    homeless_client.py both now produce raw dicts in the SAME flat shape yad2_client._parse_cards
    already does — id/url/price/rooms/floor/square_meters/street/neighborhood/city — deliberately,
    specifically so this one function keeps working for all three without per-source branches).
    The `_get(...)` fallback key names below (roomsCount/squareMeter/cityText/etc.) are Yad2-
    specific historical hedges from before that shape was confirmed; harmless no-ops for
    Komo/Homeless items, which never carry those keys, but kept rather than removed since Yad2
    raw items (via _feed_record-enriched cards) still sometimes do."""
    external_id = _get(raw_item, "id", "adNumber", "order_id")
    if external_id is None:
        logger.warning("Skipping %s item with no recognizable id field: %r", source, raw_item)
        return None

    url = _get(raw_item, "url", "link")
    if url is None and source == Source.YAD2:
        # Yad2-specific historical fallback — Komo/Homeless items always carry their own real
        # "url" (see their own fetch_search_results), so they never need this and must NEVER get
        # a yad2.co.il URL slapped on by accident if one's ever missing (that would silently
        # mislabel a Komo/Homeless listing as a Yad2 one to anyone who clicks it). Left narrowly
        # scoped to source == Source.YAD2 rather than generalized to "any source, build some
        # generic URL" — a genuinely missing url for a non-Yad2 source should fail loudly (below,
        # `url: str` in NormalizedListing has no default, so this raises and gets skipped) rather
        # than silently invent a plausible-looking but wrong link.
        url = f"https://www.yad2.co.il/item/{external_id}"

    try:
        item = NormalizedListing(
            source=source,
            external_id=str(external_id),
            url=url,
            deal_type=deal_type,
            price=_to_price(_get(raw_item, "price")),
            rooms=_to_float(_get(raw_item, "rooms", "roomsCount")),
            floor=_to_int(_get(raw_item, "floor")),
            floor_total=_to_int(_get(raw_item, "floorTotal", "buildingFloors")),
            size_sqm=_to_int(_get(raw_item, "square_meters", "squareMeter")),
            # canonicalize_city: Yad2's own page text sometimes spells a city differently from
            # this project's bundled cities.py list (confirmed for Kiryat Motzkin, see that
            # module's docstring) — remap it here, once, so listings.city always agrees with
            # whatever spelling a saved filter's cities array uses, instead of every comparison
            # site (matching.py, notifier.py's SQL pre-filter) needing to know about spelling
            # variants.
            city=cities.canonicalize_city(_get(raw_item, "city", "cityText")),
            neighborhood=_get(raw_item, "neighborhood", "neighborhoodText"),
            street=_get(raw_item, "street", "streetText"),
            latitude=_to_float(_get(raw_item, "latitude")),
            longitude=_to_float(_get(raw_item, "longitude")),
            has_parking=_to_bool(_get(raw_item, "parking")),
            has_elevator=_to_bool(_get(raw_item, "elevator")),
            has_balcony=_to_bool(_get(raw_item, "balcony")),
            pets_allowed=_to_bool(_get(raw_item, "petsAllowed")),
            is_renovated=_to_bool(_get(raw_item, "renovated")),
            is_roommate_friendly=_to_bool(_get(raw_item, "roommates")),
            is_broker_listing=_to_bool(_get(raw_item, "isBroker", "agency")),
            safe_room_type="safe_room" if _get(raw_item, "safeRoom") is True else None,
            furniture="furnished" if _get(raw_item, "furnished") is True else None,
            move_in_note=(str(_get(raw_item, "move_in_text") or "").strip()[:40] or None),
            description=_get(raw_item, "description", "text"),
            image_urls=list(_get(raw_item, "images", "imageUrls", default=[]) or []),
            posted_at=_parse_datetime(_get(raw_item, "dateAdded", "updatedAt")),
            raw_payload=raw_item,
        )
    except Exception:
        logger.exception("Failed to normalize Yad2 item, skipping: %r", raw_item)
        return None

    # Free bonus enrichment (real photos/amenity tags/broker status) from the search page's own
    # embedded feed record, when yad2_client._parse_cards found one for this listing — see
    # _enrich_from_feed_record's own docstring. No extra cost: this data rides along in the same
    # search-page request already being fetched.
    feed_record = raw_item.get("_feed_record")
    if isinstance(feed_record, dict):
        item = _enrich_from_feed_record(item, feed_record)

    return item


def _compute_detail_updates(detail: dict[str, Any]) -> dict[str, Any]:
    """The field-extraction logic behind enrich_from_detail. Lives in todira_common.yad2_item_api now (2026-10-09) so the
    scraper, the notifier and the website share ONE mapping from a Yad2 ad record to Listing columns; this wrapper stays
    for the callers and tests that use the old name. Returns {} when `detail` yields nothing usable."""
    return detail_updates_from_item(detail)


def enrich_from_detail(item: NormalizedListing, detail: dict[str, Any]) -> NormalizedListing:
    """Fills in fields Yad2's search-results cards never carry at all — property type, amenity
    booleans, safe-room presence, a real description, real multi-photo image URLs, floor_total,
    move-in date, and broker status — from one listing's own detail-page data (see
    yad2_client.fetch_listing_detail, or common/todira_common/bright_data_client.py's
    fetch_listing_detail_via_bright_data — both read the same underlying Yad2 __NEXT_DATA__, just
    via different scraping infrastructure, confirmed 2026-09-12). Purely additive and defensive:
    `detail`'s exact shape was confirmed against real listings (2026-09-02 via ZenRows,
    2026-09-11/12 via Bright Data), so every read is a `.get()` with a type check, never a blind
    index — a field this can't confidently read is simply left at whatever `item` already had
    (usually None) rather than guessed. The actual extraction logic lives in
    `_compute_detail_updates` (only depends on `detail`, not `item` — this function's `item`
    argument is purely the base being updated). Only ever called for a listing genuinely new to the
    DB this run (see scraper/main.py) — never re-fetched for one already known, since each call is
    a real, separate cost (ZenRows credits or a Bright Data page load)."""
    updates = _compute_detail_updates(detail)
    if not updates:
        return item
    return item.model_copy(update=updates)
