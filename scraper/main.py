"""Entrypoint: run one scrape+match+notify cycle, then exit. Triggered periodically by the k8s
CronJob (see charts/todira), or manually via `docker compose run --rm scraper` locally.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import os
import sys

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from dorin_common.db import get_session
from dorin_common.enums import DealType, Source
from dorin_common.models import Listing
from normalize import normalize
from notifier import run_notifications
from yad2_client import CITY_SLUG_TO_HEBREW_NAME, Yad2FetchError, fetch_search_results

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("scraper.main")


def _select_cities_for_run(all_cities: list[str], batch_size: int) -> list[str]:
    """Picks a `batch_size`-sized, deterministically-rotating slice of `all_cities` for this run.

    Every ZenRows request costs real, limited credits (see PROJECT_STATE.md, 2026-08-31 — the
    free tier's entire monthly 5,000-credit budget was burned in ~2 days scraping all 42 cities
    every 10 minutes). Scraping only a rotating slice per run, keyed off the calendar day so it's
    stable across every run within the same day and advances the next day with no stored state
    needed, keeps every city in eventual rotation (nobody's chosen city is structurally
    unreachable) while bounding total monthly requests. `batch_size <= 0` or `>= len(all_cities)`
    disables rotation entirely (every city, every run) — useful for local/manual testing."""
    if batch_size <= 0 or batch_size >= len(all_cities):
        return all_cities
    day_index = datetime.date.today().toordinal()
    start = (day_index * batch_size) % len(all_cities)
    end = start + batch_size
    if end <= len(all_cities):
        return all_cities[start:end]
    return all_cities[start:] + all_cities[: end - len(all_cities)]


def _scrape_cities() -> list[str]:
    raw = os.environ.get("SCRAPE_CITIES", "")
    cities = [c.strip() for c in raw.split(",") if c.strip()]
    if not cities:
        raise RuntimeError(
            "SCRAPE_CITIES environment variable is not set (comma-separated list of cities)"
        )
    batch_size = int(os.environ.get("SCRAPE_CITIES_PER_RUN", "0") or "0")
    return _select_cities_for_run(cities, batch_size)


def _upsert_listings(session, normalized_items) -> tuple[list[int], list[tuple[int, int]]]:
    """For each normalized item: insert if the (source, external_id) pair is new, otherwise
    update the existing row and check whether its price just dropped.

    Returns (new_ids, price_drop_events) where price_drop_events is a list of
    (listing_id, old_price) for existing listings whose price went down this run. This is a
    per-item SELECT-then-INSERT/UPDATE rather than a single bulk `INSERT ... ON CONFLICT DO
    NOTHING` — less efficient at scale, but DO NOTHING can't see what the previous value was,
    and seeing it is exactly what price-drop detection needs (added after the user pointed out
    the reference bot's "📉 ירידת מחיר!" re-notification, which the original DO-NOTHING design
    missed). Fine at this project's scale — a personal deployment, not high-throughput.

    Real photos/amenity tags/broker status are already merged into `item` by `normalize()` itself
    (see its own `_enrich_from_feed_record` call) before this function ever sees it — a free
    bonus from the search page already being fetched, not a separate cost this function has to
    manage. An earlier version fetched a full per-listing detail page here for every genuinely new
    item (~25 ZenRows credits each, real recurring cost) — rejected once that cost was understood;
    see PROJECT_STATE.md, 2026-09-02."""
    table = Listing.__table__
    new_ids: list[int] = []
    price_drop_events: list[tuple[int, int]] = []

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
        if item.price is not None and old_price is not None and item.price < old_price:
            price_drop_events.append((existing_id, old_price))

        session.execute(table.update().where(table.c.id == existing_id).values(**item.model_dump()))

    session.commit()
    return new_ids, price_drop_events


def _mark_delisted(session, seen_external_ids: set[str], scraped_city_names: set[str]) -> int:
    """Mark previously-active listings that weren't seen in this (complete) run as delisted, and
    un-delist any that reappeared. Scoped to `scraped_city_names` (the canonical Hebrew names —
    see cities.canonicalize_city — of the cities actually scraped THIS run), NOT globally across
    every city ever scraped.

    This used to run globally, on the reasoning that `listings.city` might not reliably match the
    city slug used in the search query, so scoping per-city on a possibly-mismatched string risked
    wrongly delisting an entire city's worth of listings. That reasoning predates
    canonicalize_city() (2026-09-02, see cities.py's docstring) — `listings.city` is now
    normalized to exactly the Hebrew name CITY_SLUG_TO_HEBREW_NAME maps the scraped slug to, so
    matching against it here is reliable.

    Running this globally turned out to be a much worse bug than the one it was written to avoid:
    once SCRAPE_CITIES_PER_RUN started rotating through a 1-city subset per run (added later, for
    ZenRows cost control — see _select_cities_for_run), a global pass meant EVERY run delisted
    every listing from every city NOT scraped that specific run, since their external_ids are
    never in that run's (necessarily city-scoped) seen_external_ids. In practice this meant only
    whichever single city was scraped most recently ever had any non-delisted listings at all —
    found live 2026-09-02 via a production query showing literally every non-delisted listing in
    the entire table belonged to the one city just scraped. Still only called when every city
    ATTEMPTED this run succeeded (see run_once) — a partial fetch failure within that scoped set
    must never be mistaken for "everything in these cities disappeared"."""
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
    cities = _scrape_cities()
    logger.info("Scraping %d cities this run: %s", len(cities), ", ".join(cities))
    fetched = 0
    normalized_items = []
    errors = 0
    seen_external_ids: set[str] = set()
    all_cities_succeeded = True

    for city in cities:
        logger.info("Fetching Yad2 listings for city=%s", city)
        try:
            for raw_item in fetch_search_results(city):
                fetched += 1
                normalized = normalize(raw_item, deal_type=DealType.RENT)
                if normalized is not None:
                    normalized_items.append(normalized)
                    seen_external_ids.add(normalized.external_id)
                else:
                    errors += 1
        except Yad2FetchError:
            logger.exception(
                "Failed to fetch Yad2 results for city=%s — skipping this city", city
            )
            errors += 1
            all_cities_succeeded = False

    with get_session() as session:
        new_ids, price_drop_pairs = _upsert_listings(session, normalized_items)

        delisted_count = 0
        if all_cities_succeeded and seen_external_ids:
            scraped_city_names = {CITY_SLUG_TO_HEBREW_NAME[slug] for slug in cities}
            delisted_count = _mark_delisted(session, seen_external_ids, scraped_city_names)
        elif not all_cities_succeeded:
            logger.warning(
                "Skipping delisting check this run — at least one city failed to fetch, so the "
                "seen-listings set is incomplete and can't be trusted for delisting."
            )

        new_listings = (
            list(session.scalars(select(Listing).where(Listing.id.in_(new_ids))))
            if new_ids
            else []
        )
        price_drop_ids = [listing_id for listing_id, _old_price in price_drop_pairs]
        listings_by_id = {
            listing.id: listing
            for listing in (
                session.scalars(select(Listing).where(Listing.id.in_(price_drop_ids)))
                if price_drop_ids
                else []
            )
        }
        price_drop_events = [
            (listings_by_id[listing_id], old_price)
            for listing_id, old_price in price_drop_pairs
            if listing_id in listings_by_id
        ]

        summary = {
            "fetched": fetched,
            "new": len(new_listings),
            "price_drops": len(price_drop_events),
            "delisted": delisted_count,
            "errors": errors,
        }
        if new_listings or price_drop_events:
            summary.update(
                asyncio.run(run_notifications(session, new_listings, price_drop_events))
            )
        else:
            summary.update(
                {"matched": 0, "notifications_sent": 0, "price_drop_notifications_sent": 0}
            )

    return summary


if __name__ == "__main__":
    try:
        run_summary = run_once()
    except Exception:
        logger.exception("Scraper run failed")
        sys.exit(1)
    logger.info("Scraper run summary: %s", run_summary)
