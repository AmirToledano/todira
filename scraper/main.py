"""Entrypoint: run one scrape+match+notify cycle, then exit. Triggered periodically by the k8s
CronJob (see charts/todira), or manually via `docker compose run --rm scraper` locally.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from dedup import find_duplicate_listing
from dorin_common import bright_data_client
from dorin_common.db import get_session
from dorin_common.enums import DealType, Source
from dorin_common.models import Listing
from homeless_client import HomelessFetchError
from homeless_client import fetch_search_results as fetch_homeless_results
from komo_client import KomoFetchError, fetch_coordinate_ids
from komo_client import fetch_listing_detail as fetch_komo_listing_detail
from normalize import _compute_detail_updates, normalize
from notifier import run_notifications
from yad2_client import CITY_SLUG_TO_HEBREW_NAME, REGION_SLUGS, Yad2FetchError, fetch_region_pages

# 2026-09-12: how many fetch_listing_detail_via_bright_data calls run concurrently when enriching
# a batch of newly-discovered listings. Each call is a real blocking trigger->poll->snapshot round
# trip (up to _POLL_TIMEOUT_SECONDS ~45s in the worst case, see bright_data_client.py) — running
# them one at a time would make a scrape run with many new listings unacceptably slow; running ALL
# of them at once risks hammering Bright Data's API with an unbounded burst. 5 is a starting guess
# at "meaningfully parallel but not abusive", not a documented Bright Data rate limit — revisit if
# real usage shows it's too low (slow runs) or too high (errors/throttling).
_BRIGHT_DATA_ENRICH_CONCURRENCY = 5

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
    full — this ONLY skips the final run_notifications call) so the catch-up itself is never
    silently incomplete; just re-enable notifications (unset this) once satisfied the DB is caught
    up to real current state."""
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


async def _enrich_new_listings_via_bright_data(session, new_ids: list[int]) -> int:
    """For every listing genuinely new to the DB this run (never for one already known — an
    already-known listing already got this exactly once, on the run it first appeared, and the
    result is cached on Listing.description/etc forever), fetches the full listing-detail record
    from Bright Data's Scraper Studio collector and applies normalize._compute_detail_updates'
    fields (description, property type, amenities, floor_total, move-in date, real photos, broker
    status) straight onto that row.

    A no-op (returns 0 immediately, no network calls) when Bright Data isn't configured
    (BRIGHT_DATA_API_KEY/BRIGHT_DATA_COLLECTOR_ID unset) — see bright_data_client.is_configured() —
    so this is always safe to call regardless of whether the feature is actually turned on yet.

    2026-09-13: scoped to source == Source.YAD2 only (now that `new_ids` can include Komo/Homeless
    rows too — see run_once) — the Bright Data collector this calls is tied to one Scraper Studio
    collector built specifically to parse a YAD2 listing detail page's DOM (see
    bright_data_client.py's own module docstring); pointing it at a komo.co.il/homeless.co.il URL
    would get nonsense or a hard failure, not real enrichment. Komo/Homeless don't need this
    anyway — their own scrapers already get everything they support in one fetch.

    Runs the actual per-listing fetches concurrently (bounded by _BRIGHT_DATA_ENRICH_CONCURRENCY)
    via asyncio.to_thread, since fetch_listing_detail_via_bright_data is blocking/synchronous (real
    network calls + a polling wait, same contract as fetch_listing_description elsewhere in this
    codebase) — see that function's own docstring. Deliberately best-effort per listing: one whose
    fetch fails, times out, or returns nothing usable simply keeps its already-normalized
    (search-card-only) fields, exactly as every listing always could before this feature existed —
    never blocks or fails the whole run over one bad fetch.

    Returns how many listings were actually enriched (Bright Data returned usable data for)."""
    if not new_ids or not bright_data_client.is_configured():
        return 0

    table = Listing.__table__
    # Plain (id, url) rows via Core, NOT ORM `Listing` objects — this session's factory is
    # expire_on_commit=False (see dorin_common/db.py), so an ORM object loaded here would sit in
    # the identity map with its PRE-enrichment values and get handed back as-is to run_once()'s own
    # later `select(Listing)` for the same ids, silently undoing this whole function's work. Same
    # reason _upsert_listings/_mark_delisted already operate at the Core `table` level instead of
    # through the ORM.
    id_url_pairs = session.execute(
        select(table.c.id, table.c.url).where(
            table.c.id.in_(new_ids), table.c.source == Source.YAD2
        )
    ).all()
    semaphore = asyncio.Semaphore(_BRIGHT_DATA_ENRICH_CONCURRENCY)

    async def _fetch_one(listing_id: int, url: str) -> tuple[int, dict] | None:
        async with semaphore:
            detail = await asyncio.to_thread(
                bright_data_client.fetch_listing_detail_via_bright_data, url
            )
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
        logger.info("Fetching Yad2 listings for region=%s", region)
        try:
            for raw_item in fetch_region_pages(region, known_ids, **fetch_kwargs):
                fetched += 1
                normalized = normalize(raw_item, source=Source.YAD2, deal_type=DealType.RENT)
                if normalized is not None:
                    normalized_items.append(normalized)
                    seen_external_ids.add(normalized.external_id)
                else:
                    errors += 1
        except Yad2FetchError:
            logger.exception(
                "Failed to fetch Yad2 results for region=%s — skipping this region", region
            )
            errors += 1
            all_succeeded = False

    return normalized_items, seen_external_ids, fetched, errors, all_succeeded


def _scrape_komo() -> tuple[list, set[str], int, int, bool]:
    """Returns the same (normalized_items, seen_external_ids, fetched, errors, all_succeeded)
    shape as _scrape_yad2 — see that function and run_once() for how it's used.

    Loops over EVERY city in CITY_SLUG_TO_HEBREW_NAME (cheap: 2 credits discovery per city,
    confirmed live — see komo_client.py's own module docstring), not just a curated subset —
    komo_client.fetch_coordinate_ids' own docstring flags a REAL, still-unconfirmed possibility
    that Komo's coordinates endpoint returns nationwide results regardless of which city was
    queried (one live sample spanned both Jerusalem- and Tel-Aviv-area coordinates for a
    Jerusalem-only query). This function doesn't need to resolve that uncertainty to be correct
    either way: `processed_this_run` (below) guards against re-fetching (and re-paying for) the
    SAME listing's detail page more than once even if every city's coordinate list turns out to
    be identical/overlapping — the only cost of looping over all 42 cities regardless is the cheap
    2-credit discovery step repeated 42 times (~84 credits/run), not repeated detail fetches.

    Unlike Yad2, a Komo listing's price/rooms/floor/etc. are NEVER refreshed for an
    already-known external_id (the coordinates list carries no price at all — see
    fetch_listing_detail's own module-docstring cost note) — only genuinely new ids get a detail
    fetch. This means an existing Komo listing's price change is NOT currently detected by this
    scraper (a real, documented gap — re-fetching every known listing's detail page each run would
    cost 1 credit per already-known listing per run, rejected as wasteful without a real reason to
    believe Komo prices change often enough to justify it; revisit if that assumption turns out
    wrong). `seen_external_ids` still includes already-known ids (from the coordinates list, not a
    detail fetch) so delisting stays correct regardless of this gap.

    2026-09-13: also enforces _komo_max_new_detail_fetches_per_run() — a real, temporary credit-
    budget safety cap (see that function's own comment) on how many NEW detail fetches (the only
    part of this function with an actual per-listing ZenRows cost) happen in ONE run. Only the paid
    detail fetch is skipped once the cap is hit for the rest of this run — coordinate discovery
    keeps running for every remaining city regardless (cheap, and still needed so
    seen_external_ids stays complete for delisting), and a capped-out id is simply picked up by a
    LATER run instead (processed_this_run doesn't mark it as done, so it's retried next time)."""
    fetched = 0
    errors = 0
    normalized_items = []
    seen_external_ids: set[str] = set()
    all_succeeded = True

    known_ids = _fetch_known_external_ids(Source.KOMO)
    processed_this_run: set[str] = set(known_ids)
    max_new_detail_fetches = _komo_max_new_detail_fetches_per_run()
    new_detail_fetches_this_run = 0
    cap_logged = False

    logger.info("Scraping %d Komo cities this run", len(CITY_SLUG_TO_HEBREW_NAME))
    for city in CITY_SLUG_TO_HEBREW_NAME:
        logger.info("Fetching Komo coordinates for city=%s", city)
        try:
            coordinates = fetch_coordinate_ids(city)
        except KomoFetchError:
            logger.exception(
                "Failed to fetch Komo coordinates for city=%s — skipping this city", city
            )
            errors += 1
            all_succeeded = False
            continue

        for coordinate in coordinates:
            modaa_num = coordinate.get("id")
            if not modaa_num:
                continue
            modaa_num = str(modaa_num)
            seen_external_ids.add(modaa_num)
            if modaa_num in processed_this_run:
                continue  # already known from a prior run, or already handled earlier this run
            processed_this_run.add(modaa_num)

            if new_detail_fetches_this_run >= max_new_detail_fetches:
                if not cap_logged:
                    logger.warning(
                        "Komo hit its per-run new-detail-fetch safety cap (%s=%d) — remaining new "
                        "listings this run are skipped and will be picked up in a later run "
                        "instead of spending unbounded ZenRows credits in one shot.",
                        _KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR, max_new_detail_fetches,
                    )
                    cap_logged = True
                continue

            new_detail_fetches_this_run += 1
            fetched += 1
            detail = fetch_komo_listing_detail(modaa_num)
            if detail is None:
                errors += 1
                continue
            normalized = normalize(detail, source=Source.KOMO, deal_type=DealType.RENT)
            if normalized is not None:
                normalized_items.append(normalized)
            else:
                errors += 1

    return normalized_items, seen_external_ids, fetched, errors, all_succeeded


def _scrape_homeless() -> tuple[list, set[str], int, int, bool]:
    """Returns the same (normalized_items, seen_external_ids, fetched, errors, all_succeeded)
    shape as _scrape_yad2. Unlike Yad2/Komo, Homeless doesn't need a `known_ids` set at all — its
    one plain fetch already returns full data (price/rooms/floor/street/city, all confirmed in the
    same request — see homeless_client.py's own module docstring) for every listing currently on
    the page, so an already-known listing's price gets refreshed for free every run, same as Yad2.

    NOT yet confirmed (see homeless_client.py's own module docstring): whether homeless.co.il/rent/
    paginates beyond what one fetch returns. If it does, this function currently only sees
    whatever's on that one page — a real, documented open question, not a silent assumption of
    full coverage."""
    fetched = 0
    errors = 0
    normalized_items = []
    seen_external_ids: set[str] = set()
    all_succeeded = True

    logger.info("Fetching Homeless listings")
    try:
        for raw_item in fetch_homeless_results():
            fetched += 1
            seen_external_ids.add(raw_item["id"])
            normalized = normalize(raw_item, source=Source.HOMELESS, deal_type=DealType.RENT)
            if normalized is not None:
                normalized_items.append(normalized)
            else:
                errors += 1
    except HomelessFetchError:
        logger.exception("Failed to fetch Homeless listings — skipping this source this run")
        errors += 1
        all_succeeded = False

    return normalized_items, seen_external_ids, fetched, errors, all_succeeded


# 2026-09-13: one entry per source this project scrapes — each a (source, scrape_fn) pair, where
# scrape_fn takes no arguments and returns _scrape_yad2's own (normalized_items, seen_external_ids,
# fetched, errors, all_succeeded) shape. run_once() below loops over this list generically instead
# of three copy-pasted blocks, so adding a fourth source later means one line here, not editing
# run_once() itself. Order doesn't matter (each source's upsert/delisting is independent; only
# notifications run once at the end, over ALL sources' new listings/price changes combined).
_SOURCE_SCRAPERS: tuple[tuple[str, Callable[[], tuple]], ...] = (
    (Source.YAD2, _scrape_yad2),
    (Source.KOMO, _scrape_komo),
    (Source.HOMELESS, _scrape_homeless),
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

    for source, scrape_fn in _SOURCE_SCRAPERS:
        logger.info("Scraping source=%s", source)
        normalized_items, seen_external_ids, source_fetched, source_errors, all_succeeded = (
            scrape_fn()
        )
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
            logger.warning(
                "%s is set — skipping notifications for %d new listing(s) and %d price change(s) "
                "this run (already upserted/delisted normally; only the notify step is skipped).",
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
