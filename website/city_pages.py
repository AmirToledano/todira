"""A page per city: what renting there costs right now, how fast flats go, and the newest ones (2026-10-31, owner: "do
everything that can sell Todira, without paid ads").

People search Google for "דירות להשכרה בחיפה" and "כמה עולה דירה בחיפה". These pages answer with our own numbers, kept
fresh by the scraper, and end with the way into the bot. Every number comes from listings we collected in the last 30
days; nothing is estimated. A city with too few listings gets no page (404), so a thin page never goes up.
"""
from __future__ import annotations

import datetime as dt
import heapq
import logging
import math
import statistics
import threading
import time
from collections import defaultdict

from sqlalchemy import or_, select

from todira_common import share
from todira_common.models import Listing
from todira_common.non_home import not_non_home_sql

logger = logging.getLogger(__name__)

WINDOW = dt.timedelta(days=30)
GONE_COHORT_FROM = dt.timedelta(days=14)
MIN_LISTINGS = 30
MIN_PER_ROOMS = 5
NEWEST = 8
TTL_SECONDS = 3600
INDEX_CITIES = 40
_NOT_A_NEIGHBORHOOD = "שאר העיר"

# 2026-10-31: the first live visits took 16 s for /rent and 3 to 6 s per city (measured from outside after the deploy;
# diagnose-city-pages-speed.yaml showed every query reading the whole 30-day window from disk). So all cities are now
# built together from one pass over that window, kept for the hour, and rebuilt before it runs out by the website's
# warm-up thread (main.py), so no visitor or crawler waits for it. A request finds it built; only one that comes before
# the first build finishes builds it (and others wait for that one rather than starting their own).
_lock = threading.Lock()
_build_lock = threading.Lock()
_snapshot: dict = {"at": None, "index": None, "pages": None}


def _rentals(now: dt.datetime):
    return [
        Listing.deal_type == "rent",
        Listing.duplicate_of_id.is_(None),
        Listing.price.between(1000, 40000),
        or_(Listing.property_type.is_(None), Listing.property_type != "shared_room"),
        not_non_home_sql(Listing),
        Listing.first_seen_at >= now - WINDOW,
        Listing.city.is_not(None),
    ]


def _median(values) -> int:
    """The median rounded to tens, the same number Postgres' percentile_cont(0.5) gave before rounding."""
    return int(round(float(statistics.median(values)), -1))


def build(session, now: dt.datetime) -> tuple[list[dict], dict[str, dict]]:
    """(the index, every city's page) from one pass over the rentals first seen in the last 30 days."""
    count: dict[str, int] = defaultdict(int)
    week: dict[str, int] = defaultdict(int)
    three: dict[str, list[int]] = defaultdict(list)
    by_rooms: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    neighborhoods: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    up_days: dict[str, list[float]] = defaultdict(list)
    newest: dict[str, list] = defaultdict(list)
    week_from, cohort_to = now - dt.timedelta(days=7), now - GONE_COHORT_FROM
    query = select(
        Listing.id, Listing.city, Listing.neighborhood, Listing.street, Listing.rooms, Listing.price, Listing.size_sqm,
        Listing.first_seen_at, Listing.delisted_at, Listing.is_delisted, Listing.image_urls[1],
    ).where(*_rentals(now))
    for (listing_id, city, neighborhood, street, rooms, price, size, first_seen, delisted_at, is_delisted,
         photo) in session.execute(query.execution_options(yield_per=2000)):
        count[city] += 1
        if first_seen >= week_from:
            week[city] += 1
        if rooms is not None and 1 <= rooms <= 12:
            by_rooms[city][5 if rooms >= 5 else int(math.floor(rooms))].append(price)
        if rooms is not None and 3 <= rooms <= 3.5:
            three[city].append(price)
            if neighborhood is not None and neighborhood != _NOT_A_NEIGHBORHOOD:
                neighborhoods[city][neighborhood].append(price)
        # Half the ads were down within this many days. Over ads first seen 14 to 30 days ago, so every one had at least
        # 14 days; one still up counts as up until now. (Older ads are deleted once down, so they can't be used.) Shown
        # only when it is under 14 days, where the answer can't be cut short by the window.
        if first_seen <= cohort_to:
            up_days[city].append(((delisted_at or now) - first_seen).total_seconds() / 86400)
        heap = newest[city]
        if photo and not is_delisted and (len(heap) < NEWEST or (first_seen, listing_id) > heap[0][:2]):
            item = (first_seen, listing_id, {
                "price": price, "rooms": rooms, "neighborhood": neighborhood, "street": street, "size": size,
                "photo": photo, "link": share.share_path(listing_id), "first_seen_at": first_seen,
            })
            (heapq.heappush if len(heap) < NEWEST else heapq.heapreplace)(heap, item)

    pages: dict[str, dict] = {}
    for city, total in count.items():
        if total < MIN_LISTINGS:
            continue
        gone = statistics.median(up_days[city]) if up_days[city] else None
        hoods = [
            {"name": name, "median": _median(prices), "count": len(prices)}
            for name, prices in neighborhoods[city].items()
            if len(prices) >= MIN_PER_ROOMS
        ]
        hoods = sorted(hoods, key=lambda n: (-n["count"], n["name"]))[:10]
        pages[city] = {
            "city": city, "total": total, "week": week[city],
            "by_rooms": [
                {"rooms": rooms, "median": _median(prices), "count": len(prices)}
                for rooms, prices in sorted(by_rooms[city].items())
                if len(prices) >= MIN_PER_ROOMS
            ],
            "gone_days": round(gone) if gone is not None and gone < 14 else None,
            "neighborhoods": sorted(hoods, key=lambda n: n["median"]),
            "newest": [item[2] for item in sorted(newest[city], key=lambda item: item[:2], reverse=True)],
        }
    index = [
        {"city": city, "count": page["total"], "median3": _median(three[city]) if three[city] else None}
        for city, page in sorted(pages.items(), key=lambda kv: (-kv[1]["total"], kv[0]))
    ][:INDEX_CITIES]
    return index, pages


def refresh(session, now: dt.datetime | None = None) -> None:
    now = now or dt.datetime.now(dt.timezone.utc)
    index, pages = build(session, now)
    with _lock:
        _snapshot.update(at=time.monotonic(), index=index, pages=pages)


def _current(session) -> dict:
    with _lock:
        if _snapshot["at"] is not None and time.monotonic() - _snapshot["at"] < TTL_SECONDS:
            return dict(_snapshot)
    with _build_lock:  # one build at a time; who waited here gets what the build before them made
        with _lock:
            if _snapshot["at"] is not None and time.monotonic() - _snapshot["at"] < TTL_SECONDS:
                return dict(_snapshot)
        refresh(session)
    with _lock:
        return dict(_snapshot)


def rebuild(session_factory) -> None:
    """For the website's warm-up thread: build again now, whatever the age."""
    with _build_lock:
        with session_factory() as session:
            refresh(session)


def city_index(session) -> list[dict]:
    """The cities with enough rentals for a page, most listings first: name, listings in 30 days, 3-room median."""
    return _current(session)["index"]


def city_page(session, city: str) -> dict | None:
    """Everything the city page shows, or None when the city has too few rentals for a page."""
    return _current(session)["pages"].get(city)
