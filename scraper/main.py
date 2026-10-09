"""Entrypoint: run one scrape+match+notify cycle, then exit. Triggered periodically by the k8s
CronJob (see charts/todira), or manually via `docker compose run --rm scraper` locally.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import random
import sys
import time
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from dedup import find_duplicate_listing
from todira_common import gemini_url_detail
from todira_common.db import get_session
from todira_common.enums import DealType, NotificationReason, Source
from todira_common import whatsapp_guard
from todira_common.models import Listing, SentNotification
import facebook_client
from facebook_client import FacebookFetchError
from facebook_client import fetch_listing_detail as fetch_facebook_listing_detail
from facebook_client import fetch_search_results as fetch_facebook_results
from facebook_groups_client import FacebookGroupsFetchError
from facebook_groups_client import fetch_home_feed_post_ids
from facebook_groups_client import fetch_post_detail as fetch_facebook_group_post_detail
import homeless_client
from homeless_client import HomelessFetchError
from homeless_client import fetch_listing_description as fetch_homeless_description
from homeless_client import fetch_search_results as fetch_homeless_results
import komo_client
from komo_client import KomoFetchError, fetch_all_coordinate_ids
from komo_client import fetch_listing_detail as fetch_komo_listing_detail
from normalize import normalize
from notifier import run_notifications
from whatsapp_checkin import run_whatsapp_checkins
from renewal_reminder import run_renewal_reminders
from whatsapp_cost_guard import run_cost_guard
from yad2_client import (
    REGION_SLUGS,
    REGIONS_ON_MAP_API,
    Yad2FetchError,
    Yad2MapFetchError,
    TileSweepStats,
    fetch_forsale_region,
    fetch_region_pages,
    fetch_region_tiles,
    fetch_region_via_map_api,
    tile_max_requests,
    tile_max_seconds,
    sale_tile_sweep_enabled,
    tile_sweep_enabled,
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
_BRIGHT_DATA_ENRICH_CONCURRENCY = 1  # 2026-10-05: Gemini calls are serialised anyway (see gemini_url_detail)

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

# 2026-09-26: same real gap as Yad2's own (see _BRIGHT_DATA_BACKFILL_MAX_PER_RUN_ENV_VAR's comment
# below) — confirmed live, Homeless sat at only 28.6% description coverage despite this project's
# own comment above claiming a capped-out listing "is picked up in a later run": it isn't — a
# listing already in the DB is never "new" again, so _scrape_homeless's own new-listing fetch never
# gets a second shot at it, and unlike Yad2, Homeless has NO safety-net fallback at all (scraper/
# notifier.py's _maybe_fetch_description and website/main.py's lazy backfill are both scoped to
# Source.YAD2 only — homeless_client.fetch_listing_description was assumed reliable enough on its
# own not to need one, which the real numbers disprove). Same backfill pattern as Yad2's own.
_HOMELESS_BACKFILL_MAX_PER_RUN_ENV_VAR = "HOMELESS_BACKFILL_MAX_PER_RUN"
_DEFAULT_HOMELESS_BACKFILL_MAX_PER_RUN = 30

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
# 2026-10-02: eager enrichment of every genuinely-new Yad2 listing STAYS ON (owner: "don't turn it
# off") at 50 per run — real volume is ~400-600 new listings/day over 14 runs (~43/run).
# 2026-10-05: the fetch is Gemini-only now (free, no Bright Data cost): ~7s between requests, so a full
# run of 50 takes ~6 minutes; when every Gemini model is out of daily quota the calls return instantly and the
# listing simply keeps its search-card fields until a viewer opens it (todira_common/listing_enrichment.py) or
# it is about to be sent to a paying user (notifier._maybe_fetch_description).
_DEFAULT_BRIGHT_DATA_ENRICH_MAX_PER_RUN = 50

# 2026-09-26: real gap found live (diagnose-description-coverage-per-source.yaml) — only 6.2%
# description coverage among the 470 most-recent active Yad2 listings, despite Bright Data being
# configured and not suspended. Root cause: _enrich_new_listings_via_bright_data only ever gets ONE
# shot at a listing (the run it's first discovered), capped at _DEFAULT_BRIGHT_DATA_ENRICH_MAX_PER_
# RUN above — anything past that cap, or whose one attempt failed, was meant to get a second chance
# via notifier.py's _maybe_fetch_description (only fires if the listing matches a PAYING/trial user
# at notification time) or website/main.py's _fill_missing_descriptions_in_background (only fires
# if a has_access viewer happens to open that exact listing on /apartments or /liked) — both narrow
# enough in practice that most Yad2 listings never hit either trigger and just sit with no
# description forever. This is the real, unconditional catch-up: every run, backfill a bounded
# number of still-missing EXISTING Yad2 listings (any age), same safety-cap reasoning as the
# new-listing cap above (a real per-request Web Unlocker cost/timeout, not "assume the backlog is
# small").
_BRIGHT_DATA_BACKFILL_MAX_PER_RUN_ENV_VAR = "BRIGHT_DATA_BACKFILL_MAX_PER_RUN"
# 2026-10-02: default 0 = backfill OFF, same cost reason as _DEFAULT_BRIGHT_DATA_ENRICH_MAX_PER_RUN
# above (it kept chasing every Yad2 listing missing a description, ~420 requests/day at the old 30).
_DEFAULT_BRIGHT_DATA_BACKFILL_MAX_PER_RUN = 0

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
#
# RENT vs SALE (2026-09-24): unlike every other source this project scrapes, a Facebook Group has
# no per-post deal-type field at all (see facebook_groups_client.py's own docstring) — a group is
# rent-focused or sale-focused (or mixed) by its own name/purpose, not by anything in a post's own
# payload. Only ever confirmed one real group so far ("פשפשוק - דירות להשכרה" — a RENT group), so
# _scrape_facebook_groups below used to hardcode DealType.RENT for every post from every tracked
# group; a sale-focused group added to the ORIGINAL env var would have had its own listings silently
# mislabeled as rentals. Kept as two separate env vars (not one var + a per-id suffix) — same
# already-established rent/sale-as-separate-inputs shape every other source in this project uses
# (yad2_client.SEARCH_PAGE_URL/SALE_SEARCH_PAGE_URL, komo_client, homeless_client, facebook_client's
# own category split) — rather than inventing a new per-source convention here. Empty (the default,
# today's actual state — no real sale group id has been provided yet) means exactly today's existing
# single-rent-group behavior, unchanged.
_FACEBOOK_GROUPS_TRACKED_IDS_ENV_VAR = "FACEBOOK_GROUPS_TRACKED_IDS"
_FACEBOOK_GROUPS_SALE_TRACKED_IDS_ENV_VAR = "FACEBOOK_GROUPS_SALE_TRACKED_IDS"
# Same account-safety reasoning as _DEFAULT_FACEBOOK_MAX_NEW_DETAIL_FETCHES_PER_RUN above, just a
# smaller default — the home feed's own real per-run yield was 2 new posts across 2 groups in the
# one live test so far (see PROJECT_STATE.md, 2026-09-21/22), nowhere near Marketplace's ~25;
# raise this only with real evidence a legitimate run is actually hitting the cap.
_FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_ENV_VAR = "FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_PER_RUN"
_DEFAULT_FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_PER_RUN = 15


def _facebook_groups_tracked_ids() -> set[str]:
    raw = os.environ.get(_FACEBOOK_GROUPS_TRACKED_IDS_ENV_VAR, "").strip()
    return {s.strip() for s in raw.split(",") if s.strip()}


def _facebook_groups_sale_tracked_ids() -> set[str]:
    raw = os.environ.get(_FACEBOOK_GROUPS_SALE_TRACKED_IDS_ENV_VAR, "").strip()
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


def _homeless_backfill_max_per_run() -> int:
    raw = os.environ.get(_HOMELESS_BACKFILL_MAX_PER_RUN_ENV_VAR, "").strip()
    if not raw:
        return _DEFAULT_HOMELESS_BACKFILL_MAX_PER_RUN
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%r (not an int) — using default %d",
            _HOMELESS_BACKFILL_MAX_PER_RUN_ENV_VAR, raw, _DEFAULT_HOMELESS_BACKFILL_MAX_PER_RUN,
        )
        return _DEFAULT_HOMELESS_BACKFILL_MAX_PER_RUN


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


def _bright_data_backfill_max_per_run() -> int:
    raw = os.environ.get(_BRIGHT_DATA_BACKFILL_MAX_PER_RUN_ENV_VAR, "").strip()
    if not raw:
        return _DEFAULT_BRIGHT_DATA_BACKFILL_MAX_PER_RUN
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%r (not an int) — using default %d",
            _BRIGHT_DATA_BACKFILL_MAX_PER_RUN_ENV_VAR, raw,
            _DEFAULT_BRIGHT_DATA_BACKFILL_MAX_PER_RUN,
        )
        return _DEFAULT_BRIGHT_DATA_BACKFILL_MAX_PER_RUN


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
    2026-09-02 per an explicit request that both directions get a re-notification. A detected
    change is also persisted onto the row itself (previous_price/price_changed_at, 2026-09-24) —
    price_change_events is consumed once by notifier.py and gone after this call returns, so
    without persisting it there'd be nothing left for the website card's own price-drop/increase
    badge to read on a later page load. This is a
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
        update_values = item.model_dump()
        # 2026-09-25 real bug found via a fresh code-review pass: `NormalizedListing` (item's own
        # schema) has no `scraped_at` field, and the column has no `onupdate` — so this UPDATE never
        # touched it, leaving `scraped_at` frozen at the listing's original INSERT time forever. That
        # silently defeated _mark_delisted's own min_hours_before_delist grace period (see its
        # docstring's "2026-09-25" entry): the WHERE clause `scraped_at < now() - min_hours_before_delist`
        # was comparing against "time of first-ever discovery", not "time last confirmed still active",
        # so any listing older than the grace window since its original insert — i.e. essentially every
        # listing that isn't brand new — qualified for delisting on the very first run that happened to
        # miss it, reproducing the exact mass-delisting bug the grace period was built to prevent.
        # Explicit assignment here (not `onupdate=func.now()` on the column) so only a genuine
        # confirmed-still-there re-scrape advances it — an unrelated UPDATE elsewhere (e.g. a user
        # like/hide reaction, or _mark_delisted's own delist pass) must never bump it.
        update_values["scraped_at"] = func.now()
        # 2026-09-25 real bug found live (owner asked why Yad2/Homeless listings kept losing their
        # description after having one): `description` is NEVER present on a plain search-card
        # scrape — it only ever gets filled in by a separate, one-time enrichment fetch (Bright
        # Data for Yad2, fetch_listing_description for Homeless/Komo), which runs once for a
        # genuinely NEW listing only (see this function's own docstring, _maybe_fetch_description,
        # _scrape_homeless's own comment). Every later run's `item.description` is therefore always
        # None for an already-known listing, and this blind `item.model_dump()` UPDATE was wiping
        # the real description straight back to NULL on the very next scrape after it was fetched —
        # so a listing only ever showed a description for the one run right after it was enriched,
        # explaining the "some Yad2 listings have one, most don't" report exactly. Never let an
        # UPDATE erase an existing non-null description with a null one; other fields aren't
        # touched here since (unlike description) they're normally re-supplied by every scrape.
        if item.description is None:
            update_values.pop("description", None)
        if item.price is not None and old_price is not None and item.price != old_price:
            price_change_events.append((existing_id, old_price))
            # 2026-09-24: persist the change itself (previous_price/price_changed_at), not just
            # the event — the website card's own price-drop/increase badge (real owner request,
            # matching dorin.app's card) reads these after the fact; price_change_events above is
            # consumed once by notifier.py and gone, this is what's left for the card to render.
            update_values["previous_price"] = old_price
            update_values["price_changed_at"] = func.now()

        session.execute(table.update().where(table.c.id == existing_id).values(**update_values))

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
    # 2026-10-05: Gemini only (owner decision) — no longer gated on the Bright Data key/kill-switch.
    if not new_ids or not gemini_url_detail.is_enabled():
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
        # 2026-09-26: corrected — a listing skipped here is NOT "picked up in a later run" (a
        # listing already in the DB is never "new" again, so this function never gets a second
        # shot at it; see scraper/notifier.py's own docstring on this). It DOES still get a real
        # second chance, just via a different path: notifier.py's _maybe_fetch_description (at
        # notification time, if it matches a paying user) or website/main.py's
        # _fill_missing_descriptions_in_background (lazily, when a paying user views /apartments)
        # — both of which now call the same working bright_data_client.
        # fetch_yad2_description_via_web_unlocker this function itself uses.
        logger.warning(
            "Yad2 Bright Data enrichment hit its per-run safety cap (%s=%d) — remaining "
            "%d new listings this run keep only their search-card fields (no description) here; "
            "notifier.py's/website's own fallback fetches still cover them, instead of risking "
            "one run stalling for a long time on Web Unlocker's own per-request timeout.",
            _BRIGHT_DATA_ENRICH_MAX_PER_RUN_ENV_VAR, max_per_run, len(id_url_pairs) - max_per_run,
        )
        id_url_pairs = id_url_pairs[:max_per_run]

    return await _fetch_and_apply_yad2_detail_updates(session, id_url_pairs, log_context="enrichment")


async def _fetch_and_apply_yad2_detail_updates(
    session, id_url_pairs: list[tuple[int, str]], *, log_context: str
) -> int:
    """Shared fetch-and-apply tail for both _enrich_new_listings_via_bright_data (above) and
    _backfill_missing_yad2_descriptions (below) — same bounded-concurrency Web Unlocker fetch,
    same best-effort "one bad fetch never blocks the rest" handling, same Core-level table.update
    (see _enrich_new_listings_via_bright_data's own comment on why Core, not the ORM). `log_context`
    only distinguishes the two callers in a failure's log line ("enrichment" vs "backfill")."""
    table = Listing.__table__
    semaphore = asyncio.Semaphore(_BRIGHT_DATA_ENRICH_CONCURRENCY)

    async def _fetch_one(listing_id: int, url: str) -> tuple[int, dict] | None:
        async with semaphore:
            # 2026-10-05: Gemini's URL-context tool ONLY (owner decision: no paid Bright Data fallback for
            # listing details). gemini_url_detail serialises and spaces its own requests and skips a model that
            # is out of quota; None just means this listing keeps its search-card fields until somebody views it
            # (todira_common/listing_enrichment.py fills it in then).
            gemini_updates = await asyncio.to_thread(gemini_url_detail.fetch_yad2_detail_updates, url)
        return (listing_id, gemini_updates) if gemini_updates else None

    results = await asyncio.gather(
        *(_fetch_one(listing_id, url) for listing_id, url in id_url_pairs), return_exceptions=True
    )

    applied_count = 0
    for (listing_id, url), result in zip(id_url_pairs, results):
        if isinstance(result, BaseException):
            logger.exception(
                "Bright Data %s failed for listing id=%s url=%s", log_context, listing_id, url,
                exc_info=result,
            )
            continue
        if result is None:
            continue
        _listing_id, updates = result
        session.execute(table.update().where(table.c.id == listing_id).values(**updates))
        applied_count += 1

    session.commit()
    return applied_count


async def _backfill_missing_yad2_descriptions(session) -> int:
    """Real gap found live 2026-09-26 (diagnose-description-coverage-per-source.yaml): only 6.2%
    description coverage among the 470 most-recent active Yad2 listings, despite Bright Data being
    configured and not suspended. _enrich_new_listings_via_bright_data above only ever gets ONE shot
    at a listing — the run it's first discovered, capped at _bright_data_enrich_max_per_run() new
    listings per run — and a listing skipped by that cap, or whose one attempt failed, only gets a
    real second chance via notifier.py's _maybe_fetch_description (fires only if the listing matches
    a PAYING/trial user at notification time) or website/main.py's
    _fill_missing_descriptions_in_background (fires only if a has_access viewer happens to open that
    exact listing on /apartments or /liked) — both narrow enough in practice that most Yad2 listings
    never hit either trigger and sit with no description indefinitely.

    This is the real, unconditional catch-up: every run, independent of what was scraped this run,
    backfill a bounded number (_bright_data_backfill_max_per_run(), same safety-cap reasoning as the
    new-listing cap above — a real per-request Web Unlocker cost/timeout, not "assume the backlog is
    small") of still-missing EXISTING active Yad2 listings, oldest-scraped-first isn't used
    deliberately (a very old listing is more likely to have gone stale/removed already — see
    is_delisted below — so newest-first spends the budget where it's most likely to still matter to
    an actual viewer).

    Same no-op guards as the new-listing enrichment (API key unset, BRIGHT_DATA_ENRICHMENT_SUSPENDED)
    — always safe to call every run regardless of whether Bright Data is configured yet.

    Returns how many listings were actually backfilled."""
    if not gemini_url_detail.is_enabled():
        return 0

    table = Listing.__table__
    max_per_run = _bright_data_backfill_max_per_run()
    id_url_pairs = session.execute(
        select(table.c.id, table.c.url)
        .where(
            table.c.source == Source.YAD2,
            table.c.is_delisted.is_(False),
            table.c.description.is_(None),
        )
        .order_by(table.c.scraped_at.desc())
        .limit(max_per_run)
    ).all()
    if not id_url_pairs:
        return 0

    return await _fetch_and_apply_yad2_detail_updates(session, id_url_pairs, log_context="backfill")


async def _backfill_missing_homeless_descriptions(session) -> int:
    """Same real gap as Yad2's own backfill above, confirmed live: only 28.6% description coverage
    among recent active Homeless listings. _scrape_homeless's own new-listing description fetch
    only ever gets one shot at a listing (capped at _homeless_max_new_description_fetches_per_run()
    new listings per run), and — unlike Yad2 — Homeless has NO safety-net fallback at all: scraper/
    notifier.py's _maybe_fetch_description and website/main.py's own lazy backfill are both scoped
    to Source.YAD2 only, on the (empirically wrong) assumption that Homeless's own one-shot fetch is
    reliable enough not to need a second chance.

    This is the same unconditional catch-up pattern: every run, independent of what was scraped
    this run, backfill a bounded number (_homeless_backfill_max_per_run()) of still-missing EXISTING
    active Homeless listings, newest-scraped-first (same "spend the budget where it's most likely to
    still matter to an actual viewer" reasoning as Yad2's own).

    No separate ZENROWS_API_KEY guard here — homeless_client.fetch_listing_description already
    fails soft (returns None on a missing key, same as every other failure mode), matching how
    _scrape_homeless's own new-listing fetch already calls it with no key check of its own.

    Returns how many listings were actually backfilled."""
    table = Listing.__table__
    max_per_run = _homeless_backfill_max_per_run()
    id_url_pairs = session.execute(
        select(table.c.id, table.c.url)
        .where(
            table.c.source == Source.HOMELESS,
            table.c.is_delisted.is_(False),
            table.c.description.is_(None),
        )
        .order_by(table.c.scraped_at.desc())
        .limit(max_per_run)
    ).all()
    if not id_url_pairs:
        return 0

    descriptions = await _fetch_concurrently(
        [url for _listing_id, url in id_url_pairs],
        fetch_homeless_description,
        _HOMELESS_DESCRIPTION_FETCH_CONCURRENCY,
    )

    backfilled_count = 0
    for (listing_id, _url), description in zip(id_url_pairs, descriptions):
        if not description:
            continue
        session.execute(table.update().where(table.c.id == listing_id).values(description=description))
        backfilled_count += 1

    session.commit()
    return backfilled_count


_DEFAULT_MIN_HOURS_BEFORE_DELIST = 3

# How far back run_once() looks for active listings that never produced even one successful 'new'
# notification, to retry them alongside this run's genuinely-new listings — see that call site's
# own comment for the real, silent-permanent-notification-loss bug this closes. 7 days: generous
# enough to catch a listing whose very first attempt failed during a real multi-hour outage
# (WhatsApp API down, a stretch of NOTIFICATIONS_SUSPENDED, etc.), small enough that this query
# stays cheap (bounded by how many listings are scraped in a week, not the whole table).
_RETRY_UNNOTIFIED_HOURS = 24 * 7


def _mark_delisted(
    session,
    source: str,
    seen_external_ids: set[str],
    scraped_city_names: set[str],
    min_hours_before_delist: int = _DEFAULT_MIN_HOURS_BEFORE_DELIST,
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
    mistaken for "everything in these cities disappeared".

    2026-09-25 real bug found via a live code-review pass, confirmed live in production data
    (diagnose-yad2-delisting-flap.yaml): Yad2's own map API (fetch_map_markers) does ONE request
    per region and returns at most ~200 markers — a real per-request cap, not a paged/complete
    result set (the module's own comment already flagged this as a known, unconfirmed risk). A
    busy city easily has more than 200 genuinely-active listings, so any run's response is only a
    SAMPLE of what's really out there — a real active listing simply outside this run's sample
    looks identical, from this function's own point of view, to one that's genuinely gone. Live
    production data confirmed the real damage: 8,552 delisted vs. only 1,860 active Yad2 rent rows
    (an 82% delist rate implausible as genuine turnover), with essentially zero fresh delisting
    activity in the last 24h — a settled-over-delisted backlog, not ongoing correct churn.

    Fix: a listing is only actually marked delisted once it's been missing for
    `min_hours_before_delist` (default 3 — roughly 3 hourly scrape runs), not on the very first run
    that happens not to include it. A genuinely-removed listing still gets caught within a few
    hours; one merely outside a single capped response gets several more chances to reappear in a
    later run's sample before ever being wrongly hidden from users. Cheap insurance for every
    source, not just Yad2 — Komo/Homeless share the same call, and there's no real downside to a
    few extra hours of grace before delisting anywhere."""
    table = Listing.__table__
    newly_delisted = session.execute(
        table.update()
        .where(
            table.c.source == source,
            table.c.is_delisted.is_(False),
            table.c.city.in_(scraped_city_names),
            table.c.external_id.notin_(seen_external_ids),
            table.c.scraped_at < func.now() - func.make_interval(0, 0, 0, 0, min_hours_before_delist),
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


def _find_unnotified_recent_listings(session, exclude_ids: set[int]) -> list[Listing]:
    """Active listings from the last `_RETRY_UNNOTIFIED_HOURS` that have NEVER produced even one
    successful 'new' notification to anyone, excluding `exclude_ids` (this run's own genuinely-new
    listings, already handled separately).

    2026-09-25 real bug fix, found via a live code-review pass: a listing used to be handed to
    run_notifications ONLY on the one run that inserted it (or its own price-change run). If every
    send for it failed that run (WhatsApp API down, a candidate user's Telegram send hitting
    RetryAfter twice, NOTIFICATIONS_SUSPENDED covering the whole run, etc.) — no SentNotification
    row gets written on a failed send (see notifier.py's own sent_on_any_channel gate), so
    _already_notified would correctly allow a retry — but the listing was never reconsidered on any
    LATER run either, since it's no longer "new" and never has a price change. That failure was
    silent and PERMANENT: a user genuinely never got notified about a listing that matched their
    filter, with no way to recover short of a manual DB fix.

    Cheap to find (a plain NOT EXISTS against sent_notifications, bounded to a recent window — not
    a full-table scan) and self-limiting: the very first successful send removes a listing from
    this set on the next run, same as it always would have. A listing nobody has ever matched
    (normal — most listings match no one's filter) also has zero SentNotification rows and gets
    re-evaluated here too; harmless, just a cheap no-op re-check, not a bug.

    The window is measured from Listing.first_seen_at (set once on INSERT, migration 0018), NOT
    scraped_at: scraped_at is refreshed on every re-scrape, so using it made "the last 7 days"
    cover every still-active listing — a filter edit that recorded no SentNotification rows could
    then trigger cards for months-old listings on the next run."""
    retry_window_cutoff = func.now() - func.make_interval(0, 0, 0, 0, _RETRY_UNNOTIFIED_HOURS)
    never_notified_exists = (
        select(SentNotification.id)
        .where(
            SentNotification.listing_id == Listing.id,
            SentNotification.reason == NotificationReason.NEW,
        )
        .exists()
    )
    return [
        listing
        for listing in session.scalars(
            select(Listing).where(
                Listing.is_delisted.is_(False),
                # A cross-source duplicate row is deliberately never notified (see _upsert_listings),
                # so it would pass ~never_notified_exists forever and re-send the same apartment.
                Listing.duplicate_of_id.is_(None),
                Listing.first_seen_at >= retry_window_cutoff,
                ~never_notified_exists,
            )
        )
        if listing.id not in exclude_ids
    ]


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


# 2026-10-08 tile sweep (see yad2_client.py's "Tile sweep" comment): which Yad2 ids this run found ONLY through the
# sweep (not through the district-wide request), and how the sweep ended - one entry per map ("rent", "forsale").
# Module-level because _scrape_yad2's return shape is shared by every source; a scraper process lives for exactly one run,
# so nothing can leak between runs.
_YAD2_TILE_KINDS = ("rent", "forsale")
_YAD2_TILE_ONLY_IDS: dict[str, set[str]] = {kind: set() for kind in _YAD2_TILE_KINDS}
_YAD2_TILE_STATE: dict[str, dict[str, bool]] = {kind: {"ran": False, "complete": False} for kind in _YAD2_TILE_KINDS}
# The very first complete sweep suddenly finds thousands of ads that were always on Yad2 and merely never in our 200-per-region
# sample. Alerting every matching user about each of them as if it had just been posted would be a flood of old ads, so that
# run stores them quietly (first_seen_at pushed outside the retry window, no notification) and records this flag; every later
# run treats newly found ads as new. Until a complete sweep has happened the flag stays unset, so a first attempt that aborted
# half way does not leave the rest of the backlog to be announced later. Rent and for-sale seed separately.
# "_v2" for rent (2026-10-08): the deeper dense-core sweep finds thousands of old ads the first sweeps never reached; that run must be a
# quiet seed again, so the rent flag is renamed (the old "yad2_tiles_seeded" stays set but is no longer read).
_YAD2_TILES_SEEDED_FLAGS = {"rent": "yad2_tiles_seeded_v2", "forsale": "yad2_sale_tiles_seeded"}
_SEED_BACKDATE_DAYS = 8  # one day more than _RETRY_UNNOTIFIED_HOURS (7 days), so the retry sweep skips them


def _split_seed_backlog(new_rows: list[tuple[int, str]], tile_only_ids: set[str]) -> set[int]:
    """Listing ids (of this run's newly inserted Yad2 rows) that only the tile sweep found - the seed run's backlog."""
    return {listing_id for listing_id, external_id in new_rows if external_id in tile_only_ids}


def _apply_tile_seed_policy(session, new_ids: list[int]) -> list[int]:
    """Returns the ids that should still be announced as new. See _YAD2_TILES_SEEDED_FLAGS' comment."""
    rows = None
    all_backlog: set[int] = set()
    for kind in _YAD2_TILE_KINDS:
        if not _YAD2_TILE_STATE[kind]["ran"]:
            continue
        flag = _YAD2_TILES_SEEDED_FLAGS[kind]
        if whatsapp_guard.get_flag(session, flag):
            continue
        tile_only_ids = _YAD2_TILE_ONLY_IDS[kind]
        backlog: set[int] = set()
        if new_ids and tile_only_ids:
            if rows is None:
                rows = [
                    (row[0], row[1])
                    for row in session.execute(
                        select(Listing.id, Listing.external_id).where(
                            Listing.id.in_(new_ids), Listing.source == Source.YAD2
                        )
                    ).all()
                ]
            backlog = _split_seed_backlog(rows, tile_only_ids)
            if backlog:
                table = Listing.__table__
                session.execute(
                    table.update()
                    .where(table.c.id.in_(backlog))
                    .values(first_seen_at=func.now() - func.make_interval(0, 0, 0, _SEED_BACKDATE_DAYS))
                )
                session.commit()
                logger.info(
                    "Yad2 tile sweep (%s) seed run: stored %d previously unseen ad(s) quietly (no alerts)",
                    kind, len(backlog),
                )
        if _YAD2_TILE_STATE[kind]["complete"]:
            whatsapp_guard.set_flag(session, flag, dt.datetime.now(dt.timezone.utc).isoformat())
        all_backlog |= backlog
    return [listing_id for listing_id in new_ids if listing_id not in all_backlog]


# --- Streaming the sweep into the database (2026-10-08) -----------------------------------------------------------------
# The 18:00 UTC run (rent + for-sale sweeps, ~58k ads) died ~25 minutes in. The cluster is ONE node with 1.9 GiB of memory shared by
# Postgres, the website, the bot and the scraper (node pressure, not the container limit, is what bites), and holding every swept ad
# in memory until one giant upsert at the end both raises the scraper's peak and makes each run re-write ~58k rows. So the sweep now
# writes in chunks while it goes: ads whose row already exists with the same price only get scraped_at refreshed (one bulk UPDATE per
# chunk - "still there", which is all the delisting grace needs); new ads and price changes take the normal upsert. What the
# post-processing in run_once needs (new ids, price changes, cities) is collected here and merged there.
_SWEEP_FLUSH_CHUNK = 1000
_STREAMED_NEW_IDS: list[int] = []
_STREAMED_PRICE_PAIRS: list[tuple[int, int]] = []
_STREAMED_CITIES: set[str] = set()


def _reset_streamed_sweep_state() -> None:
    _STREAMED_NEW_IDS.clear()
    _STREAMED_PRICE_PAIRS.clear()
    _STREAMED_CITIES.clear()


def _flush_sweep_chunk(items: list) -> None:
    """Writes one chunk of swept Yad2 ads. Raises on a database error (the caller treats the sweep as incomplete)."""
    if not items:
        return
    table = Listing.__table__
    with get_session() as session:
        rows = session.execute(
            select(table.c.id, table.c.external_id, table.c.price).where(
                table.c.source == Source.YAD2, table.c.external_id.in_([item.external_id for item in items])
            )
        ).all()
        existing = {row[1]: (row[0], row[2]) for row in rows}
        to_upsert: list = []
        unchanged_ids: list[int] = []
        for item in items:
            known = existing.get(item.external_id)
            if known is not None and known[1] == item.price:
                unchanged_ids.append(known[0])
            else:
                to_upsert.append(item)
        if unchanged_ids:
            session.execute(table.update().where(table.c.id.in_(unchanged_ids)).values(scraped_at=func.now()))
            session.commit()
        if to_upsert:
            try:
                new_ids, price_pairs = _upsert_listings(session, to_upsert)
            except Exception:
                # One bad row must not sink the other 999: undo the failed batch and write the rows one at a time, skipping (and
                # counting) only those that still fail. The 2026-10-09 morning run lost three whole chunks to a single out-of-range
                # number before the schema learned to null such values.
                logger.exception("Yad2 sweep chunk of %d failed - retrying row by row", len(to_upsert))
                session.rollback()
                new_ids, price_pairs, skipped = [], [], 0
                for item in to_upsert:
                    try:
                        one_new, one_pairs = _upsert_listings(session, [item])
                        new_ids.extend(one_new)
                        price_pairs.extend(one_pairs)
                    except Exception:
                        session.rollback()
                        skipped += 1
                if skipped:
                    logger.warning("Yad2 sweep chunk: %d row(s) could not be stored and were skipped", skipped)
            _STREAMED_NEW_IDS.extend(new_ids)
            _STREAMED_PRICE_PAIRS.extend(price_pairs)
    _STREAMED_CITIES.update(item.city for item in items if item.city)


def _run_yad2_tile_sweep(
    kind: str, deal_type: DealType, normalized_items: list, seen_external_ids: set[str]
) -> tuple[int, int, bool]:
    """Sweeps one Yad2 map in pieces (see yad2_client's "Tile sweep" comment), writes what it finds to the database in chunks (see
    the streaming comment above; `normalized_items` is no longer appended to), adds the ids to `seen_external_ids`, and records the
    ids only the sweep found. Returns (ads added, parse errors, sweep complete)."""
    tile_stats = TileSweepStats(max_requests=tile_max_requests(), max_seconds=tile_max_seconds())
    only_ids = _YAD2_TILE_ONLY_IDS[kind]
    only_ids.clear()
    fetched = errors = 0
    buffer: list = []
    write_failed = False

    def _flush() -> None:
        nonlocal buffer, write_failed
        chunk, buffer = buffer, []
        try:
            _flush_sweep_chunk(chunk)
        except Exception:
            logger.exception("Yad2 tile sweep (%s): writing a chunk of %d ads failed", kind, len(chunk))
            write_failed = True

    for region in REGION_SLUGS:
        if region not in REGIONS_ON_MAP_API or tile_stats.aborted or tile_stats.budget_hit:
            continue
        for raw_item in fetch_region_tiles(region, tile_stats, kind=kind):
            external_id = str(raw_item.get("id"))
            if external_id in seen_external_ids:
                continue
            normalized = normalize(raw_item, source=Source.YAD2, deal_type=deal_type)
            fetched += 1
            if normalized is None:
                errors += 1
                continue
            buffer.append(normalized)
            seen_external_ids.add(normalized.external_id)
            only_ids.add(normalized.external_id)
            if len(buffer) >= _SWEEP_FLUSH_CHUNK:
                _flush()
    _flush()
    logger.info(
        "Yad2 tile sweep (%s): requests=%d extra_ads=%d failed_tiles=%d capped_leaves=%d bbox_ignored=%d "
        "aborted=%s budget_hit=%s seconds=%d",
        kind, tile_stats.requests, len(only_ids), tile_stats.failed_tiles, tile_stats.capped_leaves,
        tile_stats.bbox_ignored, tile_stats.aborted, tile_stats.budget_hit,
        int(time.monotonic() - tile_stats.started_at) if tile_stats.started_at is not None else 0,
    )
    complete = not tile_stats.incomplete and not write_failed
    _YAD2_TILE_STATE[kind].update(ran=True, complete=complete)
    return fetched, errors, complete


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

    # 2026-10-08: the loop above asks each district ONCE and Yad2 caps a response at 200 ads, so most of a busy district was
    # never seen (measured live: a 5x5 grid over Jerusalem-area saw 963 ads vs 200, our DB held 508 of them). The sweep asks
    # for the same map in smaller pieces, free route only, and never replaces the baseline above.
    for kind in _YAD2_TILE_KINDS:
        _YAD2_TILE_ONLY_IDS[kind].clear()
        _YAD2_TILE_STATE[kind].update(ran=False, complete=False)
    _reset_streamed_sweep_state()
    if tile_sweep_enabled():
        swept, sweep_errors, sweep_complete = _run_yad2_tile_sweep(
            "rent", DealType.RENT, normalized_items, seen_external_ids
        )
        fetched += swept
        errors += sweep_errors
        if not sweep_complete:
            # Same rule as a failed region: part of the map may be missing, so "not seen" must not delist anything.
            all_succeeded = False

    # 2026-09-22: task #1/#2 — forsale, confirmed live for all 7 REGION_SLUGS via the search-page +
    # Web Unlocker mechanism (see fetch_forsale_region's own docstring). No map-API fast path here
    # (Bright Data's own KYC wall blocks gw.yad2.co.il/realestate-feed/forsale/map specifically,
    # confirmed live, unrelated to rent's own map API which is unaffected) — always one search-page
    # fetch per region, same shape fetch_all_listings used for rent before REGIONS_ON_MAP_API
    # existed. Shares known_ids with the rent loop above (a Yad2 token is globally unique regardless
    # of deal type, so no cross-deal-type collision risk) — a listing seen in EITHER loop this run
    # counts as seen for delisting purposes.
    # With the for-sale map sweep on, the search-page loop below (about 50 ads per district, paid Web Unlocker, and failing for every
    # district on 2026-10-08 - which also made every Yad2 run "incomplete" and blocked its delisting) is redundant: the sweep sees every
    # for-sale ad, and an incomplete sweep already blocks delisting on its own.
    forsale_regions = [] if sale_tile_sweep_enabled() else list(REGION_SLUGS)
    if forsale_regions:
        logger.info("Scraping %d Yad2 forsale regions this run: %s", len(forsale_regions), ", ".join(forsale_regions))
    for region in forsale_regions:
        region_succeeded = False
        for attempt in range(1, _YAD2_MAX_FETCH_ATTEMPTS + 1):
            try:
                for raw_item in fetch_forsale_region(region):
                    fetched += 1
                    normalized = normalize(raw_item, source=Source.YAD2, deal_type=DealType.SALE)
                    if normalized is not None:
                        normalized_items.append(normalized)
                        seen_external_ids.add(normalized.external_id)
                    else:
                        errors += 1
                region_succeeded = True
                break
            except Yad2MapFetchError as exc:
                if attempt < _YAD2_MAX_FETCH_ATTEMPTS:
                    logger.warning(
                        "Yad2 forsale fetch failed for region=%s (attempt %d/%d) — retrying in "
                        "%.0fs: %s", region, attempt, _YAD2_MAX_FETCH_ATTEMPTS,
                        _REGION_RETRY_DELAY_SECONDS, exc,
                    )
                    time.sleep(_REGION_RETRY_DELAY_SECONDS)
                else:
                    logger.exception(
                        "Failed to fetch Yad2 forsale results for region=%s after %d attempts — "
                        "skipping this region", region, _YAD2_MAX_FETCH_ATTEMPTS,
                    )
        if not region_succeeded:
            errors += 1
            all_succeeded = False
        # Same pacing as the rent loop's own map-API requests above — this also goes through
        # Bright Data Web Unlocker, same target site, same anti-detection reasoning.
        time.sleep(_MAP_API_REGION_PACING_SECONDS)

    # 2026-10-08: the search page above shows ~50 ads per district, so for-sale was badly under-covered (723 active ads held).
    # The for-sale MAP answers on the free route like the rent map does (live probe: one request 200 ads, a 3x3 grid 743), so the
    # same piece-by-piece sweep covers it, with its own budget, seed flag and incomplete-means-no-delisting rule.
    if sale_tile_sweep_enabled():
        swept, sweep_errors, sweep_complete = _run_yad2_tile_sweep(
            "forsale", DealType.SALE, normalized_items, seen_external_ids
        )
        fetched += swept
        errors += sweep_errors
        if not sweep_complete:
            all_succeeded = False

    return normalized_items, seen_external_ids, fetched, errors, all_succeeded


# 2026-10-06: about 270 Komo listings per run have a detail page with no price (or that fails to load). They
# are never stored, so every run saw them as "new" again, refetched all of them, and they ate ~270 of the
# 300 new-detail slots (KOMO_MAX_NEW_DETAIL_FETCHES_PER_RUN) so genuinely new Komo listings crept in ~30
# per run. A failed id is now remembered (an AppFlag, JSON {id: unix time of the failure}) and not retried
# for _KOMO_FAILED_RETRY_AFTER; entries older than _KOMO_FAILED_FORGET_AFTER, or for ids no longer on Komo,
# are dropped so the list cannot grow forever. A failure is retried daily, so a page that only failed
# temporarily is still picked up.
_KOMO_FAILED_IDS_FLAG = "komo_failed_detail_ids"
_KOMO_FAILED_RETRY_AFTER_SECONDS = 24 * 3600
_KOMO_FAILED_FORGET_AFTER_SECONDS = 14 * 24 * 3600


def _load_komo_failed_ids() -> dict[str, float]:
    try:
        with get_session() as session:
            raw = whatsapp_guard.get_flag(session, _KOMO_FAILED_IDS_FLAG)
        data = json.loads(raw) if raw else {}
        return {str(k): float(v) for k, v in data.items()}
    except Exception:
        logger.exception("Could not read the Komo failed-detail list - treating it as empty")
        return {}


def _save_komo_failed_ids(failed: dict[str, float]) -> None:
    try:
        with get_session() as session:
            whatsapp_guard.set_flag(session, _KOMO_FAILED_IDS_FLAG, json.dumps(failed))
    except Exception:
        logger.exception("Could not save the Komo failed-detail list")



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
    made a run with many new Komo listings take a real, avoidable extra chunk of wall-clock time.

    2026-09-22: task #3/#4 — also fetches Komo's real sale coordinate list (iska=2 via
    SALE_SEARCH_PAGE_URL, confirmed live — see fetch_coordinate_ids' own docstring) alongside the
    rent one (iska=1, unchanged). Both share the SAME known_ids/processed_this_run/detail-fetch cap
    — a modaaNum is globally unique regardless of deal type, and the cap is a real ZenRows-credit
    budget on total new detail fetches this run, not a per-category allowance. `sale_ids` tracks
    which of processed_this_run's new ids came from the sale list, so the right DealType is applied
    when normalizing — _parse_details_html's own regexes need no changes (confirmed live against 3
    real sale listings' detail pages). A failed sale fetch (KomoFetchError) is logged/counted but
    does not discard whatever the rent fetch already found."""
    normalized_items = []
    seen_external_ids: set[str] = set()

    known_ids = _fetch_known_external_ids(Source.KOMO)
    processed_this_run: set[str] = set(known_ids)
    max_new_detail_fetches = _komo_max_new_detail_fetches_per_run()
    errors = 0
    all_succeeded = True

    logger.info("Fetching Komo's nationwide coordinate list (one call, confirmed city-independent)")
    try:
        rent_coordinates = fetch_all_coordinate_ids()
    except KomoFetchError:
        logger.exception("Failed to fetch Komo's rent coordinate list — skipping Komo entirely this run")
        return normalized_items, seen_external_ids, 0, 1, False

    logger.info("Fetching Komo's nationwide SALE coordinate list (iska=2, one call)")
    try:
        sale_coordinates = fetch_all_coordinate_ids(
            iska="2", search_page_url=komo_client.SALE_SEARCH_PAGE_URL
        )
    except KomoFetchError:
        logger.exception(
            "Failed to fetch Komo's sale coordinate list — continuing with rent results only"
        )
        sale_coordinates = []
        errors += 1
        all_succeeded = False

    sale_ids: set[str] = set()
    # Real lat/lng per id, straight off the SAME coordinates-list response already being paid
    # for — confirmed live nationwide (both rent/sale, see module docstring) — no separate fetch
    # needed. Only used below for genuinely-new ids (an already-known listing's coordinates don't
    # change and aren't worth a re-normalize just to refresh them).
    coords_by_id: dict[str, tuple[float, float]] = {}
    new_ids_to_fetch: list[str] = []
    for coordinate, is_sale in [(c, False) for c in rent_coordinates] + [
        (c, True) for c in sale_coordinates
    ]:
        modaa_num = coordinate.get("id")
        if not modaa_num:
            continue
        modaa_num = str(modaa_num)
        seen_external_ids.add(modaa_num)
        if is_sale:
            sale_ids.add(modaa_num)
        lat, lng = coordinate.get("lat"), coordinate.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            coords_by_id[modaa_num] = (lat, lng)
        if modaa_num in processed_this_run:
            continue  # already known from a prior run, or a duplicate within this run's own list
        processed_this_run.add(modaa_num)
        new_ids_to_fetch.append(modaa_num)

    now_ts = time.time()
    failed_ids = _load_komo_failed_ids()
    recently_failed = {
        modaa for modaa, ts in failed_ids.items() if now_ts - ts < _KOMO_FAILED_RETRY_AFTER_SECONDS
    }
    skipped_recently_failed = sum(1 for modaa in new_ids_to_fetch if modaa in recently_failed)
    new_ids_to_fetch = [modaa for modaa in new_ids_to_fetch if modaa not in recently_failed]
    if skipped_recently_failed:
        logger.info(
            "Komo: skipping %d id(s) whose detail page failed within the last %d h (retried daily)",
            skipped_recently_failed, _KOMO_FAILED_RETRY_AFTER_SECONDS // 3600,
        )

    ids_to_fetch = new_ids_to_fetch[:max_new_detail_fetches]
    if len(new_ids_to_fetch) > max_new_detail_fetches:
        logger.warning(
            "Komo hit its per-run new-detail-fetch safety cap (%s=%d) — remaining new "
            "listings this run (across rent and sale) are skipped and will be picked up in a "
            "later run instead of spending unbounded ZenRows credits in one shot.",
            _KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR, max_new_detail_fetches,
        )

    _KOMO_BACKLOG_IDS.clear()
    _KOMO_BACKLOG_IDS.update(_komo_backlog_ids(ids_to_fetch, known_ids))
    if _KOMO_BACKLOG_IDS:
        logger.info("Komo: %d of %d ad(s) fetched this run are older backlog (stored quietly)", len(_KOMO_BACKLOG_IDS), len(ids_to_fetch))

    fetched = len(ids_to_fetch)
    details = asyncio.run(
        _fetch_concurrently(ids_to_fetch, fetch_komo_listing_detail, _KOMO_DETAIL_FETCH_CONCURRENCY)
    )
    newly_failed: set[str] = set()
    for modaa_num, detail in zip(ids_to_fetch, details):
        if detail is None:
            errors += 1
            newly_failed.add(modaa_num)
            continue
        deal_type = DealType.SALE if modaa_num in sale_ids else DealType.RENT
        coords = coords_by_id.get(modaa_num)
        if coords is not None:
            detail["latitude"], detail["longitude"] = coords
        normalized = normalize(detail, source=Source.KOMO, deal_type=deal_type)
        if normalized is not None:
            normalized_items.append(normalized)
        else:
            errors += 1
            newly_failed.add(modaa_num)

    # Remember this run's failures; keep earlier ones that are still recent and still on Komo.
    if newly_failed or failed_ids:
        updated = {
            modaa: ts
            for modaa, ts in failed_ids.items()
            if modaa in seen_external_ids and now_ts - ts < _KOMO_FAILED_FORGET_AFTER_SECONDS
        }
        updated.update({modaa: now_ts for modaa in newly_failed})
        if updated != failed_ids:
            _save_komo_failed_ids(updated)

    return normalized_items, seen_external_ids, fetched, errors, all_succeeded


# --- Homeless pagination (2026-10-08) -------------------------------------------------------------------------------------
# Homeless lists ~53 cards per page and paginates with /rent/<n> and /sale/<n> (rent ends near page 75, sale is longer); we only ever
# read page 1, so ~90 active Homeless ads were held. Every page costs one ZenRows credit and the free plan has 5,000 a month
# (about 175 a day left in the cycle), so a full crawl every run is out of reach. Instead each run reads
#   * the first pages of each category (where every new ad appears), and
#   * a few "rolling" pages from a stored cursor that walks the whole list over about three days, then starts again.
# An ad found only by a rolling page is old by definition (the first pages are re-read every hour), so it is stored quietly and
# never announced. Because a run sees only part of the list, the usual "not seen = gone" delisting is off for Homeless; instead an
# ad not seen for _HOMELESS_STALE_DAYS is delisted, but only for a deal type whose cursor completed a lap recently.
_HOMELESS_PAGINATION_ENV_VAR = "HOMELESS_PAGINATION"
_HOMELESS_FRESH_PAGES = 2
_HOMELESS_ROLLING_PAGES_PER_RUN = 2
_HOMELESS_MAX_PAGE = 200
_HOMELESS_END_NEW_CARDS = 3  # a rolling page adding this few unseen cards (or fewer) is past the end of the list
_HOMELESS_CURSOR_FLAG = "homeless_rolling_cursor"
# The scraper used to read only the ~8 promoted cards of a Homeless page; the regular table rows (~42 more per page) are read from
# 2026-10-08. The first run that reads them finds a pile of ads that were always there, so it stores them quietly and sets this flag.
_HOMELESS_ROWS_SEEDED_FLAG = "homeless_table_rows_seeded"
_HOMELESS_STALE_DAYS = 6
_HOMELESS_LAP_HEALTHY_DAYS = 5
_HOMELESS_PAGE_PAUSE_SECONDS = 1.5
_HOMELESS_ROLLING_ONLY_IDS: set[str] = set()
_HOMELESS_CURSOR_STATE: dict[str, dict] = {}
# Sources whose run sees only part of the list on purpose: run_once skips the "not seen = gone" delisting for them.
_PARTIAL_VIEW_SOURCES: set[str] = set()


def _homeless_pagination_enabled() -> bool:
    return os.environ.get(_HOMELESS_PAGINATION_ENV_VAR, "").strip().lower() == "true"


def _homeless_read_category(
    base_url: str, cursor: int, *, fetch_page=None, sleep=time.sleep
) -> tuple[list[dict], set[str], int, int, bool]:
    """Reads the first pages plus this run's rolling pages of one Homeless category.
    Returns (cards, ids found only by rolling pages, next cursor, failed page count, completed a lap)."""
    fetch_page = fetch_page or homeless_client.fetch_search_page
    cards: dict[str, dict] = {}
    errors = 0
    for page in range(1, _HOMELESS_FRESH_PAGES + 1):
        if page > 1:
            sleep(_HOMELESS_PAGE_PAUSE_SECONDS)
        try:
            for card in fetch_page(base_url, page):
                cards.setdefault(card["id"], card)
        except HomelessFetchError:
            logger.exception("Homeless page %d failed (%s)", page, base_url)
            errors += 1
    rolling_only: set[str] = set()
    next_cursor = max(cursor, _HOMELESS_FRESH_PAGES + 1)
    page = next_cursor
    wrapped = False
    for _ in range(_HOMELESS_ROLLING_PAGES_PER_RUN):
        sleep(_HOMELESS_PAGE_PAUSE_SECONDS)
        try:
            page_cards = fetch_page(base_url, page)
        except HomelessFetchError:
            logger.exception("Homeless rolling page %d failed (%s)", page, base_url)
            errors += 1
            page += 1
            next_cursor = page
            continue
        unseen = [card for card in page_cards if card["id"] not in cards]
        if len(unseen) <= _HOMELESS_END_NEW_CARDS or page > _HOMELESS_MAX_PAGE:
            next_cursor = _HOMELESS_FRESH_PAGES + 1
            wrapped = True
            break
        for card in unseen:
            cards[card["id"]] = card
            rolling_only.add(card["id"])
        page += 1
        next_cursor = page
    return list(cards.values()), rolling_only, next_cursor, errors, wrapped


def _homeless_rows_seeded() -> bool:
    try:
        with get_session() as session:
            return bool(whatsapp_guard.get_flag(session, _HOMELESS_ROWS_SEEDED_FLAG))
    except Exception:
        logger.exception("Could not read the Homeless table-rows seed flag - treating the run as already seeded")
        return True  # never risk a flood of alerts because of a read error


def _mark_homeless_rows_seeded() -> None:
    try:
        with get_session() as session:
            whatsapp_guard.set_flag(session, _HOMELESS_ROWS_SEEDED_FLAG, dt.datetime.now(dt.timezone.utc).isoformat())
    except Exception:
        logger.exception("Could not save the Homeless table-rows seed flag")


def _load_homeless_cursor() -> dict[str, dict]:
    try:
        with get_session() as session:
            raw = whatsapp_guard.get_flag(session, _HOMELESS_CURSOR_FLAG)
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("Could not read the Homeless rolling cursor - starting the lap over")
        return {}


def _save_homeless_cursor(state: dict[str, dict]) -> None:
    try:
        with get_session() as session:
            whatsapp_guard.set_flag(session, _HOMELESS_CURSOR_FLAG, json.dumps(state))
    except Exception:
        logger.exception("Could not save the Homeless rolling cursor")


def _homeless_healthy_deal_types(state: dict[str, dict], now: dt.datetime | None = None) -> set[str]:
    """Deal types whose rolling cursor completed a lap recently enough to trust 'not seen for a few days' as 'gone'."""
    now = now or dt.datetime.now(dt.timezone.utc)
    healthy: set[str] = set()
    for deal_type, entry in state.items():
        try:
            wrapped_at = dt.datetime.fromisoformat(entry["wrapped_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if now - wrapped_at <= dt.timedelta(days=_HOMELESS_LAP_HEALTHY_DAYS):
            healthy.add(deal_type)
    return healthy


def _delist_stale_homeless(session, seen_external_ids: set[str], healthy_deal_types: set[str]) -> int:
    """Delists Homeless ads not seen for _HOMELESS_STALE_DAYS (only for deal types with a recent completed lap) and un-delists any
    that reappeared. See the comment above for why this replaces the usual per-run delisting for Homeless."""
    table = Listing.__table__
    delisted = 0
    if healthy_deal_types:
        delisted = len(
            session.execute(
                table.update()
                .where(
                    table.c.source == Source.HOMELESS,
                    table.c.is_delisted.is_(False),
                    table.c.deal_type.in_(healthy_deal_types),
                    table.c.scraped_at < func.now() - func.make_interval(0, 0, 0, _HOMELESS_STALE_DAYS),
                )
                .values(is_delisted=True, delisted_at=func.now())
                .returning(table.c.id)
            ).fetchall()
        )
    if seen_external_ids:
        session.execute(
            table.update()
            .where(
                table.c.source == Source.HOMELESS,
                table.c.is_delisted.is_(True),
                table.c.external_id.in_(seen_external_ids),
            )
            .values(is_delisted=False, delisted_at=None)
        )
    session.commit()
    return delisted


# 2026-10-08: Komo catch-up. Raising the per-run detail cap (300 -> 800) made the old sale backlog arrive as hundreds of "new" ads
# per run (728 in one run, 365 notifications). A Komo ad id grows with time (about 1,200 a day; measured: ads first seen in the last
# 24 hours sit within ~250 of the highest id we hold, the backlog up to ~29,000 below it), so an ad whose id is more than
# _KOMO_BACKLOG_ID_GAP below the highest known id is old by definition and is stored quietly, like the other backlogs.
_KOMO_BACKLOG_ID_GAP = 1500
_KOMO_BACKLOG_IDS: set[str] = set()


def _komo_backlog_ids(candidate_ids: list[str], known_ids: set[str]) -> set[str]:
    """The candidates whose numeric id is far below the highest id we already hold (see the comment above). Empty when nothing
    numeric is known yet (the very first run has no reference point)."""
    known_numeric = [int(i) for i in known_ids if i.isdigit()]
    if not known_numeric:
        return set()
    newest_known = max(known_numeric)
    return {i for i in candidate_ids if i.isdigit() and newest_known - int(i) > _KOMO_BACKLOG_ID_GAP}


def _quiet_backlog(session, new_ids: list[int]) -> list[int]:
    """Stores the new ads that are old by definition without announcing them (first_seen_at pushed outside the retry window):
    Homeless ads only a rolling page found, and Komo ads far below the newest known id. Returns the ids still to be announced."""
    if not new_ids:
        return new_ids
    quiet_by_source = ((Source.HOMELESS, _HOMELESS_ROLLING_ONLY_IDS), (Source.KOMO, _KOMO_BACKLOG_IDS))
    backlog: set[int] = set()
    for source, quiet_ids in quiet_by_source:
        if not quiet_ids:
            continue
        rows = session.execute(
            select(Listing.id, Listing.external_id).where(Listing.id.in_(new_ids), Listing.source == source)
        ).all()
        found = {row[0] for row in rows if row[1] in quiet_ids}
        if found:
            logger.info("%s backlog: stored %d older ad(s) quietly (no alerts)", source, len(found))
        backlog |= found
    if backlog:
        table = Listing.__table__
        session.execute(
            table.update()
            .where(table.c.id.in_(backlog))
            .values(first_seen_at=func.now() - func.make_interval(0, 0, 0, _SEED_BACKDATE_DAYS))
        )
        session.commit()
    return [listing_id for listing_id in new_ids if listing_id not in backlog]


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
    capped-out listing still gets fully upserted (this only skips the EXTRA description fetch,
    never the listing itself), just with no description this run.

    2026-09-26: corrected — a listing skipped here does NOT get "picked up on a later run" by
    this function itself (a listing already in the DB is never "new" again, so this fetch never
    gets a second shot at it — confirmed live, this exact gap sat Homeless at only 28.6%
    description coverage). It DOES still get a real second chance, just via a different path:
    _backfill_missing_homeless_descriptions (below), which every run queries for ANY active
    Homeless listing with description IS NULL — regardless of when it was first scraped — and
    fetches it via this same fetch_homeless_description, capped by its own
    _homeless_backfill_max_per_run().

    NOT yet confirmed (see homeless_client.py's own module docstring): whether homeless.co.il/rent/
    paginates beyond what one fetch returns. If it does, this function currently only sees
    whatever's on that one page — a real, documented open question, not a silent assumption of
    full coverage.

    2026-09-15: the actual new-listing description fetches now run CONCURRENTLY, bounded by
    _HOMELESS_DESCRIPTION_FETCH_CONCURRENCY (see that constant's own comment — these go through
    ZenRows either way, a managed proxy built for concurrent traffic, so this doesn't change the
    request rate OUR OWN IP presents to homeless.co.il at all) — same _fetch_concurrently helper
    _scrape_komo uses. Previously these ran one at a time, sequentially.

    2026-09-24: task #5/#6 — also fetches Homeless's real sale listings (SALE_SEARCH_PAGE_URL,
    confirmed live — see homeless_client.py's own module docstring for the real site-redesign
    story this rewrite was built against) alongside rent, tagging each with the right DealType.
    Both categories share ONE known_ids set (a Homeless ad id is globally unique regardless of
    deal type) and ONE combined new-description-fetch cap — a real ZenRows-credit budget on total
    new fetches this run, not a per-category allowance. A failed category (HomelessFetchError) is
    logged/counted but doesn't discard whatever the other category already found."""
    errors = 0
    normalized_items = []
    seen_external_ids: set[str] = set()
    all_succeeded = True

    known_ids = _fetch_known_external_ids(Source.HOMELESS)
    max_new_description_fetches = _homeless_max_new_description_fetches_per_run()

    raw_items: list[dict] = []
    _HOMELESS_ROLLING_ONLY_IDS.clear()
    _PARTIAL_VIEW_SOURCES.discard(Source.HOMELESS)
    categories = (
        (homeless_client.SEARCH_PAGE_URL, DealType.RENT),
        (homeless_client.SALE_SEARCH_PAGE_URL, DealType.SALE),
    )
    if _homeless_pagination_enabled():
        _PARTIAL_VIEW_SOURCES.add(Source.HOMELESS)
        cursor_state = _load_homeless_cursor()
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        for url, deal_type in categories:
            entry = cursor_state.get(deal_type) or {}
            logger.info("Fetching Homeless listings (deal_type=%s, rolling page %s)", deal_type, entry.get("page", 3))
            cards, rolling_only, next_cursor, failed_pages, wrapped = _homeless_read_category(
                url, int(entry.get("page", _HOMELESS_FRESH_PAGES + 1))
            )
            for card in cards:
                card["_deal_type"] = deal_type
                raw_items.append(card)
            _HOMELESS_ROLLING_ONLY_IDS.update(rolling_only)
            errors += failed_pages
            cursor_state[deal_type] = {
                "page": next_cursor,
                "wrapped_at": now_iso if wrapped else entry.get("wrapped_at"),
            }
        _save_homeless_cursor(cursor_state)
        if not _homeless_rows_seeded():
            _HOMELESS_ROLLING_ONLY_IDS.update(card["id"] for card in raw_items)  # first run with the table rows: all quiet
            _mark_homeless_rows_seeded()
        _HOMELESS_CURSOR_STATE.clear()
        _HOMELESS_CURSOR_STATE.update(cursor_state)
        logger.info(
            "Homeless rolling crawl: cards=%d rolling_only=%d failed_pages=%d cursor=%s",
            len(raw_items), len(_HOMELESS_ROLLING_ONLY_IDS), errors,
            {key: value.get("page") for key, value in cursor_state.items()},
        )
    else:
        for url, deal_type in categories:
            logger.info("Fetching Homeless listings (deal_type=%s)", deal_type)
            try:
                for raw_item in fetch_homeless_results(url):
                    raw_item["_deal_type"] = deal_type
                    raw_items.append(raw_item)
            except HomelessFetchError:
                # A partial list (whatever was already yielded before the failure) is still processed
                # below, same as before this change — a mid-iteration failure never discarded what had
                # already been fetched, and a failed category doesn't discard the other's results.
                logger.exception(
                    "Failed to fetch Homeless listings (deal_type=%s) — skipping the rest of this "
                    "category", deal_type,
                )
                errors += 1
                all_succeeded = False

    fetched = len(raw_items)
    for raw_item in raw_items:
        seen_external_ids.add(raw_item["id"])

    new_items = [
        item for item in raw_items if item["id"] not in known_ids and item["id"] not in _HOMELESS_ROLLING_ONLY_IDS
    ]
    items_to_fetch = new_items[:max_new_description_fetches]
    if len(new_items) > max_new_description_fetches:
        logger.warning(
            "Homeless hit its per-run new-description-fetch safety cap (%s=%d) — "
            "remaining new listings this run (across rent and sale) keep no description here "
            "instead of spending unbounded ZenRows credits in one shot; "
            "_backfill_missing_homeless_descriptions still covers them on a later run.",
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
        deal_type = raw_item.pop("_deal_type")
        normalized = normalize(raw_item, source=Source.HOMELESS, deal_type=deal_type)
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

# 2026-10-08: Marketplace's feed is local to a map point, and the default point returned only 3 rentals. Asking the same category
# for 13 city centres (radius 40 km) returned 20 distinct rentals in one probe (diagnose-facebook-marketplace-coverage, run on the
# scraper's own egress IP), so with this switch on each run also reads the feed around the points below. Off by default; the
# dedicated account is the sensitive part, so the extra page loads are paced (5-12 s apart), counted, and stop after two failures
# in a row (an expired cookie or a block must not be hammered). New ads still share the one per-run detail-fetch cap.
_FACEBOOK_MARKETPLACE_POINTS_ENV_VAR = "FACEBOOK_MARKETPLACE_POINTS"
_FACEBOOK_POINT_RADIUS_KM = 40
_FACEBOOK_PAGE_PACING_SECONDS_RANGE = (5.0, 12.0)
_FACEBOOK_POINT_MAX_CONSECUTIVE_FAILURES = 2
_FACEBOOK_MARKETPLACE_POINTS: tuple[tuple[str, float, float], ...] = (
    ("tel-aviv", 32.0853, 34.7818),
    ("jerusalem", 31.7683, 35.2137),
    ("haifa", 32.7940, 34.9896),
    ("beer-sheva", 31.2530, 34.7915),
    ("netanya", 32.3215, 34.8532),
    ("rishon", 31.9730, 34.7925),
    ("ashdod", 31.8044, 34.6553),
    ("modiin", 31.8969, 35.0104),
    ("tiberias", 32.7959, 35.5310),
    ("kiryat-shmona", 33.2075, 35.5700),
    ("eilat", 29.5577, 34.9519),
)
_FACEBOOK_SALE_POINT_NAMES = frozenset({"tel-aviv", "jerusalem", "haifa", "beer-sheva", "netanya"})


def _facebook_marketplace_feeds() -> list[tuple[str, str]]:
    """The base rent + for-sale feeds, plus (when FACEBOOK_MARKETPLACE_POINTS=true) the same categories around each city centre."""
    feeds = list(_FACEBOOK_MARKETPLACE_CATEGORIES)
    if os.environ.get(_FACEBOOK_MARKETPLACE_POINTS_ENV_VAR, "").strip().lower() != "true":
        return feeds
    for name, lat, lon in _FACEBOOK_MARKETPLACE_POINTS:
        where = f"?latitude={lat}&longitude={lon}&radius={_FACEBOOK_POINT_RADIUS_KM}&exact=false"
        feeds.append((f"category/propertyrentals{where}", DealType.RENT))
        if name in _FACEBOOK_SALE_POINT_NAMES:
            feeds.append((f"category/propertyforsale{where}", DealType.SALE))
    return feeds


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

    point_failures_in_a_row = 0
    for url_path, deal_type in _facebook_marketplace_feeds():
        is_point_feed = "?" in url_path
        if is_point_feed:
            if point_failures_in_a_row >= _FACEBOOK_POINT_MAX_CONSECUTIVE_FAILURES:
                logger.error("Facebook Marketplace city feeds stopped after %d failures in a row", point_failures_in_a_row)
                break
            time.sleep(random.uniform(*_FACEBOOK_PAGE_PACING_SECONDS_RANGE))
        try:
            raw_items = list(fetch_facebook_results(url_path))
            if is_point_feed:
                point_failures_in_a_row = 0
        except FacebookFetchError:
            logger.exception(
                "Failed to fetch Facebook Marketplace search results for url_path=%r — "
                "skipping this category this run", url_path,
            )
            errors += 1
            all_succeeded = False
            if is_point_feed:
                point_failures_in_a_row += 1
            continue

        for raw_item in raw_items:
            external_id = raw_item["id"]
            if external_id in seen_external_ids:
                continue  # already handled earlier this run (city-centre feeds overlap) - never a second detail fetch
            fetched += 1
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
    shape as _scrape_yad2. A genuine no-op (returns immediately, all_succeeded=True) when both
    _facebook_groups_tracked_ids() and _facebook_groups_sale_tracked_ids() are empty — no group ids
    configured is not an error, just nothing to do yet (see PROJECT_STATE.md, 2026-09-21/22: only
    one real RENT group confirmed as of this writing; a sale-focused group's real id goes in
    FACEBOOK_GROUPS_SALE_TRACKED_IDS instead — see that env var's own comment above for why they're
    separate — as the owner sends one).

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

    rent_group_ids = _facebook_groups_tracked_ids()
    sale_group_ids = _facebook_groups_sale_tracked_ids()
    tracked_group_ids = rent_group_ids | sale_group_ids
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

        # A group not explicitly in sale_group_ids defaults to RENT — preserves today's exact
        # single-rent-group behavior unchanged when FACEBOOK_GROUPS_SALE_TRACKED_IDS is unset.
        deal_type = DealType.SALE if group_id in sale_group_ids else DealType.RENT
        normalized = normalize(detail, source=Source.FACEBOOK_GROUPS, deal_type=deal_type)
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
        if source == Source.YAD2:
            scraped_city_names |= _STREAMED_CITIES
        per_source_delisting_input[source] = (seen_external_ids, scraped_city_names, all_succeeded)

    with get_session() as session:
        new_ids, price_change_pairs = _upsert_listings(session, all_normalized_items)
        new_ids = new_ids + _STREAMED_NEW_IDS
        price_change_pairs = price_change_pairs + _STREAMED_PRICE_PAIRS
        new_ids = _apply_tile_seed_policy(session, new_ids)
        new_ids = _quiet_backlog(session, new_ids)

        # Before anything reads the new listings back out (delisting check doesn't touch them, but
        # the notification step below does) — enriching first means notifications already carry
        # the real description/photos/amenities instead of only the search-card fields. A no-op,
        # fast, if Bright Data isn't configured yet, or for any Komo/Homeless-sourced new_ids (see
        # that function's own docstring — it filters to source == Source.YAD2 internally).
        enriched_count = asyncio.run(_enrich_new_listings_via_bright_data(session, new_ids))
        # Independent of this run's own new_ids — catches up on the accumulated backlog of older
        # Yad2 listings that never got a description at all (see this function's own docstring for
        # the real, live-confirmed 6.2%-coverage gap this closes). Not on the notification-critical
        # path (these listings were already notified, if at all, long before this run), so it runs
        # after enrichment rather than before.
        backfilled_count = asyncio.run(_backfill_missing_yad2_descriptions(session))
        # Same real gap, same catch-up pattern, Homeless's own source — see this function's own
        # docstring for the live-confirmed 28.6%-coverage number this closes.
        homeless_backfilled_count = asyncio.run(_backfill_missing_homeless_descriptions(session))

        delisted_count = 0
        for source, (seen_external_ids, scraped_city_names, all_succeeded) in (
            per_source_delisting_input.items()
        ):
            if source in _PARTIAL_VIEW_SOURCES:
                if source == Source.HOMELESS:
                    delisted_count += _delist_stale_homeless(
                        session, seen_external_ids, _homeless_healthy_deal_types(_HOMELESS_CURSOR_STATE)
                    )
                continue  # this source's run sees only part of its list on purpose - no "not seen = gone" delisting
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
        # 2026-09-25 real bug fix — see _find_unnotified_recent_listings' own docstring for the
        # silent-permanent-notification-loss bug this closes.
        retry_listings = _find_unnotified_recent_listings(
            session, exclude_ids={listing.id for listing in new_listings}
        )
        retried_unnotified_count = len(retry_listings)
        new_listings = new_listings + retry_listings
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
            "new": len(new_ids),
            "retried_unnotified": retried_unnotified_count,
            "bright_data_enriched": enriched_count,
            "bright_data_backfilled": backfilled_count,
            "homeless_backfilled": homeless_backfilled_count,
            "price_changes": len(price_change_events),
            "delisted": delisted_count,
            "errors": errors,
        }
        try:
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
        finally:
            # Runs even when the notification step above raised (the exception still propagates
            # afterwards): a failed notification run must not also swallow the check-in that keeps
            # users' free 24h WhatsApp windows open.
            # Every run, independent of whether anything new was found: keeps users' free 24h WhatsApp
            # windows open (see whatsapp_checkin.py). Fail-soft — never takes the scraper run down.
            # Only on the main scraper (SCRAPE_SOURCES unset): the Facebook CronJob also runs this
            # function, and two jobs must not both ask the same user.
            if not os.environ.get(_SCRAPE_SOURCES_ENV_VAR, "").strip():
                try:
                    # Cost backstop FIRST: if it trips, the check-ins below see the pause flag.
                    summary.update(run_cost_guard(session))
                except Exception:
                    logger.exception("WhatsApp cost guard step failed")
                try:
                    summary.update(run_whatsapp_checkins(session))
                except Exception:
                    logger.exception("WhatsApp check-in step failed")
                try:
                    summary.update(run_renewal_reminders(session))
                except Exception:
                    logger.exception("renewal reminder step failed")

    return summary


if __name__ == "__main__":
    try:
        run_summary = run_once()
    except Exception:
        logger.exception("Scraper run failed")
        sys.exit(1)
    logger.info("Scraper run summary: %s", run_summary)
