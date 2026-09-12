"""Bright Data Web Scraper API (datasets v3) client — fetches a Yad2 listing's own detail-page data
for ONE listing at a time, ON DEMAND, only when it's worth the cost. Moved here from scraper/
(2026-09-07) so website/main.py can call it too — the scraper and website pods are separate Docker
images (see their own Dockerfiles), each copying only common/dorin_common/ plus their own
directory, so a module used by both has to live here.

Two functions, same underlying trigger/poll/snapshot mechanics (`_trigger_and_fetch_first_row`):
`fetch_listing_description` (original) extracts just the free-text description string.
`fetch_listing_detail_via_bright_data` (2026-09-12) returns the WHOLE raw record, for callers that
want everything `normalize.enrich_from_detail` can use (property type, amenities, floor_total,
move-in date, broker status), not just the description text — see that function's own docstring.

`fetch_listing_description`'s two call sites, same "never speculative" principle, different
trigger: scraper/notifier.py calls it only for a listing that just matched at least one PAYING
user's filter at discovery time (see that module's own comment) — the exact sequencing Amir asked
for (match first, THEN decide whether to spend a fetch on it). website/main.py's /apartments and
/liked calls it lazily, in the background, for any already-matched listing a paying viewer is
about to see whose description is still missing. Either way the result caches on
Listing.description forever, so the real cost is bounded by distinct listings ever actually seen
by a paying user, never the full scrape volume and never repeated per viewer.
(`fetch_listing_detail_via_bright_data` isn't wired into either call site yet — see its own
docstring and PROJECT_STATE.md for the different, discovery-time trigger it's meant for instead.)

⚠️ PARTIALLY VERIFIED. The trigger/progress/snapshot flow below is read from Bright Data's own
public GitHub reference (github.com/brightdata/skills, web-scraper-api.md — docs.brightdata.com
itself is blocked by this sandbox's network egress, same restriction hit with Grow/Meshulam, see
website/grow_client.py's own docstring), so the ENDPOINTS/REQUEST SHAPE are real, not guessed.
The snapshot RECORD SHAPE, on the other hand, is now real and confirmed — not guessed — for a Yad2
listing detail page specifically: field names like `additionalDetails`, `inProperty`, `metaData`,
`customer`, `searchText` were read live off real listings via a Bright Data Scraper Studio
collector's own Parser code, not invented (see PROJECT_STATE.md's 2026-09-11/12 entries). What's
still genuinely unknown here is only account-specific, not shape-specific:
  - BRIGHT_DATA_DATASET_ID has no value here on purpose — the Web Scraper API is dataset/scraper-
    specific, not a generic "fetch any URL" endpoint. Needs that Scraper Studio collector actually
    published to production with a real dataset_id, which goes in this env var.
  - The snapshot JSON's field name for the description text, if it differs from the confirmed
    `description`/`searchText` (e.g. a custom Parser output schema uses another name) —
    BRIGHT_DATA_DESCRIPTION_FIELD lets the owner override it; this also tries the confirmed
    fallback keys either way.
Both BRIGHT_DATA_API_KEY and BRIGHT_DATA_DATASET_ID are required together; unset (the default) =
both functions always return None immediately, same as before this feature existed.
"""
from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

API_KEY_ENV_VAR = "BRIGHT_DATA_API_KEY"
DATASET_ID_ENV_VAR = "BRIGHT_DATA_DATASET_ID"
DESCRIPTION_FIELD_ENV_VAR = "BRIGHT_DATA_DESCRIPTION_FIELD"

_TRIGGER_URL = "https://api.brightdata.com/datasets/v3/trigger"
_PROGRESS_URL = "https://api.brightdata.com/datasets/v3/progress/{snapshot_id}"
_SNAPSHOT_URL = "https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}"
_REQUEST_TIMEOUT_SECONDS = 15.0
_POLL_INTERVAL_SECONDS = 3.0
# A scrape run shouldn't hang indefinitely on one slow fetch — 45s is a guess at "generous but
# bounded", not a documented Bright Data SLA (async jobs have "no stated limit" per the reference
# above). Times out to None (same as any other failure) rather than blocking the run forever.
_POLL_TIMEOUT_SECONDS = 45.0


def is_configured() -> bool:
    return bool(
        os.environ.get(API_KEY_ENV_VAR, "").strip()
        and os.environ.get(DATASET_ID_ENV_VAR, "").strip()
    )


def _trigger_and_fetch_first_row(url: str) -> dict | None:
    """Shared trigger -> poll -> snapshot mechanics for both fetch_listing_description and
    fetch_listing_detail_via_bright_data (2026-09-12 addition) — same Bright Data datasets/v3 API,
    same blocking/synchronous contract, same "never raises" guarantee. Returns the first row of the
    snapshot as a plain dict, or None on missing config, any request failure, a "failed" snapshot,
    a poll timeout, an empty snapshot, or a non-dict row — every failure mode collapses to None so
    callers never need their own separate error handling."""
    api_key = os.environ.get(API_KEY_ENV_VAR, "").strip()
    dataset_id = os.environ.get(DATASET_ID_ENV_VAR, "").strip()
    if not (api_key and dataset_id):
        return None

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        trigger_resp = httpx.post(
            _TRIGGER_URL,
            params={"dataset_id": dataset_id, "format": "json"},
            json={"input": [{"url": url}]},
            headers=headers,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        trigger_resp.raise_for_status()
        snapshot_id = trigger_resp.json()["snapshot_id"]
    except (httpx.HTTPError, KeyError, ValueError):
        logger.exception("Bright Data trigger call failed for %s", url)
        return None

    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    status = None
    while time.monotonic() < deadline:
        try:
            progress_resp = httpx.get(
                _PROGRESS_URL.format(snapshot_id=snapshot_id), headers=headers,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            progress_resp.raise_for_status()
            status = progress_resp.json().get("status")
        except (httpx.HTTPError, ValueError):
            logger.exception("Bright Data progress poll failed for snapshot %s (%s)", snapshot_id, url)
            return None
        if status in ("ready", "failed"):
            break
        time.sleep(_POLL_INTERVAL_SECONDS)

    if status != "ready":
        logger.error(
            "Bright Data snapshot %s for %s did not become ready in time (last status=%s)",
            snapshot_id, url, status,
        )
        return None

    try:
        snapshot_resp = httpx.get(
            _SNAPSHOT_URL.format(snapshot_id=snapshot_id),
            params={"format": "json"},
            headers=headers,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        snapshot_resp.raise_for_status()
        rows = snapshot_resp.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Bright Data snapshot fetch failed for %s (%s)", snapshot_id, url)
        return None

    logger.info("Bright Data raw snapshot for %s: %r", url, rows)
    if not rows:
        return None
    row = rows[0] if isinstance(rows, list) else rows
    return row if isinstance(row, dict) else None


def fetch_listing_description(url: str) -> str | None:
    """Synchronous and BLOCKING (real network calls + a polling wait) — callers on an event loop
    MUST run this via asyncio.to_thread, same as every other blocking call in this codebase (see
    e.g. dorin_common/cards.py's _build_collage_sync docstring for why). Returns None on missing
    config, any request failure, a "failed" snapshot, or a poll timeout — never raises, and a
    listing is always still sent without a description exactly as it always could before this
    feature existed, never blocked on this call succeeding."""
    row = _trigger_and_fetch_first_row(url)
    if row is None:
        return None

    field = (os.environ.get(DESCRIPTION_FIELD_ENV_VAR, "").strip()) or "description"
    # searchText added 2026-09-12: confirmed live (see PROJECT_STATE.md) as a second, DIFFERENT
    # real free-text field on a Yad2 listing detail page's own __NEXT_DATA__, alongside
    # metaData.description — a defensive fallback, not a fix (description already worked).
    description = (
        row.get(field) or row.get("description") or row.get("searchText")
        or row.get("text") or row.get("content")
    )
    return description.strip() if isinstance(description, str) and description.strip() else None


def fetch_listing_detail_via_bright_data(url: str) -> dict | None:
    """2026-09-12 addition. Returns the FULL raw listing record from Bright Data's Scraper Studio
    `yad2.co.il` collector (address, additionalDetails, inProperty, metaData, customer, price,
    token, searchText, etc — field names confirmed live against real listings, see
    PROJECT_STATE.md's 2026-09-11/12 entries), ready to pass straight into
    `normalize.enrich_from_detail` as its `detail` argument — that function already expects exactly
    this shape (it was built against ZenRows' fetch_listing_detail, which reads the SAME underlying
    Yad2 __NEXT_DATA__, just via different scraping infrastructure; the field names line up).

    Unlike fetch_listing_description (which discards everything but one text field), this keeps
    the whole record: enrich_from_detail also wants property type, amenity booleans, floor_total,
    move-in date, and broker status from the same payload, not just the description text.

    Same blocking/synchronous contract as fetch_listing_description (run via asyncio.to_thread on
    an event loop) and the same "never raises, None on any failure" guarantee — a listing missing
    Bright Data enrichment is simply a listing enrich_from_detail is never called for, exactly the
    same degrade-gracefully behavior this file's other function already has.

    NOT yet called from anywhere in the scrape path — see PROJECT_STATE.md for the trigger
    mechanism this is meant to plug into (per-new-external_id, at discovery time) and what's still
    unbuilt before this is wired in for real."""
    return _trigger_and_fetch_first_row(url)
