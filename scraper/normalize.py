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
