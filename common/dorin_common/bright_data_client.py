"""Bright Data **Data Collector API** (`/dca/...`) client — fetches a Yad2 listing's own detail-
page data for ONE listing at a time, ON DEMAND, only when it's worth the cost. Moved here from
scraper/ (2026-09-07) so website/main.py can call it too — the scraper and website pods are
separate Docker images (see their own Dockerfiles), each copying only common/dorin_common/ plus
their own directory, so a module used by both has to live here.

Two functions, same underlying trigger/poll mechanics (`_trigger_and_fetch_first_row`):
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

⚠️ CORRECTED 2026-09-12, now REAL not guessed. An earlier version of this file (same date) guessed
at the "Web Scraper API" (`datasets/v3/...`) based on Bright Data's public GitHub reference —
**wrong product**. The actual collector built and tested live tonight (a Scraper Studio "custom
code" collector) uses the older **Data Collector API** instead, confirmed directly off that
collector's own "Initiate by API" tab (not a doc guess):
  - Trigger: `POST https://api.brightdata.com/dca/trigger?collector={COLLECTOR_ID}&queue_next=1`,
    body `[{"url": ...}]`, header `Authorization: Bearer {API_KEY}` — starts a job, returns some
    job/collection id in the response body (exact key name not yet independently confirmed against
    real JSON, only seen in a curl example — tried defensively below against a few plausible names,
    same hedge-with-fallback-keys approach as the description field already uses).
  - Retrieve: `GET https://api.brightdata.com/dca/dataset?id={JOB_ID}` — returns the result once
    the job (a real browser page visit) has finished; empty/absent while still running, so this is
    polled the same way the old snapshot-status endpoint was.
The collector's RECORD SHAPE, unlike the endpoints, was already real and confirmed before this
correction — not guessed — for a Yad2 listing detail page specifically: field names like
`additionalDetails`, `inProperty`, `metaData`, `customer`, `searchText` were read live off real
listings via that collector's own Parser code (see PROJECT_STATE.md's 2026-09-11/12 entries).

What's still genuinely unknown here is account-specific, not shape-specific:
  - BRIGHT_DATA_COLLECTOR_ID has no value here on purpose — needs the owner's own collector id
    (`c_...`, visible on its "Initiate by API" tab) filled in.
  - The trigger response's real job-id field name, if it turns out not to be one of the fallback
    keys tried — the first real trigger call's raw response is logged either way, so that's easy to
    add once seen.
  - The snapshot JSON's field name for the description text, if it differs from the confirmed
    `description`/`searchText` (e.g. a custom Parser output schema uses another name) —
    BRIGHT_DATA_DESCRIPTION_FIELD lets the owner override it; this also tries the confirmed
    fallback keys either way.
Both BRIGHT_DATA_API_KEY and BRIGHT_DATA_COLLECTOR_ID are required together; unset (the default) =
both functions always return None immediately, same as before this feature existed.

2026-09-13: added fetch_via_web_unlocker — a SEPARATE Bright Data product (Web Unlocker API,
POST api.brightdata.com/request) from the Data Collector API above. The DCA collector is tied to
one pre-built Scraper Studio "custom code" collector configured specifically to parse a Yad2
listing DETAIL page's DOM — useless for any other URL shape. Web Unlocker is generic: "fetch this
exact URL through our unlocking infrastructure, hand back the raw response" — no per-site collector
needed. Confirmed live against real Yad2 URLs the owner found needed it (both a full rendered
search-results page and gw.yad2.co.il's JSON map API, both blocked by ZenRows' own REQS002 at every
tier tried — see .github/workflows/diagnose-yad2-map-api-cost.yaml and
diagnose-yad2-bright-data-cost.yaml): both succeeded (HTTP 200, real data) through a Web Unlocker
zone named "web_unlocker1" (Bright Data's own default zone name for this product, created live in
the owner's dashboard the same day) — $1.50 per 1,000 SUCCESSFUL requests only, per that dashboard's
own pricing (confirmed live, not a doc guess). Uses the SAME BRIGHT_DATA_API_KEY as the DCA
functions above — one Bright Data account, multiple products/zones under it, not a second key.
"""
from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

API_KEY_ENV_VAR = "BRIGHT_DATA_API_KEY"
COLLECTOR_ID_ENV_VAR = "BRIGHT_DATA_COLLECTOR_ID"
DESCRIPTION_FIELD_ENV_VAR = "BRIGHT_DATA_DESCRIPTION_FIELD"
# 2026-09-13: only needed by fetch_via_web_unlocker (a different product from the DCA collector
# above) — defaults to "web_unlocker1", Bright Data's own default zone name for this product,
# confirmed live in the owner's own dashboard the same day this was added. Override only if the
# owner ever creates/uses a differently-named Web Unlocker zone.
WEB_UNLOCKER_ZONE_ENV_VAR = "BRIGHT_DATA_WEB_UNLOCKER_ZONE"
_DEFAULT_WEB_UNLOCKER_ZONE = "web_unlocker1"

_TRIGGER_URL = "https://api.brightdata.com/dca/trigger"
_RESULT_URL = "https://api.brightdata.com/dca/dataset"
_WEB_UNLOCKER_URL = "https://api.brightdata.com/request"
# Confirmed live 2026-09-13: a real Yad2 full-page fetch took ~9s, the JSON map API ~5s, end to end
# through Web Unlocker's own real-browser rendering — 90s leaves generous headroom without letting
# one hung request block a scrape run indefinitely.
_WEB_UNLOCKER_TIMEOUT_SECONDS = 90.0
_REQUEST_TIMEOUT_SECONDS = 15.0
_POLL_INTERVAL_SECONDS = 3.0
# A scrape run shouldn't hang indefinitely on one slow fetch — 60s is a guess at "generous but
# bounded" for a job that does a real browser page visit (confirmed live tonight to reliably take
# well under this), not a documented Bright Data SLA. Times out to None (same as any other
# failure) rather than blocking the run forever.
_POLL_TIMEOUT_SECONDS = 60.0


def is_configured() -> bool:
    return bool(
        os.environ.get(API_KEY_ENV_VAR, "").strip()
        and os.environ.get(COLLECTOR_ID_ENV_VAR, "").strip()
    )


def _extract_job_id(body: object) -> str | None:
    """The trigger response's real job/collection-id field name wasn't independently confirmed
    against actual JSON (only seen in Bright Data's own curl example on the collector's "Initiate
    by API" tab) — tries the plausible candidates rather than guess a single one blind, same hedge
    this file already applies to the description field name."""
    candidate = body
    if isinstance(candidate, list) and candidate:
        candidate = candidate[0]
    if not isinstance(candidate, dict):
        return None
    for key in ("collection_id", "response_id", "job_id", "id"):
        value = candidate.get(key)
        if value:
            return str(value)
    return None


def _trigger_and_fetch_first_row(url: str) -> dict | None:
    """Shared trigger -> poll mechanics for both fetch_listing_description and
    fetch_listing_detail_via_bright_data (2026-09-12 addition) — same Bright Data Data Collector
    API, same blocking/synchronous contract, same "never raises" guarantee. Returns the first row
    of the result as a plain dict, or None on missing config, any request failure, an
    unrecognizable trigger response, a poll timeout, an empty result, or a non-dict row — every
    failure mode collapses to None so callers never need their own separate error handling."""
    api_key = os.environ.get(API_KEY_ENV_VAR, "").strip()
    collector_id = os.environ.get(COLLECTOR_ID_ENV_VAR, "").strip()
    if not (api_key and collector_id):
        return None

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        trigger_resp = httpx.post(
            _TRIGGER_URL,
            params={"collector": collector_id, "queue_next": "1"},
            json=[{"url": url}],
            headers=headers,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        trigger_resp.raise_for_status()
        job_id = _extract_job_id(trigger_resp.json())
    except (httpx.HTTPError, ValueError):
        logger.exception("Bright Data DCA trigger call failed for %s", url)
        return None

    if job_id is None:
        logger.error(
            "Bright Data DCA trigger response for %s had no recognizable job id: %r",
            url, trigger_resp.text,
        )
        return None

    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    rows = None
    while time.monotonic() < deadline:
        try:
            result_resp = httpx.get(
                _RESULT_URL, params={"id": job_id}, headers=headers,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            result_resp.raise_for_status()
            rows = result_resp.json()
        except (httpx.HTTPError, ValueError):
            logger.exception("Bright Data DCA result poll failed for job %s (%s)", job_id, url)
            return None
        if rows:
            break
        time.sleep(_POLL_INTERVAL_SECONDS)

    if not rows:
        logger.error(
            "Bright Data DCA job %s for %s did not produce a result in time", job_id, url,
        )
        return None

    logger.info("Bright Data DCA raw result for %s: %r", url, rows)
    row = rows[0] if isinstance(rows, list) else rows
    return row if isinstance(row, dict) else None


def fetch_listing_description(url: str) -> str | None:
    """Synchronous and BLOCKING (real network calls + a polling wait) — callers on an event loop
    MUST run this via asyncio.to_thread, same as every other blocking call in this codebase (see
    e.g. dorin_common/cards.py's _build_collage_sync docstring for why). Returns None on missing
    config, any request failure, or a poll timeout — never raises, and a listing is always still
    sent without a description exactly as it always could before this feature existed, never
    blocked on this call succeeding."""
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


def fetch_via_web_unlocker(url: str, *, zone: str | None = None) -> str | None:
    """2026-09-13 addition. Fetches ANY url through Bright Data's Web Unlocker API (a single POST,
    no trigger/poll dance — see module docstring for why this is a different product from the DCA
    functions above, and what's already been confirmed live against real Yad2 URLs). Returns the
    raw response body as text on HTTP 200, or None on missing API key, any request failure, or a
    non-200 status — never raises, same "never blocks the caller on a failure" contract as every
    other function in this file.

    `zone` defaults to _DEFAULT_WEB_UNLOCKER_ZONE ("web_unlocker1") or the
    BRIGHT_DATA_WEB_UNLOCKER_ZONE env var if set — override only for an account with a
    differently-named zone. Only BRIGHT_DATA_API_KEY is required (no separate config needed to use
    this vs. the DCA functions above — same account, same key, different Bright Data product)."""
    api_key = os.environ.get(API_KEY_ENV_VAR, "").strip()
    if not api_key:
        return None
    zone_name = zone or os.environ.get(WEB_UNLOCKER_ZONE_ENV_VAR, "").strip() or _DEFAULT_WEB_UNLOCKER_ZONE

    try:
        response = httpx.post(
            _WEB_UNLOCKER_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"zone": zone_name, "url": url, "format": "raw"},
            timeout=_WEB_UNLOCKER_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError:
        logger.exception("Bright Data Web Unlocker request failed for %s", url)
        return None

    if response.status_code != 200:
        logger.warning(
            "Bright Data Web Unlocker returned non-200 for %s: zone=%r status=%d body=%r",
            url, zone_name, response.status_code, response.text[:500],
        )
        return None

    return response.text
