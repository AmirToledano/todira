"""How a listing's asking price compares with the same kind of listing around it (moved from website/main.py on
2026-10-24 so the bot's cards can show the "below the area price" tag too)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Float, cast, func, or_, select

from todira_common.models import Listing
from todira_common.non_home import is_non_home, not_non_home_sql

AREA_COMPARE_MIN_LISTINGS = 5
# Below this many comparable listings the page says the comparison rests on little data.
AREA_COMPARE_SOLID_LISTINGS = 10
AREA_COMPARE_WINDOW = dt.timedelta(days=30)
# Yad2's catch-all "rest of the city" bucket is not a real neighborhood, so it is compared with the whole city.
_NOT_A_NEIGHBORHOOD = {"שאר העיר"}
# Sizes outside this range are typos; they are left out of the price-per-m² median.
_PLAUSIBLE_SQM = (15, 500)


# A card gets the "below the area price" tag when its price is at least this much under the median of a solid group.
BELOW_AREA_TAG_PCT = 20


def area_price_comparison(session, listing: Listing) -> dict | None:
    """How this listing's asking price compares with the same kind of listing around it - computed only from listings we
    collected ourselves, nothing estimated or looked up elsewhere (2026-10-14 owner request: "as real and honest as it
    can be").

    The peers: other listings (never this one, never a cross-site duplicate of the same flat) with the same deal type and
    room count, seen live in the last AREA_COMPARE_WINDOW (so ones taken down recently - often because they were let -
    still count), a shared room only against shared rooms. In the same neighborhood when it has at least
    AREA_COMPARE_MIN_LISTINGS of them, otherwise the whole city; fewer than that anywhere and there's no comparison.
    The median, not the average, so one mistyped price can't drag it. When this listing has a size, the median price per
    m² of the same peers (those with a plausible size) is returned too: a big flat can cost more and still be cheaper
    per m². These are asking prices from the ads, not the prices flats were finally let or sold for."""
    if not listing.price or not listing.city or is_non_home(listing):
        return None
    conditions = [
        Listing.duplicate_of_id.is_(None),
        Listing.deal_type == listing.deal_type,
        Listing.price.is_not(None),
        Listing.price > 0,
        Listing.id != listing.id,
        Listing.city == listing.city,
        Listing.scraped_at >= func.now() - AREA_COMPARE_WINDOW,
        # 2026-10-31: parking spaces and storage rooms listed as one-room flats pulled the one-room median down
        not_non_home_sql(Listing),
    ]
    if listing.duplicate_of_id is not None:
        conditions.append(Listing.id != listing.duplicate_of_id)
    if listing.rooms is not None:
        conditions.append(Listing.rooms == listing.rooms)
    if listing.property_type == "shared_room":
        conditions.append(Listing.property_type == "shared_room")
    else:
        conditions.append(or_(Listing.property_type.is_(None), Listing.property_type != "shared_room"))
    scopes = []
    if listing.neighborhood and listing.neighborhood not in _NOT_A_NEIGHBORHOOD:
        scopes.append((listing.neighborhood, [*conditions, Listing.neighborhood == listing.neighborhood]))
    scopes.append((listing.city, conditions))
    for area, where in scopes:
        median, count = session.execute(
            select(func.percentile_cont(0.5).within_group(Listing.price), func.count()).where(*where)
        ).one()
        if not median or count < AREA_COMPARE_MIN_LISTINGS:
            continue
        median = float(median)
        result = {
            "area": area,
            "median": int(round(median, -1)),
            "count": count,
            "diff_pct": int(round((listing.price - median) / median * 100)),
            "solid": count >= AREA_COMPARE_SOLID_LISTINGS,
            "sqm_median": None,
        }
        low, high = _PLAUSIBLE_SQM
        if listing.size_sqm and low <= listing.size_sqm <= high:
            per_sqm = cast(Listing.price, Float) / Listing.size_sqm
            sqm_median, sqm_count = session.execute(
                select(func.percentile_cont(0.5).within_group(per_sqm), func.count()).where(
                    *where, Listing.size_sqm.between(low, high)
                )
            ).one()
            if sqm_median and sqm_count >= AREA_COMPARE_MIN_LISTINGS:
                result["sqm_median"] = int(round(float(sqm_median)))
                result["sqm_count"] = sqm_count
        return result
    return None


def below_area_pct(session, listing: Listing) -> int | None:
    """How many percent under the area price this listing is, when it is at least BELOW_AREA_TAG_PCT under a median of
    at least AREA_COMPARE_SOLID_LISTINGS comparable listings; None otherwise."""
    result = area_price_comparison(session, listing)
    if not result or not result["solid"] or result["diff_pct"] > -BELOW_AREA_TAG_PCT:
        return None
    return -result["diff_pct"]
