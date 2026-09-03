"""Entrypoint: run one scrape+match+notify cycle, then exit. Triggered periodically by the k8s
CronJob (see charts/todira), or manually via `docker compose run --rm scraper` locally.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from dorin_common.db import get_session
from dorin_common.enums import DealType, Source
from dorin_common.models import Listing
from normalize import normalize
from notifier import run_notifications
from yad2_client import REGION_SLUGS, Yad2FetchError, fetch_all_listings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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


def run_once() -> dict[str, int]:
    logger.info("Scraping %d Yad2 regions this run: %s", len(REGION_SLUGS), ", ".join(REGION_SLUGS))
    fetched = 0
    normalized_items = []
    errors = 0
    seen_external_ids: set[str] = set()
    all_regions_succeeded = True

    for region in REGION_SLUGS:
        logger.info("Fetching Yad2 listings for region=%s", region)
        try:
            for raw_item in fetch_all_listings(regions=(region,)):
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
