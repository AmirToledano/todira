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

from dorin_common import cities
from dorin_common.enums import DealType
from dorin_common.schemas import NormalizedListing

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


def normalize(raw_item: dict[str, Any], *, deal_type: str = DealType.RENT) -> NormalizedListing | None:
    """Returns None (and logs) only if the item is missing fields we can't function without
    (a usable id). Everything else degrades gracefully to None rather than aborting."""
    external_id = _get(raw_item, "id", "adNumber", "order_id")
    if external_id is None:
        logger.warning("Skipping Yad2 item with no recognizable id field: %r", raw_item)
        return None

    url = _get(raw_item, "url", "link")
    if url is None:
        # best-effort fallback shape — verify the real ad URL pattern during the research spike
        url = f"https://www.yad2.co.il/item/{external_id}"

    try:
        return NormalizedListing(
            source="yad2",
            external_id=str(external_id),
            url=url,
            deal_type=deal_type,
            price=_to_int(_get(raw_item, "price")),
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
            has_parking=_to_bool(_get(raw_item, "parking")),
            has_elevator=_to_bool(_get(raw_item, "elevator")),
            has_balcony=_to_bool(_get(raw_item, "balcony")),
            pets_allowed=_to_bool(_get(raw_item, "petsAllowed")),
            is_renovated=_to_bool(_get(raw_item, "renovated")),
            is_roommate_friendly=_to_bool(_get(raw_item, "roommates")),
            is_broker_listing=_to_bool(_get(raw_item, "isBroker", "agency")),
            description=_get(raw_item, "description", "text"),
            image_urls=list(_get(raw_item, "images", "imageUrls", default=[]) or []),
            posted_at=_parse_datetime(_get(raw_item, "dateAdded", "updatedAt")),
            raw_payload=raw_item,
        )
    except Exception:
        logger.exception("Failed to normalize Yad2 item, skipping: %r", raw_item)
        return None


# Yad2's own `property.textEng` -> this project's PropertyType literal (schemas.py). Only values
# actually confirmed against a real fetched listing (see fetch_listing_detail's module comment in
# yad2_client.py) are mapped — an unmapped/never-seen value deliberately falls through to None
# (matching.py already gives that the benefit of the doubt) rather than guessing at a mapping this
# project hasn't verified. Extend as more values are confirmed live.
_PROPERTY_TYPE_MAP = {
    "penthouse": "penthouse",
}


def enrich_from_detail(item: NormalizedListing, detail: dict[str, Any]) -> NormalizedListing:
    """Fills in fields Yad2's search-results cards never carry at all — property type, amenity
    booleans, safe-room presence, a real description, real multi-photo image URLs, floor_total,
    move-in date, and broker status — from one listing's own detail-page data (see
    yad2_client.fetch_listing_detail). Purely additive and defensive: `detail`'s exact shape was
    confirmed against exactly one real listing (2026-09-02), so every read here is a `.get()` with
    a type check, never a blind index — a field this can't confidently read is simply left at
    whatever `item` already had (usually None) rather than guessed. Only ever called for a listing
    genuinely new to the DB this run (see scraper/main.py) — never re-fetched for one already
    known, since each call is a real, separate ZenRows request."""
    updates: dict[str, Any] = {}

    additional = detail.get("additionalDetails")
    additional = additional if isinstance(additional, dict) else {}
    in_property = detail.get("inProperty")
    in_property = in_property if isinstance(in_property, dict) else {}
    meta = detail.get("metaData")
    meta = meta if isinstance(meta, dict) else {}
    customer = detail.get("customer")
    customer = customer if isinstance(customer, dict) else {}

    property_field = additional.get("property")
    property_type_eng = (
        (property_field.get("textEng") or "").strip() if isinstance(property_field, dict) else ""
    )
    if property_type_eng in _PROPERTY_TYPE_MAP:
        updates["property_type"] = _PROPERTY_TYPE_MAP[property_type_eng]

    if isinstance(in_property.get("includeParking"), bool):
        updates["has_parking"] = in_property["includeParking"]
    if isinstance(in_property.get("includeElevator"), bool):
        updates["has_elevator"] = in_property["includeElevator"]
    if isinstance(in_property.get("includeBalcony"), bool):
        updates["has_balcony"] = in_property["includeBalcony"]
    if isinstance(in_property.get("includeSecurityRoom"), bool):
        updates["safe_room_type"] = (
            "safe_room" if in_property["includeSecurityRoom"] else "none"
        )

    floor_total = additional.get("buildingTopFloor")
    if isinstance(floor_total, int):
        updates["floor_total"] = floor_total

    entrance_date = _parse_datetime(additional.get("entranceDate"))
    if entrance_date is not None:
        updates["move_in_date"] = entrance_date.date()

    description = meta.get("description")
    if isinstance(description, str) and description.strip():
        updates["description"] = description.strip()

    images = meta.get("images")
    if isinstance(images, list):
        real_images = [u for u in images if isinstance(u, str) and u.strip()]
        if real_images:
            updates["image_urls"] = real_images

    # An agency NAME is a confident positive signal ("definitely a broker listing"); its absence
    # is NOT confident evidence of the opposite (a private listing might still carry some customer
    # record) — so this only ever sets True, matching the benefit-of-the-doubt policy the rest of
    # this field already gets in matching.py (an unset/None value stays untouched here).
    if customer.get("agencyName"):
        updates["is_broker_listing"] = True

    if not updates:
        return item
    return item.model_copy(update=updates)
