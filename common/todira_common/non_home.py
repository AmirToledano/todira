"""Ads that are not a home at all: a parking space or a storage room listed under rentals or sales.

2026-10-31 (owner, a parking space in Jerusalem sent as a one-room flat "70% below the area price"): measured live, in
30 days 250 live rentals opened with "חניה ..." / "מחסן ..." and about 1,300 alerts went out for such ads. The sites list
them in the same category as flats and give no type, so the ad's own opening words are what tells.

An ad counts only when its text OPENS with the word (after "להשכרה" and the like) AND its price or size is that of a
parking space or a storage room, so a flat whose ad happens to start with "חניה צמודה, 4 חדרים" at 6,000 ₪ is kept.
"""
from __future__ import annotations

import re

from sqlalchemy import and_, func, or_

_LEAD = r"^(?:להשכרה|למכירה|להשכיר|משכיר|משכירה|מוכר|מוכרת|השכרת|מכירת|דרוש שוכר ל)?\s*(?:מקום|מקומות)?\s*"
_PARKING = r"(?:חניה|חנייה|חניות|חנייות|חנית|חניית)"
_STORAGE = r"(?:מחסן|מחסנים)"
_PARKING_RE = re.compile(_LEAD + _PARKING)
_STORAGE_RE = re.compile(_LEAD + _STORAGE)
_LEADING_JUNK_RE = re.compile(r"^[^א-תa-zA-Z]+")

# Above these an ad that opens with "חניה" is a flat that mentions its parking first.
RENT_PRICE_LIMIT = 2000
SALE_PRICE_LIMIT = 800_000
SIZE_LIMIT = 25


def _cheap_or_small(deal_type: str | None, price: int | None, size_sqm: int | None) -> bool:
    if size_sqm is not None and 0 < size_sqm < SIZE_LIMIT:
        return True
    if price is None:
        return True
    limit = SALE_PRICE_LIMIT if deal_type == "sale" else RENT_PRICE_LIMIT
    return price < limit


def non_home_kind(description: str | None, deal_type: str | None, price: int | None, size_sqm: int | None) -> str | None:
    """"parking", "storage", or None for anything else (a home, or no text to tell by)."""
    if not description:
        return None
    head = _LEADING_JUNK_RE.sub("", description[:200].strip())[:60].lower()
    if _PARKING_RE.match(head):
        kind = "parking"
    elif _STORAGE_RE.match(head):
        kind = "storage"
    else:
        return None
    return kind if _cheap_or_small(deal_type, price, size_sqm) else None


def is_non_home(listing_row) -> bool:
    return non_home_kind(
        getattr(listing_row, "description", None),
        getattr(listing_row, "deal_type", None),
        getattr(listing_row, "price", None),
        getattr(listing_row, "size_sqm", None),
    ) is not None


def not_non_home_sql(listing):
    """The same test as a SQL condition that keeps homes, for queries that compare a listing with others
    (todira_common.area_price)."""
    head = func.lower(func.left(func.regexp_replace(func.coalesce(listing.description, ""), r"^[^א-תa-zA-Z]+", ""), 60))
    opens_with_word = or_(head.op("~")(_LEAD + _PARKING), head.op("~")(_LEAD + _STORAGE))
    cheap_or_small = or_(
        and_(listing.size_sqm.is_not(None), listing.size_sqm > 0, listing.size_sqm < SIZE_LIMIT),
        listing.price.is_(None),
        and_(listing.deal_type == "sale", listing.price < SALE_PRICE_LIMIT),
        and_(listing.deal_type != "sale", listing.price < RENT_PRICE_LIMIT),
    )
    # 2026-10-31: the cheap half first. Postgres keeps this order, and the text half reads every ad's whole description;
    # measured on the live database, the /rent query took 6.7 to 13.4 s with the text half first and 1.1 s like this.
    return ~and_(cheap_or_small, opens_with_word)
