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
# 2026-11-04 (owner): a page per neighbourhood too (/rent/<city>/<neighbourhood>), for searches like "דירות להשכרה
# בהדר". Same rules as a city: only flats of the last 30 days, a rooms row only with MIN_PER_ROOMS flats behind it, and
# a neighbourhood with fewer than MIN_HOOD_LISTINGS rentals (or no rooms row at all) gets no page, so none goes up thin.
MIN_HOOD_LISTINGS = 10

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


def _hood_name(neighborhood: str | None) -> str | None:
    """The neighbourhood as a page name, or None for no neighbourhood, "the rest of the city" or a name no URL keeps."""
    name = (neighborhood or "").strip()
    if not name or name == _NOT_A_NEIGHBORHOOD or set(name) <= {".", "/"}:
        return None
    return name


def _diff_percent(here: int, city: int | None) -> int | None:
    """How much more (or less, negative) a neighbourhood's median is than the city's, in whole percent."""
    if not city:
        return None
    return int(round((here - city) * 100 / city))


def _newest_first(heap: list) -> list[dict]:
    return [item[2] for item in sorted(heap, key=lambda item: item[:2], reverse=True)]


def build(session, now: dt.datetime) -> tuple[list[dict], dict[str, dict]]:
    """(the index, every city's page) from one pass over the rentals first seen in the last 30 days."""
    count: dict[str, int] = defaultdict(int)
    week: dict[str, int] = defaultdict(int)
    three: dict[str, list[int]] = defaultdict(list)
    by_rooms: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    neighborhoods: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    up_days: dict[str, list[float]] = defaultdict(list)
    newest: dict[str, list] = defaultdict(list)
    # 2026-11-04 (owner): the neighbourhood pages come from this same pass, so they cost no query of their own
    hood_count: dict[tuple[str, str], int] = defaultdict(int)
    hood_rooms: dict[tuple[str, str], dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    hood_newest: dict[tuple[str, str], list] = defaultdict(list)
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
        hood = _hood_name(neighborhood)
        if hood is not None:
            hood_count[(city, hood)] += 1
        if rooms is not None and 1 <= rooms <= 12:
            bucket = 5 if rooms >= 5 else int(math.floor(rooms))
            by_rooms[city][bucket].append(price)
            if hood is not None:
                hood_rooms[(city, hood)][bucket].append(price)
        if rooms is not None and 3 <= rooms <= 3.5:
            three[city].append(price)
            if neighborhood is not None and neighborhood != _NOT_A_NEIGHBORHOOD:
                neighborhoods[city][neighborhood].append(price)
        # Half the ads were down within this many days. Over ads first seen 14 to 30 days ago, so every one had at least
        # 14 days; one still up counts as up until now. (Older ads are deleted once down, so they can't be used.) Shown
        # only when it is under 14 days, where the answer can't be cut short by the window.
        if first_seen <= cohort_to:
            up_days[city].append(((delisted_at or now) - first_seen).total_seconds() / 86400)
        if photo and not is_delisted:
            flat = None
            for heap in (newest[city], hood_newest[(city, hood)] if hood is not None else None):
                if heap is None or not (len(heap) < NEWEST or (first_seen, listing_id) > heap[0][:2]):
                    continue
                flat = flat or {
                    "price": price, "rooms": rooms, "neighborhood": neighborhood, "street": street, "size": size,
                    "photo": photo, "link": share.share_path(listing_id), "first_seen_at": first_seen,
                }
                (heapq.heappush if len(heap) < NEWEST else heapq.heapreplace)(heap, (first_seen, listing_id, flat))

    hoods_of: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (hood_city, name), total_here in hood_count.items():
        hoods_of[hood_city].append((name, total_here))
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
        city_rooms = {
            rooms: _median(prices) for rooms, prices in by_rooms[city].items() if len(prices) >= MIN_PER_ROOMS
        }
        pages[city] = {
            "city": city, "total": total, "week": week[city],
            "by_rooms": [
                {"rooms": rooms, "median": city_rooms[rooms], "count": len(by_rooms[city][rooms])}
                for rooms in sorted(city_rooms)
            ],
            "gone_days": round(gone) if gone is not None and gone < 14 else None,
            "neighborhoods": sorted(hoods, key=lambda n: n["median"]),
            "newest": _newest_first(newest[city]),
        }
        hood_pages = {}
        for name, total_here in hoods_of[city]:
            if total_here < MIN_HOOD_LISTINGS:
                continue
            rows = []
            for rooms, prices in sorted(hood_rooms[(city, name)].items()):
                if len(prices) >= MIN_PER_ROOMS:
                    median = _median(prices)
                    rows.append({"rooms": rooms, "median": median, "count": len(prices),
                                 "city_median": city_rooms.get(rooms), "diff": _diff_percent(median, city_rooms.get(rooms))})
            if not rows:
                continue
            compared = [row for row in rows if row["diff"] is not None]
            hood_pages[name] = {
                "city": city, "name": name, "total": total_here, "by_rooms": rows,
                # the sentence under the title compares the rooms row with the most flats behind it
                "headline": max(compared, key=lambda row: (row["count"], -row["rooms"])) if compared else None,
                "newest": _newest_first(hood_newest[(city, name)]),
            }
        pages[city]["hood_pages"] = hood_pages
        pages[city]["hood_links"] = sorted(hood_pages, key=lambda name: (-hood_pages[name]["total"], name))
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


def neighbourhood_page(session, city: str, name: str) -> dict | None:
    """2026-11-04 (owner): one neighbourhood's page, or None when it has too few rentals (or its city has no page)."""
    page = _current(session)["pages"].get(city)
    return (page.get("hood_pages") or {}).get(name) if page else None


def neighbourhood_links(session, city: str) -> list[str]:
    """2026-11-04 (owner): the city's neighbourhoods that have a page, most rentals first."""
    page = _current(session)["pages"].get(city)
    return list(page.get("hood_links") or ()) if page else []


def neighbourhood_index(session) -> list[tuple[str, str]]:
    """2026-11-04 (owner): (city, neighbourhood) for every neighbourhood page, for the sitemap."""
    return [
        (city, name)
        for city, page in sorted(_current(session)["pages"].items())
        for name in page.get("hood_links") or ()
    ]
