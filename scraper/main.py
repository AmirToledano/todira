"""Entrypoint: run one scrape+match+notify cycle, then exit. Triggered periodically by the k8s
CronJob (see charts/todira), or manually via `docker compose run --rm scraper` locally.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from dorin_common import bright_data_client
from dorin_common.db import get_session
from dorin_common.enums import DealType, Source
from dorin_common.models import Listing
from normalize import _compute_detail_updates, normalize
from notifier import run_notifications
from yad2_client import REGION_SLUGS, Yad2FetchError, fetch_region_pages

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
    see PROJECT_STATE.md, 2026-09-02."""
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
            row = session.execute(
                pg_insert(table).values(**item.model_dump()).returning(table.c.id)
            ).first()
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
        select(table.c.id, table.c.url).where(table.c.id.in_(new_ids))
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


def _mark_delisted(session, seen_external_ids: set[str], scraped_city_names: set[str]) -> int:
    """Mark previously-active listings that weren't seen in this (complete) run as delisted, and
    un-delist any that reappeared. Scoped to `scraped_city_names` — the canonical Hebrew names
    (see cities.canonicalize_city) of the cities actually REPRESENTED among this run's fetched
    listings, NOT globally across every city this project tracks.

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
    just scraped. Still only called when every region ATTEMPTED this run succeeded (see
    run_once) — a partial fetch failure within that observed set must never be mistaken for
    "everything in these cities disappeared"."""
    table = Listing.__table__
    newly_delisted = session.execute(
        table.update()
        .where(
            table.c.source == Source.YAD2,
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
            table.c.source == Source.YAD2,
            table.c.is_delisted.is_(True),
            table.c.city.in_(scraped_city_names),
            table.c.external_id.in_(seen_external_ids),
        )
        .values(is_delisted=False, delisted_at=None)
    )
    session.commit()
    return len(newly_delisted)


def _fetch_known_yad2_external_ids() -> set[str]:
    """Every Yad2 external_id this project already has, regardless of region/city — read once at
    the start of a run and handed to fetch_region_pages for every region (see that function's own
    docstring for why: it isn't scoped per-region, a listing's region isn't tracked separately).

    2026-09-12: added alongside the switch to fetch_region_pages (see that function's module
    comment in yad2_client.py) — a short-lived read-only session, separate from the write session
    the rest of run_once() opens later, since this needs to happen BEFORE the (potentially long,
    all-network) fetch loop rather than interleaved with it."""
    table = Listing.__table__
    with get_session() as session:
        return set(
            session.scalars(
                select(table.c.external_id).where(table.c.source == Source.YAD2)
            )
        )


def run_once() -> dict[str, int]:
    logger.info("Scraping %d Yad2 regions this run: %s", len(REGION_SLUGS), ", ".join(REGION_SLUGS))
    fetched = 0
    normalized_items = []
    errors = 0
    seen_external_ids: set[str] = set()
    all_regions_succeeded = True

    # 2026-09-12: fetch_region_pages (not fetch_all_listings) — keeps paging a region's feed past
    # page 1 until it's caught up to everything already known, instead of assuming one page always
    # holds every listing posted since the last run. See that function's own module comment in
    # yad2_client.py for the full reasoning/cost tradeoffs.
    known_ids = _fetch_known_yad2_external_ids()

    for region in REGION_SLUGS:
        logger.info("Fetching Yad2 listings for region=%s", region)
        try:
            for raw_item in fetch_region_pages(region, known_ids):
                fetched += 1
                normalized = normalize(raw_item, deal_type=DealType.RENT)
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
            all_regions_succeeded = False

    with get_session() as session:
        new_ids, price_change_pairs = _upsert_listings(session, normalized_items)

        # Before anything reads the new listings back out (delisting check doesn't touch them, but
        # the notification step below does) — enriching first means notifications already carry
        # the real description/photos/amenities instead of only the search-card fields. A no-op,
        # fast, if Bright Data isn't configured yet (see that function's own docstring).
        enriched_count = asyncio.run(_enrich_new_listings_via_bright_data(session, new_ids))

        delisted_count = 0
        if all_regions_succeeded and seen_external_ids:
            scraped_city_names = {item.city for item in normalized_items if item.city}
            delisted_count = _mark_delisted(session, seen_external_ids, scraped_city_names)
        elif not all_regions_succeeded:
            logger.warning(
                "Skipping delisting check this run — at least one region failed to fetch, so the "
                "seen-listings set is incomplete and can't be trusted for delisting."
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
        if new_listings or price_change_events:
            summary.update(
                asyncio.run(run_notifications(session, new_listings, price_change_events))
            )
        else:
            summary.update(
                {"matched": 0, "notifications_sent": 0, "price_change_notifications_sent": 0}
            )

    return summary


if __name__ == "__main__":
    try:
        run_summary = run_once()
    except Exception:
        logger.exception("Scraper run failed")
        sys.exit(1)
    logger.info("Scraper run summary: %s", run_summary)
