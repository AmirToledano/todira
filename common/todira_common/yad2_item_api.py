"""Yad2 listing details from Yad2's own per-listing JSON endpoint — free, no AI, no paid scraper (2026-10-09).

`GET https://gw.yad2.co.il/realestate-item/<token>` returns `{"data": {...}, "message": ...}` with the whole ad record: the
description (`metaData.description`), total floors (`additionalDetails.buildingTopFloor`), entrance date, the amenity
booleans in `inProperty`, photos, and `dates` (created / updated). Verified live from the production egress IP
(diagnose-yad2-item-json-endpoint.yaml and -shape.yaml, 2026-10-09): 60 of 60 requests answered HTTP 200 JSON at ~0.6 s
each, with the same browser-TLS fingerprint (curl_cffi `impersonate="chrome"`) the free map route already uses. The ad's
HTML page (www.yad2.co.il/item/<token>) is still behind Radware, which is why details used to come from Gemini's URL
context or a paid unlocker — Gemini answered HTTP 402 (prepaid balance spent) on every model on 2026-10-09 and the cards
went out without description / floors / features, the gap this module closes.

The record has the same inner shape as the `__NEXT_DATA__` item the older fetchers parsed, so `detail_updates_from_item`
below is the single place that turns it into Listing columns (scraper/normalize.py's `_compute_detail_updates` delegates here).

Contract: `fetch_yad2_detail_updates(url)` returns a dict of column updates (possibly EMPTY: the ad exists but states
nothing usable, or it is gone — both definitive, nothing to retry) or None (disabled, blocked, network/HTTP error —
retry later). Never raises. Requests are serialised per process, one second apart.

Bot protection (found in the first production run, 2026-10-09): now and then Yad2's WAF answers HTTP 200 with a JSON body
that is NOT the ad — `{"_event_clientip": ..., "_event_clientport": ..., "_event_transid": ...}` — about 3 in 15 at 0.5 s spacing
from the cluster IP (60 in a row at 0.65 s passed in the earlier probe). That is a rate-limit signal, not a missing ad: such an
answer is retried after 8 s and again after 20 s, and only a request that still fails after the retries counts as a failure;
three failed requests in a row pause the fetcher for 15 minutes so it can never turn into a hammering loop.

Opt-in via YAD2_ITEM_API=true (helm scraper/website `yad2ItemApi`)."""
from __future__ import annotations

import datetime as dt
import logging
import os
import re
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

ENABLED_ENV_VAR = "YAD2_ITEM_API"
MIN_SPACING_ENV_VAR = "YAD2_ITEM_API_MIN_SPACING_SECONDS"
_DEFAULT_MIN_SPACING_SECONDS = 1.0
_ITEM_URL = "https://gw.yad2.co.il/realestate-item/{token}"
_TOKEN_RE = re.compile(r"/item/([A-Za-z0-9]+)")
_TIMEOUT_SECONDS = 25
_BLOCK_AFTER_FAILURES = 3
_RETRY_WAITS_SECONDS = (8.0, 20.0)
_BLOCK_SECONDS = 900.0
_MAX_DESCRIPTION_CHARS = 4000

# Yad2's `additionalDetails.property.textEng` / `.text` -> this project's property type. Only values confirmed live are
# mapped; anything else stays None (matching.py gives that the benefit of the doubt).
PROPERTY_TYPE_BY_ENG = {"penthouse": "penthouse"}
HEBREW_PROPERTY_TYPE_MAP = {
    "דירה": "apartment",
    "דירת גן": "garden_apartment",
    "גג/ פנטהאוז": "penthouse",
    "בית בודד": "private_house",
}

_lock = threading.Lock()
_last_request_at = 0.0
_consecutive_failures = 0
_blocked_until = 0.0


def is_enabled() -> bool:
    if os.environ.get(ENABLED_ENV_VAR, "").strip().lower() != "true":
        return False
    try:
        import curl_cffi  # noqa: F401
    except ImportError:
        return False
    return True


def token_from_url(url: str) -> str | None:
    match = _TOKEN_RE.search(url or "")
    return match.group(1) if match else None


def _min_spacing() -> float:
    raw = os.environ.get(MIN_SPACING_ENV_VAR, "").strip()
    try:
        return max(0.0, float(raw)) if raw else _DEFAULT_MIN_SPACING_SECONDS
    except ValueError:
        return _DEFAULT_MIN_SPACING_SECONDS


def _record_failure(url: str, reason: str) -> None:
    global _consecutive_failures, _blocked_until
    _consecutive_failures += 1
    logger.warning("Yad2 item API %s for %s", reason, url)
    if _consecutive_failures >= _BLOCK_AFTER_FAILURES:
        _blocked_until = time.monotonic() + _BLOCK_SECONDS
        _consecutive_failures = 0
        logger.warning(
            "Yad2 item API failed %d requests in a row — pausing it for %.0f min", _BLOCK_AFTER_FAILURES, _BLOCK_SECONDS / 60
        )


def _request_once(token: str) -> tuple[str, Any]:
    """One HTTP attempt: ("ok", data) / ("gone", {}) / ("retry", reason). Caller holds the lock."""
    global _last_request_at
    from curl_cffi import requests as curl_requests

    wait = _last_request_at + _min_spacing() - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()
    try:
        response = curl_requests.get(
            _ITEM_URL.format(token=token),
            headers={"Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7"},
            impersonate="chrome",
            timeout=_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except Exception:
        return "retry", "request failed (network)"
    if response.status_code in (404, 410):
        return "gone", {}
    if response.status_code != 200:
        return "retry", f"answered HTTP {response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return "retry", "answered non-JSON (challenge page?)"
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return "retry", "answered JSON that is not the ad (bot-protection event / rate limit)"
    return "ok", data


def fetch_item(token: str) -> dict | None:
    """The ad record (`data`), `{}` when Yad2 says the ad is gone (404/410), or None when it could not be read right now."""
    global _consecutive_failures
    url = _ITEM_URL.format(token=token)
    with _lock:
        if time.monotonic() < _blocked_until:
            return None
        reason = ""
        for attempt in range(len(_RETRY_WAITS_SECONDS) + 1):
            if attempt:
                time.sleep(_RETRY_WAITS_SECONDS[attempt - 1])
            outcome, value = _request_once(token)
            if outcome != "retry":
                _consecutive_failures = 0
                return value
            reason = value
        _record_failure(url, reason + f" (after {len(_RETRY_WAITS_SECONDS) + 1} attempts)")
        return None


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _entrance_date(value: Any) -> dt.date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
    except ValueError:
        return None
    return parsed if 2000 <= parsed.year <= dt.date.today().year + 5 else None


def detail_updates_from_item(detail: dict[str, Any]) -> dict[str, Any]:
    """Listing-column updates from one ad record (`data`, or the older `__NEXT_DATA__` item — same inner shape).
    Purely additive and defensive: every read is type-checked, a field the record does not state is simply absent from
    the result (never guessed, never False-by-default). {} when nothing is usable."""
    updates: dict[str, Any] = {}

    additional = _dict(detail.get("additionalDetails"))
    in_property = _dict(detail.get("inProperty"))
    meta = _dict(detail.get("metaData"))
    customer = _dict(detail.get("customer"))

    property_field = _dict(additional.get("property"))
    property_eng = (property_field.get("textEng") or "").strip() if isinstance(property_field.get("textEng"), str) else ""
    property_text = (property_field.get("text") or "").strip() if isinstance(property_field.get("text"), str) else ""
    if property_eng in PROPERTY_TYPE_BY_ENG:
        updates["property_type"] = PROPERTY_TYPE_BY_ENG[property_eng]
    elif property_text in HEBREW_PROPERTY_TYPE_MAP:
        updates["property_type"] = HEBREW_PROPERTY_TYPE_MAP[property_text]

    for source_key, column in (
        ("includeParking", "has_parking"),
        ("includeElevator", "has_elevator"),
        ("includeBalcony", "has_balcony"),
        ("isPetsAllowed", "pets_allowed"),
        ("isRenovated", "is_renovated"),
        ("isForPartners", "is_roommate_friendly"),
    ):
        flag = _bool(in_property.get(source_key))
        if flag is not None:
            updates[column] = flag

    security_room = _bool(in_property.get("includeSecurityRoom"))
    building_shelter = _bool(in_property.get("includeBuildingShelter"))
    if security_room:
        updates["safe_room_type"] = "safe_room"
    elif building_shelter:
        updates["safe_room_type"] = "building_shelter"
    elif security_room is not None:
        updates["safe_room_type"] = "none"

    furniture = _bool(in_property.get("includeFurniture"))
    if furniture is not None:
        updates["furniture"] = "furnished" if furniture else "unfurnished"

    top_floor = additional.get("buildingTopFloor")
    if isinstance(top_floor, int) and not isinstance(top_floor, bool) and 0 <= top_floor <= 120:
        updates["floor_total"] = top_floor

    # Yad2 keeps an ad's original entrance date after it has passed, so a date that is today or earlier means "available
    # now": stored as the note "מיידית", never as move_in_date — matching.py rejects a listing whose move_in_date is
    # before a filter's earliest date, which would wrongly drop an ad that is open for any later date.
    entrance = _entrance_date(additional.get("entranceDate"))
    if entrance is not None and entrance > dt.date.today():
        updates["move_in_date"] = entrance
    elif entrance is not None or _bool(in_property.get("isImmediateEntrance")):
        updates["move_in_note"] = "מיידית"
    elif _bool(additional.get("isEnterDateFlexible")):
        updates["move_in_note"] = "גמיש"

    # searchText is a fallback, not the primary source — metaData.description is the human-written text.
    description = meta.get("description") or detail.get("searchText")
    if isinstance(description, str) and description.strip():
        updates["description"] = description.strip()[:_MAX_DESCRIPTION_CHARS]

    images = meta.get("images")
    if isinstance(images, list):
        real_images = [u for u in images if isinstance(u, str) and u.strip()]
        if real_images:
            updates["image_urls"] = real_images

    # An agency NAME is a confident positive signal; its absence is not evidence of a private listing.
    if customer.get("agencyName"):
        updates["is_broker_listing"] = True

    return updates


def fetch_yad2_detail_updates(url: str) -> dict | None:
    """See the module docstring's contract: {} / dict on a definitive answer, None when the caller should retry later."""
    if not is_enabled():
        return None
    token = token_from_url(url)
    if token is None:
        return None
    record = fetch_item(token)
    if record is None:
        return None
    return detail_updates_from_item(record)
