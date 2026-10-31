"""A page per city: what renting there costs right now, how fast flats go, and the newest ones (2026-10-31, owner: "do
everything that can sell Todira, without paid ads").

People search Google for "דירות להשכרה בחיפה" and "כמה עולה דירה בחיפה". These pages answer with our own numbers, kept
fresh by the scraper, and end with the way into the bot. Every number comes from listings we collected in the last 30
days; nothing is estimated. A city with too few listings gets no page (404), so a thin page never goes up.
"""
from __future__ import annotations

import datetime as dt
import threading
import time

from sqlalchemy import case, func, or_, select

from todira_common import share
from todira_common.models import Listing
from todira_common.non_home import not_non_home_sql

WINDOW = dt.timedelta(days=30)
MIN_LISTINGS = 30
MIN_PER_ROOMS = 5
NEWEST = 8
TTL_SECONDS = 3600
INDEX_CITIES = 40

_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, build):
    with _lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < TTL_SECONDS:
            return hit[1]
    value = build()
    with _lock:
        _cache[key] = (time.monotonic(), value)
    return value


def _rentals(now: dt.datetime, *, seen_since: dt.timedelta | None = WINDOW):
    conditions = [
        Listing.deal_type == "rent",
        Listing.duplicate_of_id.is_(None),
        Listing.price.between(1000, 40000),
        or_(Listing.property_type.is_(None), Listing.property_type != "shared_room"),
        not_non_home_sql(Listing),
    ]
    if seen_since is not None:
        conditions.append(Listing.first_seen_at >= now - seen_since)
    return conditions


def city_index(session) -> list[dict]:
    """The cities with enough rentals for a page, most listings first: name, listings in 30 days, 3-room median."""
    def build():
        now = dt.datetime.now(dt.timezone.utc)
        three = func.percentile_cont(0.5).within_group(Listing.price).filter(Listing.rooms.between(3, 3.5))
        rows = session.execute(
            select(Listing.city, func.count(), three)
            .where(*_rentals(now), Listing.city.is_not(None))
            .group_by(Listing.city)
            .having(func.count() >= MIN_LISTINGS)
            .order_by(func.count().desc())
            .limit(INDEX_CITIES)
        ).all()
        return [
            {"city": city, "count": int(count), "median3": int(round(float(median), -1)) if median else None}
            for city, count, median in rows
        ]

    return _cached("index", build)


def city_page(session, city: str) -> dict | None:
    """Everything the city page shows, or None when the city has too few rentals for a page."""
    def build():
        now = dt.datetime.now(dt.timezone.utc)
        where = [*_rentals(now), Listing.city == city]
        total = session.scalar(select(func.count()).select_from(Listing).where(*where)) or 0
        if total < MIN_LISTINGS:
            return None
        bucket = case((Listing.rooms >= 5, 5), else_=func.floor(Listing.rooms))
        by_rooms = []
        for rooms, median, count in session.execute(
            select(bucket, func.percentile_cont(0.5).within_group(Listing.price), func.count())
            .where(*where, Listing.rooms.between(1, 12))
            .group_by(bucket)
            .order_by(bucket)
        ):
            if rooms is not None and count >= MIN_PER_ROOMS:
                by_rooms.append({"rooms": int(rooms), "median": int(round(float(median), -1)), "count": int(count)})
        week = session.scalar(
            select(func.count()).select_from(Listing).where(*where, Listing.first_seen_at >= now - dt.timedelta(days=7))
        ) or 0
        # Half the ads were down within this many days. Over ads first seen 14 to 30 days ago, so every one had at least
        # 14 days; one still up counts as up until now. (Older ads are deleted once down, so they can't be used.) Shown
        # only when it is under 14 days, where the answer can't be cut short by the window.
        cohort = [
            *_rentals(now, seen_since=None), Listing.city == city,
            Listing.first_seen_at.between(now - WINDOW, now - dt.timedelta(days=14)),
        ]
        up_days = func.extract("epoch", func.coalesce(Listing.delisted_at, func.now()) - Listing.first_seen_at) / 86400
        gone_days = session.scalar(select(func.percentile_cont(0.5).within_group(up_days)).where(*cohort))
        if gone_days is not None and float(gone_days) >= 14:
            gone_days = None
        neighborhoods = [
            {"name": name, "median": int(round(float(median), -1)), "count": int(count)}
            for name, median, count in session.execute(
                select(Listing.neighborhood, func.percentile_cont(0.5).within_group(Listing.price), func.count())
                .where(*where, Listing.neighborhood.is_not(None), Listing.neighborhood != "שאר העיר",
                       Listing.rooms.between(3, 3.5))
                .group_by(Listing.neighborhood)
                .having(func.count() >= MIN_PER_ROOMS)
                .order_by(func.count().desc())
                .limit(10)
            )
        ]
        newest = [
            {
                "price": listing.price, "rooms": listing.rooms, "neighborhood": listing.neighborhood,
                "street": listing.street, "size": listing.size_sqm, "photo": (listing.image_urls or [None])[0],
                "link": share.share_path(listing.id), "first_seen_at": listing.first_seen_at,
            }
            for listing in session.scalars(
                select(Listing)
                .where(*where, Listing.is_delisted.is_(False), Listing.image_urls != [])
                .order_by(Listing.first_seen_at.desc())
                .limit(NEWEST)
            )
        ]
        return {
            "city": city, "total": int(total), "week": int(week), "by_rooms": by_rooms,
            "gone_days": round(float(gone_days)) if gone_days is not None else None,
            "neighborhoods": sorted(neighborhoods, key=lambda n: n["median"]), "newest": newest,
        }

    return _cached(f"city:{city}", build)
