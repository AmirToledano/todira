"""Entrypoint: run one scrape+match+notify cycle, then exit. Triggered periodically by the k8s
CronJob (see charts/todira), or manually via `docker compose run --rm scraper` locally.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
import time
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from dedup import find_duplicate_listing
from todira_common import bright_data_client
from todira_common.db import get_session
from todira_common.enums import DealType, Source
from todira_common.models import Listing
import facebook_client
from facebook_client import FacebookFetchError
from facebook_client import fetch_listing_detail as fetch_facebook_listing_detail
from facebook_client import fetch_search_results as fetch_facebook_results
from facebook_groups_client import FacebookGroupsFetchError
from facebook_groups_client import fetch_home_feed_post_ids
from facebook_groups_client import fetch_post_detail as fetch_facebook_group_post_detail
from homeless_client import HomelessFetchError
from homeless_client import fetch_listing_description as fetch_homeless_description
from homeless_client import fetch_search_results as fetch_homeless_results
from komo_client import KomoFetchError, fetch_all_coordinate_ids
from komo_client import fetch_listing_detail as fetch_komo_listing_detail
from normalize import _compute_detail_updates, normalize
from notifier import run_notifications
from yad2_client import (
    REGION_SLUGS,
    REGIONS_ON_MAP_API,
    Yad2FetchError,
    Yad2MapFetchError,
    fetch_listing_detail_via_web_unlocker,
    fetch_region_pages,
    fetch_region_via_map_api,
)

# 2026-09-12: how many fetch_listing_detail_via_web_unlocker calls run concurrently when enriching
# a batch of newly-discovered listings. Each call is one blocking, self-contained Web Unlocker POST
# (see yad2_client.py's own docstring) — running them one at a time would make a scrape run with
# many new listings unacceptably slow; running ALL of them at once risks hammering Bright Data's API
# with an unbounded burst.
#
# 2026-09-15: dropped to 1 while this ran through Bright Data's Scraper Studio DCA collector — a
# real cross-job-contamination race (the collector didn't reliably scope results by job id under
# concurrent triggers) made concurrent enrichment return wrong data. 2026-09-17: back to 5 now that
# this routes through Web Unlocker instead — a single stateless POST per listing, no shared
# trigger/poll job id at all, so that race is structurally impossible here. Revisit (higher, or
# lower if Bright Data's own rate limits complain) only with real evidence, not preemptively.
_BRIGHT_DATA_ENRICH_CONCURRENCY = 5

# 2026-09-15: real, confirmed kill-switch — see charts/todira/values.yaml's own comment on
# scraper.brightDataEnrichmentSuspended for the live diagnostic (.github/workflows/
# diagnose-bright-data-stuck-same-result.yaml) that proved the Bright Data DCA collector currently
# returns the SAME stale cached record for every distinct job id/url requested, 100% of the time —
# a platform/account-side issue, not a bug in this file or bright_data_client.py's own trigger/
# poll/retry logic (all confirmed working correctly by that same test). Checked at the START of
# _enrich_new_listings_via_bright_data, same "no-op, returns 0, never blocks the run" contract as
# is_configured() being false — every other scraper and Yad2's own normalized search-card fields
# are completely unaffected; only this extra detail-enrichment step is paused.
_BRIGHT_DATA_ENRICHMENT_SUSPENDED_ENV_VAR = "BRIGHT_DATA_ENRICHMENT_SUSPENDED"

# 2026-09-15: real, owner-requested speed optimization, after walking the actual run-time
# composition (not guessing) — Yad2/Komo/Homeless previously ran strictly SEQUENTIALLY in
# run_once() below (one full source's worth of network calls, then the next), and Komo's/
# Homeless's own per-genuinely-new-listing detail/description fetch loops were themselves fully
# sequential too, one request at a time. Neither is required for correctness or safety:
# - The three sources are three completely independent websites hit from this same box as
#   independent connections — running them concurrently doesn't change the REQUEST RATE any single
#   site sees, so it carries no extra detection risk (Yad2's own deliberate anti-detection pacing,
#   _MAP_API_REGION_PACING_SECONDS, is UNCHANGED by this — it still paces requests WITHIN Yad2's own
#   region loop exactly as before).
# - Komo has already been confirmed (2026-09-15, diagnose-komo-homeless-direct-request.yaml) to
#   have NO bot-challenge wall of its own at all — a real 11,547-id nationwide fetch succeeded
#   fully un-proxied. Homeless's own per-listing description fetches go through ZenRows, a managed
#   proxy service built for concurrent traffic — concurrency here doesn't touch OUR OWN IP's
#   request rate against homeless.co.il at all, ZenRows' own pool does.
# Bounded (not unbounded) concurrency, same Semaphore + asyncio.to_thread pattern already proven by
# _enrich_new_listings_via_bright_data above — a moderate, not reckless, starting point (matching
# that function's own original "meaningfully parallel but not abusive" reasoning), not a measured
# ceiling for either site.
_KOMO_DETAIL_FETCH_CONCURRENCY = 5
_HOMELESS_DESCRIPTION_FETCH_CONCURRENCY = 5

# 2026-09-14: added after a real catch-up run's delisting got skipped ("at least one region/city
# failed to fetch") — root cause never pinned down for certain (the pod's own log for the failing
# moment had already rotated out by the time it was checked), but the account's own ZenRows
# dashboard showed 96% of its monthly credits already used the same day, and one of Yad2FetchError's
# real causes is exactly ZenRows returning an AUTH004 "usage exceeded" error — the leading
# explanation, not a certainty. A single retry, after a short pause, gives a genuinely transient
# failure (a dropped request, Yad2's own bot-challenge on one unlucky request) a real second
# chance — but retrying an AUTH004 quota error can't ever succeed (the account is out until the
# plan resets), so that specific case is never retried, just to avoid burning an extra call for
# nothing.
_REGION_RETRY_DELAY_SECONDS = 5.0

# 2026-09-17: bumped from 2 total attempts (1 retry) to 3 (2 retries) — real, live evidence from
# the first production run on Bright Data's Web Unlocker (see yad2_client._fetch_direct's own
# docstring for the switch away from a direct, un-proxied GET): of 7 regions, 3 failed even after
# one retry, but per-region log analysis showed the OTHER 4 succeeded silently on their own retry
# (a successful attempt logs nothing — only failures do). A single retry already recovering most
# failures, with the remainder failing the SAME way (an empty, non-JSON response body, not an auth
# or block signature), matches the well-documented behavior of headless-render/unlocking APIs in
# general: a fraction of individual render requests transiently come back empty on Bright Data's
# own side, independent of anything this project controls, and need more than one retry to reduce
# to a small residual failure rate rather than a systemic one.
_YAD2_MAX_FETCH_ATTEMPTS = 3

# 2026-09-15: added after a real, live-observed finding — the owner-only safe-single-test-run.yaml
# run fired center-and-sharon/tel-aviv-area/jerusalem-area within under 0.6s of each other (no
# delay ever existed between iterations of the `for region in REGION_SLUGS` loop below, only
# _REGION_RETRY_DELAY_SECONDS above, which is a retry-within-one-region gap, not a between-regions
# one) — jerusalem-area got a 302 Radware challenge on both its attempts, while every region that
# happened to fire with more natural spacing (waiting on a slower ZenRows region, or after a retry
# cycle) succeeded. Matches the same velocity-sensitivity already documented elsewhere for this
# site (see yad2_client.py's REGIONS_ON_MAP_API comment) — this project's production IP has no
# fresh-IP-per-request advantage GitHub Actions' own diagnostic runs happened to have. A small,
# deliberate pause between map-API region fetches only (ZenRows regions are naturally paced by
# their own much slower per-page fetches) costs at most 6 * this value per run (~9s for all 7
# regions) — cheap insurance against tripping the same challenge again.
_MAP_API_REGION_PACING_SECONDS = 1.5

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx's own "httpx" logger emits an INFO line per request with the FULL request URL — including
# the `apikey=...` query param yad2_client.py's ZenRows calls carry — so at the root INFO level
# above, every scraper run was leaking the live ZenRows key straight into pod logs. Confirmed live
# 2026-09-03 on the real cluster's first post-deploy run. Silencing httpx specifically (not the
# whole app) keeps our own "scraper.main"/"scraper.notifier" etc. logging at INFO as intended.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("scraper.main")

# 2026-09-13: real, live ZenRows balance check (owner's own dashboard screenshot) found only
# 7,218 credits remain on a plan that renews 2026-10-01 — ~18 days away. At the schedule/sources
# active before this date (8 runs/day, full 7-region Yad2 sweep + all-42-city Komo discovery every
# run, ~260 credits/run in steady state) that remaining balance lasts only ~3.5 days, not 18 — and
# BEFORE counting Komo's own first-ever production run, where EVERY currently-active Komo listing
# nationwide looks "new" (no prior run ever populated known_ids for source=komo) and would each
# cost a real detail-page fetch. These three env vars are the real, deployable response — all
# optional/temporary, meant to be relaxed or removed once either the ZenRows plan renews, the
# owner buys more credits, or Yad2 fully moves off ZenRows onto Bright Data's ISP proxy (see
# yad2_client.py's fetch_map_markers — not wired in yet, blocked on a separate rate-limit finding,
# see PROJECT_STATE.md 2026-09-13).
_KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR = "KOMO_MAX_NEW_DETAIL_FETCHES_PER_RUN"
# 300 credits reserved for Komo's backlog per run, out of the real ~2,500-credit safety buffer
# this whole change is built around (see values.yaml's own comment for the exact math) — a genuine
# guess at "meaningfully progresses the backlog without risking the whole remaining balance in one
# run", not a measured number (Komo's real total nationwide active-listing count is unknown).
_DEFAULT_KOMO_MAX_NEW_DETAIL_FETCHES_PER_RUN = 300
_YAD2_MAX_PAGES_ENV_VAR = "YAD2_MAX_PAGES_PER_REGION"
_NOTIFICATIONS_SUSPENDED_ENV_VAR = "NOTIFICATIONS_SUSPENDED"
# 2026-09-13: same real-money-per-fetch reasoning as Komo's own cap above, one order of magnitude
# smaller — Homeless is a much lower-volume site than Komo's nationwide coverage (see
# homeless_client.py's own module docstring), so a first-ever run's genuinely-new backlog is
# expected to be far smaller too, but this is still a real per-listing ZenRows cost with no cap
# otherwise — never assume a site is "small enough" without a real safety net.
_HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_ENV_VAR = "HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_PER_RUN"
_DEFAULT_HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_PER_RUN = 50

# 2026-09-18: real incident, not a hypothetical — the very first real production run after
# switching Yad2 enrichment to Web Unlocker (see fetch_listing_detail_via_web_unlocker's own
# docstring) ran for 20+ minutes and never reached the notification-sending step at all, live-
# confirmed via check-scraper-job-status.yaml's real pod logs: Yad2 had a real backlog of
# genuinely-new listings (map-API fetching was down for hours beforehand), and Web Unlocker's own
# per-request timeout (_WEB_UNLOCKER_TIMEOUT_SECONDS=90s in bright_data_client.py) meant even a
# handful of slow/timed-out individual item-page fetches could stall the whole run for many
# minutes — with no cap at all, unlike Komo/Homeless/Facebook's own per-run caps above, which all
# exist for exactly this "unbounded backlog" reason. Same safety-net pattern applied here.
_BRIGHT_DATA_ENRICH_MAX_PER_RUN_ENV_VAR = "BRIGHT_DATA_ENRICH_MAX_NEW_LISTINGS_PER_RUN"
_DEFAULT_BRIGHT_DATA_ENRICH_MAX_PER_RUN = 15

# 2026-09-15: Facebook's own per-run cap is NOT a credit-cost safety net like Komo/Homeless's own
# caps above (Facebook charges nothing per request) — it's an ACCOUNT-SAFETY net. Every request
# here runs through the dedicated scraping account's own real, authenticated session from a
# datacenter IP, the exact profile Facebook's own automation/Account-Integrity detection is built
# to catch; the real downside of getting that wrong is a checkpoint/restriction on the account
# itself, not a recoverable "try again later" the way a blocked scrape of a public, anonymous page
# is. A small, deliberately conservative default — see facebook_client.py's own module docstring
# for the real, live-confirmed field structure this whole client is built against, and
# PROJECT_STATE.md's 2026-09-15 Facebook entries for the real account-risk discussion this default
# came out of.
_FACEBOOK_MAX_NEW_DETAIL_FETCHES_ENV_VAR = "FACEBOOK_MAX_NEW_DETAIL_FETCHES_PER_RUN"
# 2026-09-15: raised from an initial 15 to 25 (owner's own explicit go-ahead, "can give more") —
# one discovery fetch has only ever yielded ~24-27 real listings live (see facebook_client.py's own
# module docstring), so 25 is effectively "enrich everything this run found", not a further
# artificial narrowing below the feed's own real size; still a real, deliberate ceiling against an
# unexpectedly large feed rather than no cap at all.
_DEFAULT_FACEBOOK_MAX_NEW_DETAIL_FETCHES_PER_RUN = 25
# Deliberate, RANDOMIZED pacing between each per-listing detail-page fetch (real, separate requests
# against the live account) — same reasoning as _MAP_API_REGION_PACING_SECONDS above (a human
# browsing Marketplace never opens listing after listing with zero delay, and request velocity is
# one of the most basic bot-detection signals), randomized rather than a fixed interval per the
# owner's own explicit suggestion tonight — a perfectly constant gap between requests is itself a
# machine-like signal a fixed sleep doesn't hide. Costs at most a couple of minutes per run at the
# cap above — cheap insurance either way.
_FACEBOOK_DETAIL_FETCH_PACING_SECONDS_RANGE = (2.0, 6.0)
# Real kill-switch, independent of any CronJob's own `suspend`/schedule: Facebook scraping is
# EXCLUDED from a run unless explicitly opted in via SCRAPE_SOURCES (see _active_source_scrapers
# below) — so merely deploying this code, or FACEBOOK_COOKIES existing in the secret, can never by
# itself start hitting the live Facebook account. A separate CronJob (see charts/todira's
# facebook-scraper-cronjob.yaml) sets SCRAPE_SOURCES=facebook_marketplace explicitly, on its own
# schedule, with its own `suspend` — the main scraper's own CronJob never sets this var at all, so
# its default (every source except Facebook) is exactly today's existing behavior, unchanged.
_SCRAPE_SOURCES_ENV_VAR = "SCRAPE_SOURCES"

# 2026-09-22: comma-separated Facebook numeric group ids to track — deliberately an env var, not a
# DB table, matching this project's existing config style (e.g. SCRAPE_SOURCES itself) rather than
# adding new schema for what's currently one group. `fetch_home_feed_post_ids` (see
# facebook_groups_client.py's own docstring) uses this set to filter the account's home feed down
# to only the groups actually wanted — a Story from any other group (or non-group content, like a
# followed Page's post) is silently skipped. Empty/unset means "no groups configured" — the scrape
# function below is a no-op in that case, never an error.
_FACEBOOK_GROUPS_TRACKED_IDS_ENV_VAR = "FACEBOOK_GROUPS_TRACKED_IDS"
# Same account-safety reasoning as _DEFAULT_FACEBOOK_MAX_NEW_DETAIL_FETCHES_PER_RUN above, just a
# smaller default — the home feed's own real per-run yield was 2 new posts across 2 groups in the
# one live test so far (see PROJECT_STATE.md, 2026-09-21/22), nowhere near Marketplace's ~25;
# raise this only with real evidence a legitimate run is actually hitting the cap.
_FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_ENV_VAR = "FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_PER_RUN"
_DEFAULT_FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_PER_RUN = 15


def _facebook_groups_tracked_ids() -> set[str]:
    raw = os.environ.get(_FACEBOOK_GROUPS_TRACKED_IDS_ENV_VAR, "").strip()
    return {s.strip() for s in raw.split(",") if s.strip()}


def _facebook_groups_max_new_detail_fetches_per_run() -> int:
    raw = os.environ.get(_FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "").strip()
    if not raw:
        return _DEFAULT_FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_PER_RUN
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%r (not an int) — using default %d",
            _FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_ENV_VAR, raw,
            _DEFAULT_FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_PER_RUN,
        )
        return _DEFAULT_FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_PER_RUN


def _homeless_max_new_description_fetches_per_run() -> int:
    raw = os.environ.get(_HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_ENV_VAR, "").strip()
    if not raw:
        return _DEFAULT_HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_PER_RUN
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%r (not an int) — using default %d",
            _HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_ENV_VAR, raw,
            _DEFAULT_HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_PER_RUN,
        )
        return _DEFAULT_HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_PER_RUN


def _bright_data_enrich_max_per_run() -> int:
    raw = os.environ.get(_BRIGHT_DATA_ENRICH_MAX_PER_RUN_ENV_VAR, "").strip()
    if not raw:
        return _DEFAULT_BRIGHT_DATA_ENRICH_MAX_PER_RUN
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%r (not an int) — using default %d",
            _BRIGHT_DATA_ENRICH_MAX_PER_RUN_ENV_VAR, raw,
            _DEFAULT_BRIGHT_DATA_ENRICH_MAX_PER_RUN,
        )
        return _DEFAULT_BRIGHT_DATA_ENRICH_MAX_PER_RUN


def _facebook_max_new_detail_fetches_per_run() -> int:
    raw = os.environ.get(_FACEBOOK_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "").strip()
    if not raw:
        return _DEFAULT_FACEBOOK_MAX_NEW_DETAIL_FETCHES_PER_RUN
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%r (not an int) — using default %d",
            _FACEBOOK_MAX_NEW_DETAIL_FETCHES_ENV_VAR, raw,
            _DEFAULT_FACEBOOK_MAX_NEW_DETAIL_FETCHES_PER_RUN,
        )
        return _DEFAULT_FACEBOOK_MAX_NEW_DETAIL_FETCHES_PER_RUN


def _komo_max_new_detail_fetches_per_run() -> int:
    raw = os.environ.get(_KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "").strip()
    if not raw:
        return _DEFAULT_KOMO_MAX_NEW_DETAIL_FETCHES_PER_RUN
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%r (not an int) — using default %d",
            _KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR, raw, _DEFAULT_KOMO_MAX_NEW_DETAIL_FETCHES_PER_RUN,
        )
        return _DEFAULT_KOMO_MAX_NEW_DETAIL_FETCHES_PER_RUN


def _yad2_max_pages_per_region_override() -> int | None:
    """None (the default) means "use fetch_region_pages' own built-in default (15)" — this only
    exists so ops can temporarily tighten Yad2's own per-region catch-up cap (see that function's
    module comment for its own reasoning) via a values.yaml/env change, without a code redeploy,
    during the exact same credit-budget squeeze _KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR above is for."""
    raw = os.environ.get(_YAD2_MAX_PAGES_ENV_VAR, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r (not an int) — using fetch_region_pages' own default", _YAD2_MAX_PAGES_ENV_VAR, raw)
        return None


def _notifications_suspended() -> bool:
    """True while catching up a long-paused scraper back to real current state — a resume after
    days/weeks suspended would otherwise find many genuinely-new listings and fire a real
    notification burst to every matching user's phone in one shot, regardless of time of day. When
    set, run_once() still does everything else exactly as normal (scrape/upsert/delist all run in
    full) so the catch-up itself is never silently incomplete.

    2026-09-13: this no longer means a full skip — see run_once()'s own use of this alongside
    OWNER_TELEGRAM_USER_ID. The owner explicitly wants real Telegram pushes to keep landing on
    their OWN phone during the catch-up (so the pipeline is genuinely being verified end to end,
    not just trusted on faith) while every other real user stays untouched until this is lifted."""
    return os.environ.get(_NOTIFICATIONS_SUSPENDED_ENV_VAR, "").strip().lower() in ("1", "true", "yes")


def _upsert_listings(session, normalized_items) -> tuple[list[int], list[tuple[int, int]]]:
    """For each normalized item: insert if the (source, external_id) pair is new, otherwise
    update the existing row and check whether its price just changed.

    Returns (new_ids, price_change_events) where price_change_events is a list of
    (listing_id, old_price) for existing listings whose price is different this run — either
    direction; the caller (notifier.py) compares old vs. new to decide 📉 drop vs. 📈 increase.
    Originally drop-only (added after the user pointed out the reference bot's "📉 ירידת מחיר!"
    re-notification, which the original DO-NOTHING design missed); generalized to increases too
    2026-09-02 per an explicit request that both directions get a re-notification. This is a
    per-item SELECT-then-INSERT/UPDATE rather than a single bulk `INSERT ... ON CONFLICT DO
    NOTHING` — less efficient at scale, but DO NOTHING can't see what the previous value was, and
    seeing it is exactly what price-change detection needs. Fine at this project's scale — a
    personal deployment, not high-throughput.

    Real photos/amenity tags/broker status are already merged into `item` by `normalize()` itself
    (see its own `_enrich_from_feed_record` call) before this function ever sees it — a free
    bonus from the search page already being fetched, not a separate cost this function has to
    manage. An earlier version fetched a full per-listing detail page here for every genuinely new
    item (~25 ZenRows credits each, real recurring cost) — rejected once that cost was understood;
    see PROJECT_STATE.md, 2026-09-02.

    2026-09-13: a genuinely new (source, external_id) pair is now also checked against
    dedup.find_duplicate_listing before being inserted — see that module's own docstring for the
    matching heuristic. A match sets duplicate_of_id on the new row (so it's excluded from
    every "active listings" view query, see models.py's own docstring) and, deliberately, does
    NOT add it to new_ids — no notification and no Bright Data enrichment for a row the user is
    never shown as its own listing. Within one call, an EARLIER item in the same `normalized_items`
    list that was just inserted (not yet committed) is still visible to a LATER item's duplicate
    check — same session, same open transaction, no isolation gap — so cross-source duplicates
    introduced in the same scrape run are still caught, not just ones from a previous run."""
    table = Listing.__table__
    new_ids: list[int] = []
    price_change_events: list[tuple[int, int]] = []

    for item in normalized_items:
        existing = session.execute(
            select(table.c.id, table.c.price).where(
                table.c.source == item.source, table.c.external_id == item.external_id
            )
        ).first()

        if existing is None:
            duplicate_of_id = find_duplicate_listing(session, item)
            values = item.model_dump()
            if duplicate_of_id is not None:
                values["duplicate_of_id"] = duplicate_of_id
            row = session.execute(pg_insert(table).values(**values).returning(table.c.id)).first()
            if duplicate_of_id is None:
                new_ids.append(row[0])
            continue

        existing_id, old_price = existing
        if item.price is not None and old_price is not None and item.price != old_price:
            price_change_events.append((existing_id, old_price))

        session.execute(table.update().where(table.c.id == existing_id).values(**item.model_dump()))

    session.commit()
    return new_ids, price_change_events


async def _fetch_concurrently(
    items: list, fetch_fn: Callable[[object], object], concurrency: int
) -> list:
    """Runs fetch_fn(item) for each item in `items`, bounded by `concurrency` in-flight calls at
    once — same Semaphore + asyncio.to_thread pattern as _enrich_new_listings_via_bright_data
    below (fetch_fn is always a blocking/synchronous network call here too). Returns one result
    per item, in the SAME order as `items`. A result is None if fetch_fn itself returned None OR
    raised — every fetch_fn this is used with (komo_client.fetch_listing_detail,
    homeless_client.fetch_listing_description) is documented "never raises", so a raise here would
    be a genuine bug, but this stays defensive rather than letting one bad item crash the whole
    batch, matching that function's own per-listing exception handling."""
    semaphore = asyncio.Semaphore(concurrency)

    async def _one(item: object) -> object:
        async with semaphore:
            return await asyncio.to_thread(fetch_fn, item)

    results = await asyncio.gather(*(_one(item) for item in items), return_exceptions=True)
    return [None if isinstance(result, BaseException) else result for result in results]


async def _enrich_new_listings_via_bright_data(session, new_ids: list[int]) -> int:
    """For every listing genuinely new to the DB this run (never for one already known — an
    already-known listing already got this exactly once, on the run it first appeared, and the
    result is cached on Listing.description/etc forever), fetches the full listing-detail record
    and applies normalize._compute_detail_updates' fields (description, property type, amenities,
    floor_total, move-in date, real photos, broker status) straight onto that row.

    2026-09-17: routes through yad2_client.fetch_listing_detail_via_web_unlocker (Bright Data Web
    Unlocker) instead of bright_data_client.fetch_listing_detail_via_bright_data (the Scraper
    Studio DCA collector) — that collector is a dead end on this account's Free Trial tier
    regardless of key/code fixes: the API can only ever trigger a fixed demo collector, confirmed
    live by two distinct real URLs both coming back wrong (one empty, one the same stale cached
    Dizengoff listing). Web Unlocker's own KYC wall for individual listing pages (which blocked
    this exact route on 2026-09-13) is confirmed gone as of tonight. Kept this function's name and
    its "_BRIGHT_DATA_..." constants below since Web Unlocker is still a Bright Data product on the
    same account/key, just a different one than the DCA collector.

    A no-op (returns 0 immediately, no network calls) when BRIGHT_DATA_API_KEY isn't set, so this
    is always safe to call regardless of whether the feature is actually turned on yet. Also a
    no-op when BRIGHT_DATA_ENRICHMENT_SUSPENDED=true — see
    _BRIGHT_DATA_ENRICHMENT_SUSPENDED_ENV_VAR's own comment.

    2026-09-13: scoped to source == Source.YAD2 only (now that `new_ids` can include Komo/Homeless
    rows too — see run_once) — fetch_listing_detail_via_web_unlocker parses a YAD2 listing detail
    page's own __NEXT_DATA__; pointing it at a komo.co.il/homeless.co.il URL would get nonsense or
    a hard failure, not real enrichment. Komo/Homeless don't need this anyway — their own scrapers
    already get everything they support in one fetch.

    Runs the actual per-listing fetches concurrently (bounded by _BRIGHT_DATA_ENRICH_CONCURRENCY)
    via asyncio.to_thread, since fetch_listing_detail_via_web_unlocker is blocking/synchronous (a
    real network call, same contract as fetch_listing_description elsewhere in this codebase) — see
    that function's own docstring. Deliberately best-effort per listing: one whose fetch fails or
    returns nothing usable simply keeps its already-normalized (search-card-only) fields, exactly
    as every listing always could before this feature existed — never blocks or fails the whole run
    over one bad fetch.

    Returns how many listings were actually enriched (Web Unlocker returned usable data for)."""
    if not new_ids or not os.environ.get(bright_data_client.API_KEY_ENV_VAR, "").strip():
        return 0
    if os.environ.get(_BRIGHT_DATA_ENRICHMENT_SUSPENDED_ENV_VAR, "").strip().lower() == "true":
        return 0

    table = Listing.__table__
    # Plain (id, url) rows via Core, NOT ORM `Listing` objects — this session's factory is
    # expire_on_commit=False (see todira_common/db.py), so an ORM object loaded here would sit in
    # the identity map with its PRE-enrichment values and get handed back as-is to run_once()'s own
    # later `select(Listing)` for the same ids, silently undoing this whole function's work. Same
    # reason _upsert_listings/_mark_delisted already operate at the Core `table` level instead of
    # through the ORM.
    id_url_pairs = session.execute(
        select(table.c.id, table.c.url).where(
            table.c.id.in_(new_ids), table.c.source == Source.YAD2
        )
    ).all()

    max_per_run = _bright_data_enrich_max_per_run()
    if len(id_url_pairs) > max_per_run:
        logger.warning(
            "Yad2 Bright Data enrichment hit its per-run safety cap (%s=%d) — remaining "
            "%d new listings this run keep only their search-card fields (no description) "
            "and will be picked up in a later run, instead of risking one run stalling for "
            "a long time on Web Unlocker's own per-request timeout.",
            _BRIGHT_DATA_ENRICH_MAX_PER_RUN_ENV_VAR, max_per_run, len(id_url_pairs) - max_per_run,
        )
        id_url_pairs = id_url_pairs[:max_per_run]

    semaphore = asyncio.Semaphore(_BRIGHT_DATA_ENRICH_CONCURRENCY)

    async def _fetch_one(listing_id: int, url: str) -> tuple[int, dict] | None:
        async with semaphore:
            detail = await asyncio.to_thread(fetch_listing_detail_via_web_unlocker, url)
        if detail is None:
            return None
        updates = _compute_detail_updates(detail)
        return (listing_id, updates) if updates else None

    results = await asyncio.gather(
        *(_fetch_one(listing_id, url) for listing_id, url in id_url_pairs), return_exceptions=True
    )

    enriched_count = 0
    for (listing_id, url), result in zip(id_url_pairs, results):
        if isinstance(result, BaseException):
            logger.exception(
                "Bright Data enrichment failed for listing id=%s url=%s", listing_id, url,
                exc_info=result,
            )
            continue
        if result is None:
            continue
        _enriched_id, updates = result
        session.execute(table.update().where(table.c.id == listing_id).values(**updates))
        enriched_count += 1

    session.commit()
    return enriched_count


def _mark_delisted(
    session, source: str, seen_external_ids: set[str], scraped_city_names: set[str]
) -> int:
    """Mark previously-active listings FROM `source` that weren't seen in this (complete) run as
    delisted, and un-delist any that reappeared. Scoped to `scraped_city_names` — the canonical
    Hebrew names (see cities.canonicalize_city) of the cities actually REPRESENTED among this
    run's fetched listings, NOT globally across every city this project tracks.

    2026-09-13: generalized from Yad2-only to take an explicit `source` — Komo/Homeless each get
    their own independent delisting pass (see run_once), never each other's or Yad2's, since a
    listing "not seen" in Komo's own run says nothing about whether it's still active on Yad2 or
    Homeless (their own scrapes are separate requests entirely, not a shared crawl).

    Since 2026-09-03 (see yad2_client.py's REGION_SLUGS/fetch_all_listings), a run no longer picks
    cities in advance — it fetches 7 broad regions and only learns which cities actually showed up
    after parsing the results. `scraped_city_names` is therefore built from the fetched listings
    themselves (each already canonicalized by normalize()), not from a fixed slug list. A city
    genuinely absent from this run's results (nothing new/active there right now) is simply never
    in this set — correctly excluded from delisting, rather than wrongly assumed to have emptied
    out. This mirrors the same fix this function already needed once before (2026-09-02, when
    scoping was still per-scraped-city): running delisting globally, or against cities the run
    didn't actually observe, wrongly delists everything elsewhere — found live via a production
    query showing literally every non-delisted listing in the whole table belonged to the one city
    just scraped. Still only called when every region/city ATTEMPTED this run for `source`
    succeeded (see run_once) — a partial fetch failure within that observed set must never be
    mistaken for "everything in these cities disappeared"."""
    table = Listing.__table__
    newly_delisted = session.execute(
        table.update()
        .where(
            table.c.source == source,
            table.c.is_delisted.is_(False),
            table.c.city.in_(scraped_city_names),
            table.c.external_id.notin_(seen_external_ids),
        )
        .values(is_delisted=True, delisted_at=func.now())
        .returning(table.c.id)
    ).fetchall()
    session.execute(
        table.update()
        .where(
            table.c.source == source,
            table.c.is_delisted.is_(True),
            table.c.city.in_(scraped_city_names),
            table.c.external_id.in_(seen_external_ids),
        )
        .values(is_delisted=False, delisted_at=None)
    )
    session.commit()
    return len(newly_delisted)


def _fetch_known_external_ids(source: str) -> set[str]:
    """Every external_id this project already has FOR ONE SOURCE — read once at the start of a
    run and handed to that source's own fetch loop, so it knows which ids are genuinely new vs.
    already known (see fetch_region_pages'/each per-source scrape function's own docstring for why
    each needs this). A short-lived read-only session, separate from the write session the rest of
    run_once() opens later, since this needs to happen BEFORE the (potentially long, all-network)
    fetch loop rather than interleaved with it.

    2026-09-13: generalized from Yad2-only (added 2026-09-12 as _fetch_known_yad2_external_ids
    alongside fetch_region_pages) to take an explicit `source`, for Komo/Homeless's own equivalent
    needs."""
    table = Listing.__table__
    with get_session() as session:
        return set(session.scalars(select(table.c.external_id).where(table.c.source == source)))


def _scrape_yad2() -> tuple[list, set[str], int, int, bool]:
    """Returns (normalized_items, seen_external_ids, fetched_count, error_count, all_succeeded) —
    same shape every _scrape_* function returns, so run_once() can treat all three sources
    uniformly. See fetch_region_pages' own docstring in yad2_client.py for the pagination/cost
    reasoning.

    2026-09-13: _yad2_max_pages_per_region_override() lets ops temporarily tighten
    fetch_region_pages' own max_pages (built-in default 15) via a values.yaml/env change — see
    that function's own comment for the real credit-budget reasoning this and Komo's own per-run
    cap share. None (unset) means "use fetch_region_pages' own default", not "unlimited"."""
    fetched = 0
    errors = 0
    normalized_items = []
    seen_external_ids: set[str] = set()
    all_succeeded = True

    known_ids = _fetch_known_external_ids(Source.YAD2)
    max_pages_override = _yad2_max_pages_per_region_override()
    fetch_kwargs = {} if max_pages_override is None else {"max_pages": max_pages_override}
    logger.info("Scraping %d Yad2 regions this run: %s", len(REGION_SLUGS), ", ".join(REGION_SLUGS))
    for region in REGION_SLUGS:
        # 2026-09-15: as of REGIONS_ON_MAP_API covering all 7 REGION_SLUGS (see that dict's own
        # comment), this migration off ZenRows is COMPLETE — every region goes through the map API
        # now, via a plain direct (un-proxied) request (see yad2_client._fetch_direct's own
        # docstring for why it's no longer routed through Bright Data's ISP proxy either). The
        # `use_map_api`/ZenRows branch below is kept as a real fallback path, not dead code — a
        # region temporarily removed from REGIONS_ON_MAP_API (e.g. if it starts failing and no
        # replacement bbox is confirmed yet) falls straight back to it, no code change needed.
        use_map_api = region in REGIONS_ON_MAP_API
        logger.info(
            "Fetching Yad2 listings for region=%s (via %s)",
            region, "map API (direct)" if use_map_api else "ZenRows",
        )
        region_succeeded = False
        for attempt in range(1, _YAD2_MAX_FETCH_ATTEMPTS + 1):
            try:
                region_items = (
                    fetch_region_via_map_api(region)
                    if use_map_api
                    else fetch_region_pages(region, known_ids, **fetch_kwargs)
                )
                for raw_item in region_items:
                    fetched += 1
                    normalized = normalize(raw_item, source=Source.YAD2, deal_type=DealType.RENT)
                    if normalized is not None:
                        normalized_items.append(normalized)
                        seen_external_ids.add(normalized.external_id)
                    else:
                        errors += 1
                region_succeeded = True
                break
            except (Yad2FetchError, Yad2MapFetchError) as exc:
                # A quota error ("AUTH004") can't be fixed by waiting a few seconds — the account
                # is out until its plan resets, so retrying just burns another call for nothing.
                # (Only ever raised by the ZenRows path — Yad2MapFetchError never carries it — so
                # this check is simply never true for a map-API region, which is fine.)
                if "AUTH004" in str(exc):
                    logger.error(
                        "Yad2 fetch failed for region=%s — ZenRows quota exhausted (AUTH004), "
                        "not retrying: %s", region, exc,
                    )
                    break
                if attempt < _YAD2_MAX_FETCH_ATTEMPTS:
                    logger.warning(
                        "Yad2 fetch failed for region=%s (attempt %d/%d) — retrying in %.0fs: %s",
                        region, attempt, _YAD2_MAX_FETCH_ATTEMPTS, _REGION_RETRY_DELAY_SECONDS, exc,
                    )
                    time.sleep(_REGION_RETRY_DELAY_SECONDS)
                else:
                    logger.exception(
                        "Failed to fetch Yad2 results for region=%s after %d attempts — skipping "
                        "this region", region, _YAD2_MAX_FETCH_ATTEMPTS,
                    )
        if not region_succeeded:
            errors += 1
            all_succeeded = False
        if use_map_api:
            # See _MAP_API_REGION_PACING_SECONDS' own comment — deliberately unconditional (runs
            # after the LAST region too; harmless, just a few seconds of otherwise-idle time before
            # this function returns).
            time.sleep(_MAP_API_REGION_PACING_SECONDS)

    return normalized_items, seen_external_ids, fetched, errors, all_succeeded


def _scrape_komo() -> tuple[list, set[str], int, int, bool]:
    """Returns the same (normalized_items, seen_external_ids, fetched, errors, all_succeeded)
    shape as _scrape_yad2 — see that function and run_once() for how it's used.

    2026-09-13: fetches Komo's coordinate list via ONE call, fetch_all_coordinate_ids() — not once
    per tracked city as this used to. CONFIRMED live (diagnose-komo-region-coverage.yaml, prompted
    by an owner question: "why 42 cities when Yad2 needs only 7 regions?") that Komo's coordinates
    endpoint is genuinely NATIONWIDE regardless of which city is queried: a real side-by-side test
    queried Jerusalem and Tel Aviv and got back byte-identical 11,976-id sets. The old 42-city loop
    was paying 84 credits/run (2 credits × 42 cities) for the exact same data every single time —
    this fixes that down to 2 credits/run total, a real, direct answer to the ZenRows credit
    crisis (see PROJECT_STATE.md 2026-09-13), not just Yad2/Komo's own per-run cap.

    Unlike Yad2, a Komo listing's price/rooms/floor/etc. are NEVER refreshed for an
    already-known external_id (the coordinates list carries no price at all — see
    fetch_listing_detail's own module-docstring cost note) — only genuinely new ids get a detail
    fetch. This means an existing Komo listing's price change is NOT currently detected by this
    scraper (a real, documented gap — re-fetching every known listing's detail page each run would
    cost 1 credit per already-known listing per run, rejected as wasteful without a real reason to
    believe Komo prices change often enough to justify it; revisit if that assumption turns out
    wrong). `seen_external_ids` still includes already-known ids (from the coordinates list, not a
    detail fetch) so delisting stays correct regardless of this gap.

    Also enforces _komo_max_new_detail_fetches_per_run() — a real, temporary credit-budget safety
    cap (see that function's own comment) on how many NEW detail fetches (the only part of this
    function with an actual per-listing ZenRows cost) happen in ONE run. A capped-out id is simply
    picked up by a LATER run instead (processed_this_run doesn't mark it as done, so it's retried
    next time).

    2026-09-15: the actual new-listing detail fetches now run CONCURRENTLY, bounded by
    _KOMO_DETAIL_FETCH_CONCURRENCY (see that constant's own comment for why this is safe — Komo has
    already been confirmed to have no bot-challenge wall of its own) — same _fetch_concurrently
    helper _scrape_homeless uses. Previously these ran one at a time, sequentially, which is what
    made a run with many new Komo listings take a real, avoidable extra chunk of wall-clock time."""
    normalized_items = []
    seen_external_ids: set[str] = set()

    known_ids = _fetch_known_external_ids(Source.KOMO)
    processed_this_run: set[str] = set(known_ids)
    max_new_detail_fetches = _komo_max_new_detail_fetches_per_run()

    logger.info("Fetching Komo's nationwide coordinate list (one call, confirmed city-independent)")
    try:
        coordinates = fetch_all_coordinate_ids()
    except KomoFetchError:
        logger.exception("Failed to fetch Komo's coordinate list — skipping Komo entirely this run")
        return normalized_items, seen_external_ids, 0, 1, False

    new_ids_to_fetch: list[str] = []
    for coordinate in coordinates:
        modaa_num = coordinate.get("id")
        if not modaa_num:
            continue
        modaa_num = str(modaa_num)
        seen_external_ids.add(modaa_num)
        if modaa_num in processed_this_run:
            continue  # already known from a prior run, or a duplicate within this run's own list
        processed_this_run.add(modaa_num)
        new_ids_to_fetch.append(modaa_num)

    ids_to_fetch = new_ids_to_fetch[:max_new_detail_fetches]
    if len(new_ids_to_fetch) > max_new_detail_fetches:
        logger.warning(
            "Komo hit its per-run new-detail-fetch safety cap (%s=%d) — remaining new "
            "listings this run are skipped and will be picked up in a later run "
            "instead of spending unbounded ZenRows credits in one shot.",
            _KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR, max_new_detail_fetches,
        )

    fetched = len(ids_to_fetch)
    errors = 0
    details = asyncio.run(
        _fetch_concurrently(ids_to_fetch, fetch_komo_listing_detail, _KOMO_DETAIL_FETCH_CONCURRENCY)
    )
    for detail in details:
        if detail is None:
            errors += 1
            continue
        normalized = normalize(detail, source=Source.KOMO, deal_type=DealType.RENT)
        if normalized is not None:
            normalized_items.append(normalized)
        else:
            errors += 1

    return normalized_items, seen_external_ids, fetched, errors, True


def _scrape_homeless() -> tuple[list, set[str], int, int, bool]:
    """Returns the same (normalized_items, seen_external_ids, fetched, errors, all_succeeded)
    shape as _scrape_yad2. Unlike Yad2/Komo, Homeless doesn't need a `known_ids` set for its core
    fields — its one plain fetch already returns full data (price/rooms/floor/street/city, all
    confirmed in the same request — see homeless_client.py's own module docstring) for every
    listing currently on the page, so an already-known listing's price gets refreshed for free
    every run, same as Yad2.

    2026-09-13: `known_ids` IS used now, for one thing only — deciding whether a listing is
    genuinely new to this project, in which case (and only then) its own detail page gets an
    extra fetch for a real free-text description (see homeless_client.fetch_listing_description's
    own docstring) — same "enrich once, cache forever" policy as Komo's mandatory price fetch and
    Yad2's Bright Data enrichment. Enforces
    _homeless_max_new_description_fetches_per_run() the same way Komo's own per-run cap works: a
    capped-out listing simply keeps no description this run and is picked up on a later one (it's
    still fully upserted otherwise — this only skips the EXTRA description fetch, never the
    listing itself).

    NOT yet confirmed (see homeless_client.py's own module docstring): whether homeless.co.il/rent/
    paginates beyond what one fetch returns. If it does, this function currently only sees
    whatever's on that one page — a real, documented open question, not a silent assumption of
    full coverage.

    2026-09-15: the actual new-listing description fetches now run CONCURRENTLY, bounded by
    _HOMELESS_DESCRIPTION_FETCH_CONCURRENCY (see that constant's own comment — these go through
    ZenRows either way, a managed proxy built for concurrent traffic, so this doesn't change the
    request rate OUR OWN IP presents to homeless.co.il at all) — same _fetch_concurrently helper
    _scrape_komo uses. Previously these ran one at a time, sequentially."""
    errors = 0
    normalized_items = []
    seen_external_ids: set[str] = set()
    all_succeeded = True

    known_ids = _fetch_known_external_ids(Source.HOMELESS)
    max_new_description_fetches = _homeless_max_new_description_fetches_per_run()

    logger.info("Fetching Homeless listings")
    raw_items: list[dict] = []
    try:
        for raw_item in fetch_homeless_results():
            raw_items.append(raw_item)
    except HomelessFetchError:
        # A partial list (whatever was already yielded before the failure) is still processed
        # below, same as before this change — a mid-iteration failure never discarded what had
        # already been fetched.
        logger.exception("Failed to fetch Homeless listings — skipping the rest of this source")
        errors += 1
        all_succeeded = False

    fetched = len(raw_items)
    for raw_item in raw_items:
        seen_external_ids.add(raw_item["id"])

    new_items = [item for item in raw_items if item["id"] not in known_ids]
    items_to_fetch = new_items[:max_new_description_fetches]
    if len(new_items) > max_new_description_fetches:
        logger.warning(
            "Homeless hit its per-run new-description-fetch safety cap (%s=%d) — "
            "remaining new listings this run get no description and will be picked "
            "up in a later run instead of spending unbounded ZenRows credits in one "
            "shot.",
            _HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_ENV_VAR,
            max_new_description_fetches,
        )

    descriptions = asyncio.run(
        _fetch_concurrently(
            [item["url"] for item in items_to_fetch],
            fetch_homeless_description,
            _HOMELESS_DESCRIPTION_FETCH_CONCURRENCY,
        )
    )
    for item, description in zip(items_to_fetch, descriptions):
        item["description"] = description

    for raw_item in raw_items:
        normalized = normalize(raw_item, source=Source.HOMELESS, deal_type=DealType.RENT)
        if normalized is not None:
            normalized_items.append(normalized)
        else:
            errors += 1

    return normalized_items, seen_external_ids, fetched, errors, all_succeeded


# 2026-09-22: task #7/#8 (never started before tonight) — confirmed live
# (diagnose-facebook-marketplace-page-structure.yaml, url_path=category/propertyforsale/) that
# Facebook Marketplace's real for-sale category is a genuine, separate feed at this exact path:
# real 200, 24 real MarketplaceFeedListingStory nodes wrapping a real GroupCommerceProductItem
# listing type (distinct from rentals' own listing type), with real listing_price/
# strikethrough_price/min_listing_price/max_listing_price fields a rental listing never carries.
# Never guessed — same "diagnose before wiring" discipline as every other source in this project.
_FACEBOOK_MARKETPLACE_CATEGORIES: tuple[tuple[str, str], ...] = (
    (facebook_client.DEFAULT_URL_PATH, DealType.RENT),
    ("category/propertyforsale/", DealType.SALE),
)


def _scrape_facebook() -> tuple[list, set[str], int, int, bool]:
    """Returns the same (normalized_items, seen_external_ids, fetched, errors, all_succeeded)
    shape as _scrape_yad2. Unlike every other source, a Facebook listing's real CITY is genuinely
    unknown until its own detail page is fetched (see facebook_client.py's own module docstring —
    the search feed's own location is lat/lng only) — so, unlike Komo/Homeless's optional
    enrichment, a listing whose detail fetch fails or doesn't yield a real city is skipped
    ENTIRELY this run (never upserted with city=None), same as Komo's own "capped-out new id is
    simply retried next run" pattern (it stays out of `known_ids`, so nothing here marks it done).

    An already-known listing is also skipped entirely, never re-upserted — real, documented gap,
    same as Komo's own (see that function's own docstring): the search feed DOES carry a fresh
    price for every listing, known or new, but re-normalizing a known listing here with
    city=None (not re-fetched) would silently clobber its already-good city on the UPDATE path in
    _upsert_listings. Not worth the complexity of a separate "refresh price only" path yet at this
    project's current, tiny expected Facebook volume — revisit if that turns out wrong.

    2026-09-22: now loops over _FACEBOOK_MARKETPLACE_CATEGORIES (rent + forsale) instead of just
    rent — both categories share ONE known_ids set (a Facebook item id is globally unique
    regardless of category, so no cross-category collision risk) and, more importantly, ONE
    combined _facebook_max_new_detail_fetches_per_run() budget and ONE shared pacing counter: this
    is an ACCOUNT-SAFETY cap on total new requests against the dedicated account this run, not a
    per-category allowance, so adding a second category must not silently double the account's
    real request exposure. A failure fetching one category's search results (FacebookFetchError)
    is logged and counted but does not abort the other category — same "one failed sub-fetch
    doesn't kill the whole run" convention as _scrape_yad2's per-region loop."""
    fetched = 0
    errors = 0
    normalized_items = []
    seen_external_ids: set[str] = set()
    all_succeeded = True

    known_ids = _fetch_known_external_ids(Source.FACEBOOK_MARKETPLACE)
    max_new_detail_fetches = _facebook_max_new_detail_fetches_per_run()
    new_detail_fetches_this_run = 0
    cap_logged = False

    for url_path, deal_type in _FACEBOOK_MARKETPLACE_CATEGORIES:
        try:
            raw_items = list(fetch_facebook_results(url_path))
        except FacebookFetchError:
            logger.exception(
                "Failed to fetch Facebook Marketplace search results for url_path=%r — "
                "skipping this category this run", url_path,
            )
            errors += 1
            all_succeeded = False
            continue

        for raw_item in raw_items:
            fetched += 1
            external_id = raw_item["id"]
            seen_external_ids.add(external_id)

            if external_id in known_ids:
                continue  # not re-upserted this run — see this function's own docstring

            if new_detail_fetches_this_run >= max_new_detail_fetches:
                if not cap_logged:
                    logger.warning(
                        "Facebook hit its per-run new-detail-fetch safety cap (%s=%d) — "
                        "remaining new listings this run (across both categories) are skipped "
                        "and will be picked up in a later run instead of making unbounded "
                        "requests against the live account in one shot.",
                        _FACEBOOK_MAX_NEW_DETAIL_FETCHES_ENV_VAR, max_new_detail_fetches,
                    )
                    cap_logged = True
                continue

            if new_detail_fetches_this_run > 0:
                time.sleep(random.uniform(*_FACEBOOK_DETAIL_FETCH_PACING_SECONDS_RANGE))
            new_detail_fetches_this_run += 1
            detail = fetch_facebook_listing_detail(external_id)
            if detail is None or not detail.get("city"):
                errors += 1
                continue  # no real city to place it in any city-scoped filter — retried next run

            raw_item["city"] = detail["city"]
            raw_item["description"] = detail.get("description")
            normalized = normalize(raw_item, source=Source.FACEBOOK_MARKETPLACE, deal_type=deal_type)
            if normalized is not None:
                normalized_items.append(normalized)
            else:
                errors += 1

    return normalized_items, seen_external_ids, fetched, errors, all_succeeded


def _scrape_facebook_groups() -> tuple[list, set[str], int, int, bool]:
    """Returns the same (normalized_items, seen_external_ids, fetched, errors, all_succeeded)
    shape as _scrape_yad2. A genuine no-op (returns immediately, all_succeeded=True) when
    _facebook_groups_tracked_ids() is empty — no group ids configured is not an error, just nothing
    to do yet (see PROJECT_STATE.md, 2026-09-21/22: only one real group confirmed as of this
    writing, more to be added to FACEBOOK_GROUPS_TRACKED_IDS as the owner sends them).

    Two-stage, same "discover cheap, enrich only what's genuinely new" pattern as _scrape_facebook:
    fetch_home_feed_post_ids covers every tracked group in ONE request, then
    fetch_facebook_group_post_detail is only called for a post_id not already in known_ids. Unlike
    _scrape_facebook, there's no "skip if enrichment fails" requirement for city (a Group post never
    has one at all — see facebook_groups_client.py's own module docstring) — a failed detail fetch
    here is just a real error, retried automatically next run since the post_id never enters
    known_ids."""
    fetched = 0
    errors = 0
    normalized_items = []
    seen_external_ids: set[str] = set()

    tracked_group_ids = _facebook_groups_tracked_ids()
    if not tracked_group_ids:
        return normalized_items, seen_external_ids, fetched, errors, True

    known_ids = _fetch_known_external_ids(Source.FACEBOOK_GROUPS)
    max_new_detail_fetches = _facebook_groups_max_new_detail_fetches_per_run()
    new_detail_fetches_this_run = 0
    cap_logged = False

    try:
        pairs = fetch_home_feed_post_ids(tracked_group_ids)
    except FacebookGroupsFetchError:
        logger.exception(
            "Failed to fetch Facebook home feed for Groups discovery — skipping this source this run"
        )
        return normalized_items, seen_external_ids, fetched, 1, False

    for group_id, post_id in pairs:
        fetched += 1
        seen_external_ids.add(post_id)

        if post_id in known_ids:
            continue

        if new_detail_fetches_this_run >= max_new_detail_fetches:
            if not cap_logged:
                logger.warning(
                    "Facebook Groups hit its per-run new-detail-fetch safety cap (%s=%d) — "
                    "remaining new posts this run are skipped and will be picked up in a later "
                    "run instead of making unbounded requests against the live account in one shot.",
                    _FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_ENV_VAR, max_new_detail_fetches,
                )
                cap_logged = True
            continue

        if new_detail_fetches_this_run > 0:
            time.sleep(random.uniform(*_FACEBOOK_DETAIL_FETCH_PACING_SECONDS_RANGE))
        new_detail_fetches_this_run += 1
        detail = fetch_facebook_group_post_detail(group_id, post_id)
        if detail is None:
            errors += 1
            continue

        normalized = normalize(detail, source=Source.FACEBOOK_GROUPS, deal_type=DealType.RENT)
        if normalized is not None:
            normalized_items.append(normalized)
        else:
            errors += 1

    return normalized_items, seen_external_ids, fetched, errors, True


# 2026-09-13: one entry per source this project scrapes — each a (source, scrape_fn) pair, where
# scrape_fn takes no arguments and returns _scrape_yad2's own (normalized_items, seen_external_ids,
# fetched, errors, all_succeeded) shape. run_once() below loops over this list generically instead
# of three copy-pasted blocks, so adding a fourth source later means one line here, not editing
# run_once() itself. Order doesn't matter (each source's upsert/delisting is independent; only
# notifications run once at the end, over ALL sources' new listings/price changes combined).
_ALL_SOURCE_SCRAPERS: tuple[tuple[str, Callable[[], tuple]], ...] = (
    (Source.YAD2, _scrape_yad2),
    (Source.KOMO, _scrape_komo),
    (Source.HOMELESS, _scrape_homeless),
    (Source.FACEBOOK_MARKETPLACE, _scrape_facebook),
    (Source.FACEBOOK_GROUPS, _scrape_facebook_groups),
)

_FACEBOOK_KILL_SWITCHED_SOURCES = (Source.FACEBOOK_MARKETPLACE, Source.FACEBOOK_GROUPS)


def _active_source_scrapers() -> tuple[tuple[str, Callable[[], tuple]], ...]:
    """Which sources THIS run actually scrapes. Facebook (both Marketplace and Groups) is a real
    kill-switch case, not just another source — see _SCRAPE_SOURCES_ENV_VAR's own comment: neither
    ever runs unless explicitly opted into via SCRAPE_SOURCES, so neither deploying this code nor
    FACEBOOK_COOKIES existing in the secret can, by itself, start hitting the live Facebook account.
    The main scraper's own CronJob never sets SCRAPE_SOURCES at all, so its default here (every
    source except both Facebook ones) is exactly today's existing behavior, unchanged; a separate
    CronJob sets SCRAPE_SOURCES=facebook_marketplace (or ...,facebook_groups) explicitly, on its
    own schedule."""
    raw = os.environ.get(_SCRAPE_SOURCES_ENV_VAR, "").strip()
    if raw:
        wanted = {s.strip() for s in raw.split(",") if s.strip()}
        return tuple((source, fn) for source, fn in _ALL_SOURCE_SCRAPERS if source in wanted)
    return tuple(
        (source, fn)
        for source, fn in _ALL_SOURCE_SCRAPERS
        if source not in _FACEBOOK_KILL_SWITCHED_SOURCES
    )


async def _scrape_sources_concurrently(
    active_sources: tuple[tuple[str, Callable[[], tuple]], ...]
) -> tuple[tuple, ...]:
    """Runs every active source's own scrape_fn() CONCURRENTLY instead of one after another — see
    _KOMO_DETAIL_FETCH_CONCURRENCY's own comment above for why this is safe (independent websites,
    no change in the request rate any single one sees; Yad2's own deliberate anti-detection pacing
    inside _scrape_yad2 is unaffected either way). Each scrape_fn is itself a blocking/synchronous
    function — some (_scrape_komo, _scrape_homeless) make their OWN internal asyncio.run() call for
    their own bounded per-listing concurrency; safe to nest, since asyncio.to_thread runs each one
    in a genuine OS thread with no event loop of its own, so that inner asyncio.run() creates its
    own independent loop — no conflict. Returns results in the SAME order as `active_sources`
    (asyncio.gather preserves order) — same "let a genuine bug propagate and fail the whole run
    loudly" behavior as the previous sequential loop, since every scrape_fn already catches and
    reports its own real fetch failures internally (see each one's own docstring) rather than
    raising them out."""
    return tuple(
        await asyncio.gather(*(asyncio.to_thread(scrape_fn) for _source, scrape_fn in active_sources))
    )


def run_once() -> dict[str, int]:
    fetched = 0
    errors = 0
    all_normalized_items = []
    # Per-source (seen_external_ids, scraped_city_names, all_succeeded) — delisting runs once per
    # source, right after that source's own upsert, using ONLY that source's own results (see
    # _mark_delisted's own docstring for why Komo/Homeless/Yad2 must never share each other's
    # "seen" sets — a listing "not seen" in Komo's run says nothing about Yad2/Homeless).
    per_source_delisting_input: dict[str, tuple[set[str], set[str], bool]] = {}

    active_sources = _active_source_scrapers()
    logger.info(
        "Scraping %d source(s) concurrently: %s",
        len(active_sources), ", ".join(source for source, _fn in active_sources),
    )
    results = asyncio.run(_scrape_sources_concurrently(active_sources))
    for (source, _scrape_fn), (
        normalized_items, seen_external_ids, source_fetched, source_errors, all_succeeded
    ) in zip(active_sources, results):
        fetched += source_fetched
        errors += source_errors
        all_normalized_items.extend(normalized_items)
        scraped_city_names = {item.city for item in normalized_items if item.city}
        per_source_delisting_input[source] = (seen_external_ids, scraped_city_names, all_succeeded)

    with get_session() as session:
        new_ids, price_change_pairs = _upsert_listings(session, all_normalized_items)

        # Before anything reads the new listings back out (delisting check doesn't touch them, but
        # the notification step below does) — enriching first means notifications already carry
        # the real description/photos/amenities instead of only the search-card fields. A no-op,
        # fast, if Bright Data isn't configured yet, or for any Komo/Homeless-sourced new_ids (see
        # that function's own docstring — it filters to source == Source.YAD2 internally).
        enriched_count = asyncio.run(_enrich_new_listings_via_bright_data(session, new_ids))

        delisted_count = 0
        for source, (seen_external_ids, scraped_city_names, all_succeeded) in (
            per_source_delisting_input.items()
        ):
            if all_succeeded and seen_external_ids:
                delisted_count += _mark_delisted(session, source, seen_external_ids, scraped_city_names)
            elif not all_succeeded:
                logger.warning(
                    "Skipping delisting check this run for source=%s — at least one region/city "
                    "failed to fetch, so the seen-listings set is incomplete and can't be trusted "
                    "for delisting.",
                    source,
                )

        new_listings = (
            list(session.scalars(select(Listing).where(Listing.id.in_(new_ids))))
            if new_ids
            else []
        )
        price_change_ids = [listing_id for listing_id, _old_price in price_change_pairs]
        listings_by_id = {
            listing.id: listing
            for listing in (
                session.scalars(select(Listing).where(Listing.id.in_(price_change_ids)))
                if price_change_ids
                else []
            )
        }
        price_change_events = [
            (listings_by_id[listing_id], old_price)
            for listing_id, old_price in price_change_pairs
            if listing_id in listings_by_id
        ]

        summary = {
            "fetched": fetched,
            "new": len(new_listings),
            "bright_data_enriched": enriched_count,
            "price_changes": len(price_change_events),
            "delisted": delisted_count,
            "errors": errors,
        }
        if not (new_listings or price_change_events):
            summary.update(
                {"matched": 0, "notifications_sent": 0, "price_change_notifications_sent": 0}
            )
        elif _notifications_suspended():
            owner_telegram_user_id = os.environ.get("OWNER_TELEGRAM_USER_ID", "").strip() or None
            if owner_telegram_user_id is None:
                # Can't restrict-to-owner without an owner id to restrict to — falls back to a
                # full skip rather than risk accidentally notifying everyone (only_telegram_user_id
                # =None in run_notifications means "no restriction at all", the opposite of intent
                # here).
                logger.warning(
                    "%s is set but OWNER_TELEGRAM_USER_ID is not — falling back to a full "
                    "notification skip for %d new listing(s)/%d price change(s) this run (can't "
                    "restrict to the owner with no owner id configured).",
                    _NOTIFICATIONS_SUSPENDED_ENV_VAR, len(new_listings), len(price_change_events),
                )
                summary.update(
                    {
                        "matched": 0,
                        "notifications_sent": 0,
                        "price_change_notifications_sent": 0,
                        "notifications_suspended": True,
                    }
                )
            else:
                logger.warning(
                    "%s is set — restricting notifications to the owner only (telegram_user_id="
                    "%s) for %d new listing(s)/%d price change(s) this run; every other user is "
                    "skipped (still upserted/delisted normally, and will get their real "
                    "notification once this is lifted).",
                    _NOTIFICATIONS_SUSPENDED_ENV_VAR, owner_telegram_user_id,
                    len(new_listings), len(price_change_events),
                )
                summary.update(
                    asyncio.run(
                        run_notifications(
                            session,
                            new_listings,
                            price_change_events,
                            only_telegram_user_id=owner_telegram_user_id,
                        )
                    )
                )
                summary["notifications_suspended"] = True
        else:
            summary.update(
                asyncio.run(run_notifications(session, new_listings, price_change_events))
            )

    return summary


if __name__ == "__main__":
    try:
        run_summary = run_once()
    except Exception:
        logger.exception("Scraper run failed")
        sys.exit(1)
    logger.info("Scraper run summary: %s", run_summary)
