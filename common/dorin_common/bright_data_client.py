"""Bright Data Web Scraper API (datasets v3) client — fetches the full listing-detail page content
(specifically the description text) for ONE listing at a time, ON DEMAND, only when it's worth the
cost. Moved here from scraper/ (2026-09-07) so website/main.py can call it too — the scraper and
website pods are separate Docker images (see their own Dockerfiles), each copying only
common/dorin_common/ plus their own directory, so a module used by both has to live here.

Two call sites, same "never speculative" principle, different trigger: scraper/notifier.py calls
this only for a listing that just matched at least one PAYING user's filter at discovery time (see
that module's own comment) — the exact sequencing Amir asked for (match first, THEN decide whether
to spend a fetch on it). website/main.py's /apartments and /liked calls this lazily, in the
background, for any already-matched listing a paying viewer is about to see whose description is
still missing — covers listings whose paying match happened AFTER discovery (a filter edit, a new
subscription) that the discovery-time trigger alone would otherwise never fetch. Either way the
result caches on Listing.description forever, so the real cost is bounded by distinct listings ever
actually seen by a paying user, never the full scrape volume and never repeated per viewer.

⚠️ PARTIALLY VERIFIED. The trigger/progress/snapshot flow below is read from Bright Data's own
public GitHub reference (github.com/brightdata/skills, web-scraper-api.md — docs.brightdata.com
itself is blocked by this sandbox's network egress, same restriction hit with Grow/Meshulam, see
website/grow_client.py's own docstring), so the ENDPOINTS/REQUEST SHAPE are real, not guessed.

What's still genuinely unknown, and can't be resolved without the owner's own account:
  - BRIGHT_DATA_DATASET_ID has no value here on purpose — the Web Scraper API is dataset/scraper-
    specific, not a generic "fetch any URL" endpoint. The owner needs a Bright Data "scraper" built
    in Scraper Studio that targets a Yad2 LISTING DETAIL page (not the search-results page his
    existing, already-diagnosed-as-broken scraper targets — see PROJECT_STATE.md's brittle-
    CSS-selector history) and extracts its description text. Its dataset_id goes in this env var.
  - The snapshot JSON's field name for the extracted description text is whatever that scraper's
    own output schema calls it — BRIGHT_DATA_DESCRIPTION_FIELD lets the owner set the real name;
    this also tries a few common fallback keys and logs the full raw snapshot either way, so the
    first real fetch shows exactly what to configure.
Both BRIGHT_DATA_API_KEY and BRIGHT_DATA_DATASET_ID are required together; unset (the default) =
fetch_listing_description always returns None immediately, same as before this feature existed.
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


def fetch_listing_description(url: str) -> str | None:
    """Synchronous and BLOCKING (real network calls + a polling wait) — callers on an event loop
    MUST run this via asyncio.to_thread, same as every other blocking call in this codebase (see
    e.g. dorin_common/cards.py's _build_collage_sync docstring for why). Returns None on missing
    config, any request failure, a "failed" snapshot, or a poll timeout — never raises, and a
    listing is always still sent without a description exactly as it always could before this
    feature existed, never blocked on this call succeeding."""
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
    if not isinstance(row, dict):
        return None

    field = (os.environ.get(DESCRIPTION_FIELD_ENV_VAR, "").strip()) or "description"
    description = row.get(field) or row.get("description") or row.get("text") or row.get("content")
    return description.strip() if isinstance(description, str) and description.strip() else None
