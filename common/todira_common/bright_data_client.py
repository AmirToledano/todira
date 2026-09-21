"""Bright Data **Data Collector API** (`/dca/...`) client — fetches a Yad2 listing's own detail-
page data for ONE listing at a time, ON DEMAND, only when it's worth the cost. Moved here from
scraper/ (2026-09-07) so website/main.py can call it too — the scraper and website pods are
separate Docker images (see their own Dockerfiles), each copying only common/todira_common/ plus
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
  - Trigger: `POST https://api.brightdata.com/dca/trigger?collector={COLLECTOR_ID}`,
    body `[{"url": ...}]`, header `Authorization: Bearer {API_KEY}` — starts a job, returns
    `{"collection_id": "...", "start_eta": "..."}` (confirmed live 2026-09-13, see below — the
    other fallback key names in `_extract_job_id` are kept as defensive hedges, not because any
    have actually been seen). The curl example this was originally copied from also included
    `&queue_next=1`; REMOVED 2026-09-13 after it turned out to be exactly why every trigger call
    was failing — see the "trial collectors" entry further down.
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

BUT: real production use of fetch_via_web_unlocker hit a wall the very same day — Bright Data's own
"Residential Failed (bad_endpoint): ... no KYC access mode in accordance with robots.txt" error for
EVERY bbox/param variation except the one exact URL already lucky-tested (see
diagnose-yad2-map-api-coverage.yaml) — full KYC needs a company email the owner didn't have yet.

2026-09-13, same day: added fetch_via_isp_proxy as the WORKING alternative — a THIRD, different
Bright Data product (plain ISP proxies: real IPs with residential reputation but hosted in
datacenters, reached via a classic authenticated HTTP proxy, not an API wrapper). Confirmed live
(see .github/workflows/diagnose-yad2-isp-proxy.yaml) to have NO KYC gate at all ("start
immediately — no verification, no domain restrictions" per Bright Data's own dashboard) and to
successfully fetch gw.yad2.co.il's map API with real data (200 markers, real prices) — because that
endpoint is pure JSON needing no JS rendering, the earlier Web Unlocker block was Bright Data's own
residential-KYC classification specifically, not anything Yad2-side. The SAME proxy against
www.yad2.co.il's own full HTML search page came back 200 (not blocked at the network/IP level
either) but genuinely empty of real listing cards — consistent with this project's own
already-documented understanding (yad2_client.py's module docstring, attempts 1-8) that Yad2's own
search page needs real JS execution to render its cards at all, a separate problem a plain proxy
(no browser) was never going to solve on its own — not a concern for fetch_map_markers's purposes,
since the map API alone already carries everything needed.

Real cost: a flat $2/month per IP ("unlimited usage subject to Bright Data's fair use policy"), NOT
metered per request like Web Unlocker or ZenRows — confirmed live via the owner's own Bright Data
dashboard, the cheapest of every option this project has tried for Yad2 by a wide margin. Needs
THREE new env vars (a proxy's own host/user/pass, not an API key): BRIGHT_DATA_ISP_HOST (e.g.
"brd.superproxy.io:44445"), BRIGHT_DATA_ISP_USER, BRIGHT_DATA_ISP_PASS — all set together or this
function is unconfigured (returns None immediately, same contract as every other function here).

2026-09-13: the DCA trigger call (fetch_listing_detail_via_bright_data, and therefore every real
Yad2 description) had been silently failing 100% of the time in production — the first real scrape
run since this was wired in (safe-single-test-run.yaml) logged `bright_data_enriched: 0` out of 85
new listings, every single trigger call raising an httpx.HTTPStatusError that was logged WITHOUT
its response body (see _trigger_and_fetch_first_row's old except clause), so the real reason was
never actually visible. Replaying the exact same request directly (diagnose-bright-data-dca-400.yaml)
found it immediately: `{"error":"Trial collectors don't support queuing jobs"}` — this account's
collector is still on Bright Data's trial tier, which flatly rejects the `queue_next=1` param the
trigger URL was sending (a leftover from the curl example this was originally copied from, never
actually needed — one URL per call, not a batch). Removing it confirmed live: real 200,
`{"collection_id": "j_...", "start_eta": "..."}`. Fixed in both places: the param is gone, and the
except clause now always logs the response body on a 4xx/5xx, so a future rejection reason (e.g.
if the collector is ever upgraded off the trial tier and something else changes) is visible from
the next real production log line instead of needing another live replay to discover.

2026-09-14: found the NEXT reason `bright_data_enriched` was still 0 even after the fix above —
the queue_next fix made trigger calls succeed (real 200s, real job ids), but the poll loop's own
`if rows: break` treated ANY non-empty poll response as "the job is done". A real still-processing
poll returns a non-empty STATUS dict too — confirmed real from a production run's own logs (hours
of `{"status": "collecting", "message": "Job is not finished"}` / `{"status": "building", "message":
"Dataset is not ready yet, try again in 30s"}` entries) — not an empty list as the loop had always
assumed. So the very first poll (often under a second after triggering) broke out immediately with
that status object mistaken for the real record, which downstream code found no usable fields in —
every single enrichment silently failing despite the trigger call itself genuinely succeeding. A
real run that night: `bright_data_enriched: 0` out of 994 new Yad2 listings, after ~3 hours of
continuous trigger/poll activity that never actually produced one real result. Fixed by
`_looks_like_pending_status` — see that function's own docstring and the poll loop's own comment.

2026-09-14, same day, later: the fix above made enrichment actually WORK — and immediately
surfaced a THIRD, worse bug once it did: the owner's own live notifications started carrying
another listing's photos and description. Caught live from real screenshots (different addresses,
prices, and room counts, but identical photos and description text down to the word — including a
"2.5 rooms" description on a listing whose own fields said 4.0). Root cause never confirmed against
Bright Data support (no access to their side), but the working theory: this collector is still on
the trial tier (see the `queue_next` entry above), and its result buffer doesn't reliably scope by
job id under concurrent triggers (`_BRIGHT_DATA_ENRICH_CONCURRENCY` in scraper/main.py runs several
at once) — a poll for job A's `id` can hand back job B's already-collected page. Fixed defensively
in `_trigger_and_fetch_first_row`, not by chasing the trial-tier theory further: every real Yad2
item URL ends in its own external_id/adNumber, and the collector's own record separately carries
that same number back — so a mismatch is provably a wrong-listing result, discarded before it ever
reaches a row, same as any other failed fetch. The currently-running catch-up job that surfaced
this was killed via emergency-stop-scraper.yaml the moment the pattern was confirmed, before this
fix could reach it (it was already running on an older pinned image) — whatever it re-sends on its
next real run will go through this check.
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

# 2026-09-13: only needed by fetch_via_isp_proxy — a plain authenticated HTTP proxy (a Bright Data
# "ISP proxies" zone), not an API key/zone-name pair like the two products above. All three must be
# set together (host, username, password of one specific proxy zone the owner created) or this
# function is unconfigured — see its own docstring for why this exists (Web Unlocker's real KYC
# wall) and what it costs ($2/month flat, not per-request).
ISP_PROXY_HOST_ENV_VAR = "BRIGHT_DATA_ISP_HOST"
ISP_PROXY_USER_ENV_VAR = "BRIGHT_DATA_ISP_USER"
ISP_PROXY_PASS_ENV_VAR = "BRIGHT_DATA_ISP_PASS"

_TRIGGER_URL = "https://api.brightdata.com/dca/trigger"
_RESULT_URL = "https://api.brightdata.com/dca/dataset"
_WEB_UNLOCKER_URL = "https://api.brightdata.com/request"
# Confirmed live 2026-09-13: a real Yad2 full-page fetch took ~9s, the JSON map API ~5s, end to end
# through Web Unlocker's own real-browser rendering — 90s leaves generous headroom without letting
# one hung request block a scrape run indefinitely.
_WEB_UNLOCKER_TIMEOUT_SECONDS = 90.0
# Confirmed live 2026-09-13: a real gw.yad2.co.il map-API fetch through the ISP proxy took ~1.1s
# (no browser rendering involved at all, unlike Web Unlocker) — 60s still leaves generous headroom.
_ISP_PROXY_TIMEOUT_SECONDS = 60.0
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


def _looks_like_pending_status(rows: object) -> bool:
    """True for a "still processing" poll response — NOT a real result, even though it's a
    non-empty (truthy) dict. Confirmed real 2026-09-14 (a production run's own logs, hours of
    identical entries): `{"status": "collecting", "message": "Job is not finished"}` and
    `{"status": "building", "message": "Dataset is not ready yet, try again in 30s"}` — a real
    completed record NEVER has this shape (confirmed real, PROJECT_STATE.md 2026-09-11: top-level
    keys like token/price/additionalDetails/inProperty/searchText/customer/..., never "status" or
    "message"). See the poll loop's own comment for the real bug this fixes."""
    return isinstance(rows, dict) and bool(rows) and set(rows.keys()) <= {"status", "message"}


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


_ATTEMPTS = 2  # see _trigger_and_fetch_first_row's own docstring for why


def _trigger_and_fetch_first_row(url: str) -> dict | None:
    """Retries _trigger_and_fetch_first_row_once up to _ATTEMPTS times, returning the first
    successful row or None if every attempt failed. 2026-09-14: added the SAME day the adNumber
    cross-contamination check went in (see that check's own comment in the "once" function below)
    — a fresh trigger call gets a brand-new job id, which the working theory says is exactly what
    sidesteps whatever shared-result-buffer confusion produced a wrong-listing row the first time,
    so a second attempt has a real chance of getting this listing's OWN data rather than repeating
    the same failure. Also gives genuinely transient failures (a dropped request, a slow poll that
    juuust missed the deadline) a real second chance, which they never had before. Does NOT retry
    a missing-config case — that fails as an instant, guaranteed no-op, not something time helps."""
    if not is_configured():
        return None
    for attempt in range(1, _ATTEMPTS + 1):
        row = _trigger_and_fetch_first_row_once(url)
        if row is not None:
            return row
        if attempt < _ATTEMPTS:
            logger.warning(
                "Bright Data DCA attempt %d/%d failed for %s — retrying once more.",
                attempt, _ATTEMPTS, url,
            )
    return None


def _trigger_and_fetch_first_row_once(url: str) -> dict | None:
    """One real trigger -> poll attempt — shared mechanics for both fetch_listing_description and
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
        # 2026-09-13: `queue_next` REMOVED — confirmed live (diagnose-bright-data-dca-400.yaml)
        # that this account's collector is on Bright Data's trial tier, which rejects it outright:
        # {"error":"Trial collectors don't support queuing jobs"} (a real 400 on every single
        # trigger call, silently swallowed until this response body was actually looked at — see
        # the except clause below, which now always logs it). Was only ever a hedge against a
        # curl example that happened to include it, never load-bearing for anything this project
        # actually needs (one URL per trigger call, not a batch).
        trigger_resp = httpx.post(
            _TRIGGER_URL,
            params={"collector": collector_id},
            json=[{"url": url}],
            headers=headers,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        trigger_resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # The response BODY is where Bright Data actually explains a 4xx (see the queue_next
        # story above) — logging only the exception's own summary, as this used to, hides that
        # entirely. Always include it now so a future rejection reason is visible immediately
        # instead of needing a separate live replay to discover.
        logger.error(
            "Bright Data DCA trigger call failed for %s: http_status=%d body=%r",
            url, exc.response.status_code, exc.response.text[:1000],
        )
        return None
    except httpx.HTTPError:
        logger.exception("Bright Data DCA trigger call failed for %s", url)
        return None

    try:
        job_id = _extract_job_id(trigger_resp.json())
    except ValueError:
        logger.exception("Bright Data DCA trigger response for %s was not valid JSON: %r", url, trigger_resp.text[:1000])
        return None

    if job_id is None:
        logger.error(
            "Bright Data DCA trigger response for %s had no recognizable job id: %r",
            url, trigger_resp.text,
        )
        return None

    # 2026-09-14: REAL production bug found and fixed — `if rows: break` (the only check this loop
    # used to have) treated ANY non-empty poll response as "the job is done", but a genuinely
    # still-processing poll returns a non-empty STATUS dict too (see _looks_like_pending_status's
    # own docstring for the two exact real shapes seen), not an empty list/falsy value as this loop
    # originally assumed. The result: the very first poll (after ~_REQUEST_TIMEOUT_SECONDS, often
    # under a second) almost always broke out immediately with a "still collecting" status object
    # mistaken for the real record, which _compute_detail_updates (scraper/main.py) then found no
    # usable fields in — every single enrichment silently failing (`bright_data_enriched: 0` in a
    # real run-summary line, confirmed 2026-09-14, despite ~3 hours of continuous trigger/poll
    # activity across 994 new Yad2 listings). Now keeps polling through a pending-status response,
    # exactly as it already did for an empty list.
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
        if rows and not _looks_like_pending_status(rows):
            break
        time.sleep(_POLL_INTERVAL_SECONDS)
    else:
        rows = None  # loop exhausted the deadline without ever breaking — never trust a leftover
        # pending-status dict from the last iteration as if it were a real (if late) result.

    if not rows:
        logger.error(
            "Bright Data DCA job %s for %s did not produce a result in time", job_id, url,
        )
        return None

    logger.info("Bright Data DCA raw result for %s: %r", url, rows)
    row = rows[0] if isinstance(rows, list) else rows
    if not isinstance(row, dict):
        return None

    # 2026-09-14: REAL production incident, found from a live owner-only run's actual Telegram
    # messages (5+ real screenshots, different addresses/prices/room counts, IDENTICAL photos and
    # description text word-for-word — including a "2.5 rooms" description on a listing whose own
    # fields said 4.0 rooms). This collector is on Bright Data's trial tier (see this module's own
    # 2026-09-13 entry on `queue_next`); the working theory is its result buffer doesn't reliably
    # scope by job id under concurrent triggers (_BRIGHT_DATA_ENRICH_CONCURRENCY in scraper/main.py
    # runs several of these at once) and can hand back a DIFFERENT job's already-collected page.
    # Every real Yad2 item URL ends in its own external_id/adNumber (normalize.py: `url =
    # f"https://www.yad2.co.il/item/{external_id}"`), and the collector's own record separately
    # carries that same number back as `adNumber` — so this is a cheap, reliable way to catch a
    # cross-contaminated result before it ever reaches a listing row: if the two disagree, this is
    # provably NOT the page we asked for, so it's discarded exactly like any other failed fetch
    # (never raises, caller just gets nothing) rather than silently writing another listing's
    # photos/description/amenities onto this one.
    expected_id = url.rstrip("/").rsplit("/", 1)[-1]
    returned_ad_number = row.get("adNumber")
    if returned_ad_number is not None and str(returned_ad_number) != expected_id:
        logger.error(
            "Bright Data DCA returned a DIFFERENT listing than requested — url=%s expected "
            "id=%s but got adNumber=%r (job %s); discarding rather than risk cross-contaminating "
            "this listing with another one's data.",
            url, expected_id, returned_ad_number, job_id,
        )
        return None

    return row


def fetch_listing_description(url: str) -> str | None:
    """Synchronous and BLOCKING (real network calls + a polling wait) — callers on an event loop
    MUST run this via asyncio.to_thread, same as every other blocking call in this codebase (see
    e.g. todira_common/cards.py's _build_collage_sync docstring for why). Returns None on missing
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


def fetch_via_isp_proxy(url: str) -> str | None:
    """2026-09-13 addition — see module docstring for the full story (Web Unlocker's real KYC
    wall, this being the working alternative found the same day). A classic authenticated HTTP
    proxy request — NOT an API wrapper: no unlocking/rendering/CAPTCHA-solving happens on Bright
    Data's side here, just routing the request through one of their ISP-reputation IPs. Confirmed
    live to work for a pure-JSON endpoint (no JS execution needed); would NOT by itself get past a
    site that needs real browser rendering to produce its content (see this function's own
    module-docstring section for why that's a genuinely different, unsolved problem, not
    something this function claims to fix).

    Returns the raw response body as text on HTTP 200, or None on missing config (any of the three
    env vars unset), any request failure, or a non-200 status — never raises, same contract as
    every other function in this file."""
    host = os.environ.get(ISP_PROXY_HOST_ENV_VAR, "").strip()
    user = os.environ.get(ISP_PROXY_USER_ENV_VAR, "").strip()
    password = os.environ.get(ISP_PROXY_PASS_ENV_VAR, "").strip()
    if not (host and user and password):
        return None

    proxy_url = f"http://{user}:{password}@{host}"
    try:
        response = httpx.get(url, proxy=proxy_url, timeout=_ISP_PROXY_TIMEOUT_SECONDS)
    except httpx.HTTPError:
        logger.exception("Bright Data ISP proxy request failed for %s", url)
        return None

    if response.status_code != 200:
        logger.warning(
            "Bright Data ISP proxy returned non-200 for %s: status=%d body=%r",
            url, response.status_code, response.text[:500],
        )
        return None

    return response.text


def fetch_via_isp_proxy_post(url: str, data: dict[str, str]) -> str | None:
    """POST variant of fetch_via_isp_proxy — same ISP-proxy mechanism, config, and "return None,
    never raise" contract as that function's own docstring; the only difference is the HTTP method
    and the form-encoded `data` body. Added 2026-09-14 for komo_client.py's adscoordinates/list/
    endpoint, which requires a POST carrying a session token — a plain GET can't reach it."""
    host = os.environ.get(ISP_PROXY_HOST_ENV_VAR, "").strip()
    user = os.environ.get(ISP_PROXY_USER_ENV_VAR, "").strip()
    password = os.environ.get(ISP_PROXY_PASS_ENV_VAR, "").strip()
    if not (host and user and password):
        return None

    proxy_url = f"http://{user}:{password}@{host}"
    try:
        response = httpx.post(url, data=data, proxy=proxy_url, timeout=_ISP_PROXY_TIMEOUT_SECONDS)
    except httpx.HTTPError:
        logger.exception("Bright Data ISP proxy POST request failed for %s", url)
        return None

    if response.status_code != 200:
        logger.warning(
            "Bright Data ISP proxy POST returned non-200 for %s: status=%d body=%r",
            url, response.status_code, response.text[:500],
        )
        return None

    return response.text
