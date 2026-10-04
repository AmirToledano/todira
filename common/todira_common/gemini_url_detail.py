"""Yad2 listing details via Gemini's `url_context` tool — a (nearly) free replacement for Bright Data
Web Unlocker's per-listing detail fetch (2026-10-04).

Why this works: Gemini's API can fetch a public URL ITSELF, from Google's servers, so Yad2's Radware
challenge that blocks our cloud IP (and plain HTTP clients) doesn't apply. Verified live from the
production pod with the project's existing free-tier key (diagnose-gemini-url-context-*.yaml, 2026-10-03/04):
19 of 20 listing pages retrieved (the rest were 429/503), description identical to the Bright Data copy
in the DB up to whitespace, and floor / parking / elevator / balcony / safe-room matched 100%. Each call
costs ~250-400 input tokens (free tier: no charge). It does NOT work for Yad2's map API (retrieval error),
which is why that is fetched separately (scraper/yad2_client.py).

What it can't give: photos (the map API already carries them), property type, broker flag. Entrance date is
only returned when it is a FUTURE date shown on the page (a past/immediate date renders as "immediate" and
comes back null — which is exactly how the card treats a missing date, so nothing is lost).

Safety: opt-in via YAD2_DETAIL_VIA_GEMINI=true; callers always fall back to Web Unlocker when this returns
None. A 429 (free-tier rate limit) opens a circuit breaker for a few minutes so a burst doesn't hammer the
quota. Only public listing URLs are sent (no user data) — relevant because free-tier prompts may be used by
Google to improve its products. Never raises."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

ENABLED_ENV_VAR = "YAD2_DETAIL_VIA_GEMINI"
MODEL_ENV_VAR = "YAD2_GEMINI_MODEL"
_DEFAULT_MODEL = "gemini-3.6-flash"
_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_TIMEOUT_SECONDS = 90.0
_RATE_LIMIT_PAUSE_SECONDS = 600.0
_MAX_DESCRIPTION_CHARS = 4000

_PROMPT = (
    "Open the URL with your URL-context tool and read the apartment listing. Return ONLY JSON with keys: "
    '"description" (the listing description text, verbatim), "building_top_floor" (integer or null), '
    '"entrance_date" (YYYY-MM-DD, or null if immediate/flexible/not shown), "parking" (true/false/null), '
    '"elevator" (true/false/null), "balcony" (true/false/null), "safe_room" (true/false/null), "ok" (true). '
    'If you could not actually open the page return {"ok": false}. NEVER guess or invent; use null when the '
    "page does not say."
)

# monotonic deadline until which Gemini is skipped after a 429
_paused_until = 0.0


def is_enabled() -> bool:
    return (
        os.environ.get(ENABLED_ENV_VAR, "").strip().lower() == "true"
        and bool(os.environ.get("GEMINI_API_KEY", "").strip())
    )


def _as_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _parse_updates(payload: dict, today: dt.date) -> dict | None:
    candidates = payload.get("candidates") or []
    cand = candidates[0] if candidates else {}
    metadata = (cand.get("urlContextMetadata") or {}).get("urlMetadata") or []
    if [m.get("urlRetrievalStatus") for m in metadata] != ["URL_RETRIEVAL_STATUS_SUCCESS"]:
        return None
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    try:
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("ok") is not True:
        return None

    updates: dict = {}
    description = data.get("description")
    if isinstance(description, str) and description.strip():
        updates["description"] = description.strip()[:_MAX_DESCRIPTION_CHARS]
    floor_total = data.get("building_top_floor")
    if isinstance(floor_total, int) and not isinstance(floor_total, bool) and 0 <= floor_total <= 120:
        updates["floor_total"] = floor_total
    for src, column in (("parking", "has_parking"), ("elevator", "has_elevator"), ("balcony", "has_balcony")):
        flag = _as_bool(data.get(src))
        if flag is not None:
            updates[column] = flag
    safe_room = _as_bool(data.get("safe_room"))
    if safe_room is not None:
        updates["safe_room_type"] = "safe_room" if safe_room else "none"
    entrance = data.get("entrance_date")
    if isinstance(entrance, str):
        try:
            parsed = dt.date.fromisoformat(entrance)
        except ValueError:
            parsed = None
        if parsed is not None and parsed > today:
            updates["move_in_date"] = parsed
    return updates or None


def fetch_yad2_detail_updates(url: str) -> dict | None:
    """Column->value updates for a Listing row, or None (not enabled, rate-limited, page not retrieved,
    unparseable, nothing usable). Only fields the page actually states are included."""
    global _paused_until
    if not is_enabled() or time.monotonic() < _paused_until:
        return None
    model = os.environ.get(MODEL_ENV_VAR, "").strip() or _DEFAULT_MODEL
    body = {
        "contents": [{"parts": [{"text": f"{_PROMPT}\n\nURL: {url}"}]}],
        "tools": [{"url_context": {}}],
        "generationConfig": {"temperature": 0},
    }
    try:
        response = httpx.post(
            _URL.format(model=model),
            headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"].strip(), "Content-Type": "application/json"},
            json=body,
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError:
        logger.warning("Gemini URL-context request failed (network) for %s", url)
        return None
    if response.status_code == 429:
        _paused_until = time.monotonic() + _RATE_LIMIT_PAUSE_SECONDS
        logger.warning("Gemini free-tier rate limit hit — skipping Gemini for %.0f min", _RATE_LIMIT_PAUSE_SECONDS / 60)
        return None
    if response.status_code != 200:
        logger.warning("Gemini URL-context returned HTTP %s for %s", response.status_code, url)
        return None
    try:
        return _parse_updates(response.json(), dt.date.today())
    except (ValueError, AttributeError, TypeError):
        logger.warning("Gemini URL-context response unparseable for %s", url)
        return None
