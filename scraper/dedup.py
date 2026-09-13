"""Cross-source duplicate detection — the same real-world apartment posted on more than one
source (e.g. Yad2 AND Komo) should surface to a user as ONE listing, not two independently
notified rows. See common/dorin_common/models.py's Listing.duplicate_of_id docstring for how the
result of find_duplicate_listing is actually used (only at INSERT time — scraper/main.py's
_upsert_listings).

There is no shared id across sources to match on — this is necessarily a heuristic, not a
certainty, and is documented as such rather than presented as a solved problem. The heuristic:
same canonicalized city + same normalized street text + same room count + same floor + a price
within a tolerance band. All of city/street/rooms/floor/price must be genuinely known on BOTH
sides for a match to fire — a listing missing any of them is left alone (never merged) rather than
risk a false-positive match on a coarser signal. This trades some missed real duplicates (a
false negative) for never wrongly hiding a genuinely distinct apartment (a false positive) — the
safer failure direction given a hidden apartment is a real, visible loss to the user, matching
this project's existing "benefit of the doubt" convention elsewhere (see normalize.py).

Restricted to a DIFFERENT source and to still-active (not is_delisted), still-canonical (not
itself already duplicate_of_id-tagged) rows — same-source duplicates are already handled by the
(source, external_id) unique constraint, and chaining a duplicate onto another duplicate would
make delisting/promotion logic (see the models.py docstring's own documented gap) even harder to
reason about for no real benefit.

Tie-break when two sources both introduce what looks like the same apartment: whichever source's
row already exists in the database wins as canonical — the later one is flagged as its duplicate.
Within a single scrape run, sources are processed in _SOURCE_SCRAPERS order (Yad2, Komo, Homeless
— see scraper/main.py), so a same-run collision resolves to "whichever ran first this run", not
necessarily the objectively "best" source. This is a deliberately simple v1 rule, not a quality
ranking — revisit if real usage shows a specific source's data is consistently worse to keep as
canonical.
"""
from __future__ import annotations

import re

from sqlalchemy import select

from dorin_common.models import Listing
from dorin_common.schemas import NormalizedListing

# A same-real-address street name can be spelled slightly differently across sites - a leading
# "רחוב"/"רח'" prefix one source includes and another doesn't, or a geresh/gershayim mark used
# inconsistently in an abbreviation. Confirmed live only for the "רחוב "/"רח' " prefix pattern
# (not an exhaustive list of every real variant that could exist) - extend if a real cross-source
# pair is found live that this doesn't already normalize to the same string.
_STREET_PREFIX_RE = re.compile(r"^(רחוב|רח['׳]?)\s+")
_STREET_PUNCTUATION_RE = re.compile(r"[\"'׳`]")
_WHITESPACE_RE = re.compile(r"\s+")

# Two sources can legitimately show slightly different prices for the exact same real listing —
# one snapshot a few hours/days stale relative to the other, or a site-specific "including
# arnona/vaad bayit" toggle. 5% (with a floor so a cheap listing isn't held to an unrealistically
# tiny absolute tolerance) is a starting guess, not calibrated against real observed cross-source
# price pairs (no such data exists yet) - revisit once real duplicate pairs are actually seen live.
_PRICE_TOLERANCE_RATIO = 0.05
_PRICE_TOLERANCE_MIN_ILS = 150


def _normalize_street_for_matching(street: str | None) -> str | None:
    """Best-effort normalization so the same real street compares equal across sources despite
    superficial text differences - NOT a guarantee two different-looking strings that are
    genuinely the same street will always match (see module docstring: a miss here just means a
    real duplicate isn't caught, the safer failure direction). Returns None for anything that
    normalizes to empty, same as a missing street - never a false "match" against another empty
    string."""
    if not street:
        return None
    text = _STREET_PREFIX_RE.sub("", street.strip())
    text = _STREET_PUNCTUATION_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip().lower()
    return text or None


def _prices_plausibly_match(price_a: int | None, price_b: int | None) -> bool:
    """Never treat two prices as matching when either is unknown - a missing price is not
    "close enough to anything", it's a real absence of the one signal being checked here."""
    if price_a is None or price_b is None:
        return False
    allowed_diff = max(max(price_a, price_b) * _PRICE_TOLERANCE_RATIO, _PRICE_TOLERANCE_MIN_ILS)
    return abs(price_a - price_b) <= allowed_diff


def find_duplicate_listing(session, item: NormalizedListing) -> int | None:
    """Returns the id of an existing, different-source, still-active, still-canonical Listing row
    believed to be the SAME real-world apartment as `item`, or None if no confident match is
    found (including whenever city/street/rooms/floor/price aren't ALL known on `item` itself —
    see module docstring). Called only for an item about to be INSERTED as brand new (see
    scraper/main.py's _upsert_listings) - never re-evaluated later for an already-existing row.

    Runs a coarse SQL filter first (different source, active, not itself a duplicate, exact city/
    rooms/floor match - all cheap equality/index-backed conditions) and only pulls the (normally
    tiny) candidate set into Python for the two comparisons that can't be done as a plain SQL
    equality: normalized street-text comparison and price-tolerance comparison."""
    normalized_street = _normalize_street_for_matching(item.street)
    if item.city is None or normalized_street is None or item.rooms is None or item.floor is None:
        return None

    table = Listing.__table__
    candidates = session.execute(
        select(table.c.id, table.c.street, table.c.price).where(
            table.c.source != item.source,
            table.c.is_delisted.is_(False),
            table.c.duplicate_of_id.is_(None),
            table.c.city == item.city,
            table.c.rooms == item.rooms,
            table.c.floor == item.floor,
        )
    ).all()

    for candidate_id, candidate_street, candidate_price in candidates:
        if _normalize_street_for_matching(candidate_street) != normalized_street:
            continue
        if not _prices_plausibly_match(item.price, candidate_price):
            continue
        return candidate_id
    return None
