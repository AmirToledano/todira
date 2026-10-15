"""Cross-source duplicate detection — the same real-world apartment posted on more than one
source (e.g. Yad2 AND Komo) should surface to a user as ONE listing, not two independently
notified rows. See common/todira_common/models.py's Listing.duplicate_of_id docstring for how the
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
Within a single scrape run, sources are processed in _ALL_SOURCE_SCRAPERS order (Yad2, Komo, Homeless
— see scraper/main.py), so a same-run collision resolves to "whichever ran first this run", not
necessarily the objectively "best" source. This is a deliberately simple v1 rule, not a quality
ranking — revisit if real usage shows a specific source's data is consistently worse to keep as
canonical.

2026-10-15: two passes at the end of every main scraper run complete this (promote_live_duplicates,
link_missed_duplicates - see their own docstrings): the documented "canonical delisted, duplicate still live" gap is
closed, and pairs the insert-time check could not see (fields filled in later, a price that moved closer, ads older
than this module) are linked after the fact.
"""
from __future__ import annotations

import re
from itertools import groupby

from sqlalchemy import select
from sqlalchemy import text as sql_text

from todira_common.models import Listing
from todira_common.schemas import NormalizedListing

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


# 2026-10-15 (owner: "improve the also-posted-on detection"). Komo almost always writes the house number into the street
# ("הרצל 12") while Yad2 does so only about half the time, so the exact street comparison above never pairs those two.
# Measured live before using it (diagnose-cross-source-duplicates-rules.yaml): among Komo/Yad2 ads that agree on street
# name, floor, rooms, price and size and BOTH carry a number, 96% carry the same number. So when only ONE side has a
# number, the street NAME may stand in for the full street - but only with both sizes known and agreeing, and only when
# exactly one ad qualifies (two candidates means two flats in the same street, and we can't tell which). Not done for a
# missing floor: ads that agree on street, number, rooms, size and price are on different floors 8% of the time - too
# many different flats in one building that would be wrongly hidden.
_HOUSE_NUMBER_RE = re.compile(r"\s*\d.*$")
_SIZE_TOLERANCE_RATIO = 0.05
_SIZE_TOLERANCE_MIN_SQM = 2


def _street_name_and_has_number(normalized_street: str | None) -> tuple[str | None, bool]:
    """Splits an already-normalized street into its name (everything before the first digit) and whether a house number
    followed. A street that IS a number ("1 במאי") has no usable name and returns None."""
    if not normalized_street:
        return None, False
    name = _HOUSE_NUMBER_RE.sub("", normalized_street).strip()
    return (name or None), any(ch.isdigit() for ch in normalized_street)


def _sizes_agree(size_a: int | None, size_b: int | None) -> bool:
    if size_a is None or size_b is None:
        return False
    return abs(size_a - size_b) <= max(max(size_a, size_b) * _SIZE_TOLERANCE_RATIO, _SIZE_TOLERANCE_MIN_SQM)


def same_apartment_by_street_name(street_a: str | None, size_a: int | None, street_b: str | None, size_b: int | None) -> bool:
    """The looser rule above, for two ads already known to agree on city, rooms, floor and price: same street name, a
    house number on exactly one side, both sizes known and agreeing. The caller still has to make sure only ONE ad
    qualifies."""
    name_a, number_a = _street_name_and_has_number(_normalize_street_for_matching(street_a))
    name_b, number_b = _street_name_and_has_number(_normalize_street_for_matching(street_b))
    return name_a is not None and name_a == name_b and number_a != number_b and _sizes_agree(size_a, size_b)


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
        select(table.c.id, table.c.street, table.c.price, table.c.size_sqm).where(
            table.c.source != item.source,
            table.c.is_delisted.is_(False),
            table.c.duplicate_of_id.is_(None),
            table.c.city == item.city,
            table.c.rooms == item.rooms,
            table.c.floor == item.floor,
        )
    ).all()

    by_street_name = []
    for candidate_id, candidate_street, candidate_price, candidate_size in candidates:
        if not _prices_plausibly_match(item.price, candidate_price):
            continue
        if _normalize_street_for_matching(candidate_street) == normalized_street:
            return candidate_id
        if same_apartment_by_street_name(item.street, item.size_sqm, candidate_street, candidate_size):
            by_street_name.append(candidate_id)
    return by_street_name[0] if len(by_street_name) == 1 else None


def _move_user_state(session, moves: dict[int, int]) -> None:
    """`moves` maps a row that stops being the shown one to the row now shown for the same apartment. Likes and hides
    move with it (an apartment someone liked stays in their list, one they hid stays hidden), and the "already sent"
    marks are copied, so no one gets the same apartment again as new."""
    if not moves:
        return
    old_ids = list(moves)
    params = {"old": old_ids, "new": [moves[old] for old in old_ids]}
    mapping = "WITH m AS (SELECT * FROM unnest(CAST(:old AS bigint[]), CAST(:new AS bigint[])) AS t(old_id, new_id)) "
    session.execute(sql_text(
        mapping + "INSERT INTO user_listing_actions (user_id, listing_id, action, created_at) "
        "SELECT a.user_id, m.new_id, a.action, a.created_at FROM user_listing_actions a JOIN m ON a.listing_id = m.old_id "
        "ON CONFLICT (user_id, listing_id, action) DO NOTHING"
    ), params)
    session.execute(sql_text("DELETE FROM user_listing_actions WHERE listing_id = ANY(CAST(:old AS bigint[]))"), params)
    session.execute(sql_text(
        mapping + "INSERT INTO sent_notifications (user_id, listing_id, reason, sent_at) "
        "SELECT s.user_id, m.new_id, s.reason, s.sent_at FROM sent_notifications s JOIN m ON s.listing_id = m.old_id "
        "ON CONFLICT (user_id, listing_id, reason) DO NOTHING"
    ), params)


def promote_live_duplicates(session) -> int:
    """2026-10-15 (live: 239 apartments were invisible): only the canonical row of an apartment is ever shown, so when
    the canonical row was delisted while a duplicate on another site was still live, the apartment vanished from every
    list. Now the earliest-seen live duplicate becomes the shown row, and every other row of that apartment - the
    delisted one included, should it come back - points at it. Users' likes/hides/sent marks move along. Returns how
    many apartments came back."""
    rows = session.execute(sql_text(
        "SELECT DISTINCT ON (d.duplicate_of_id) d.duplicate_of_id, d.id "
        "FROM listings d JOIN listings c ON c.id = d.duplicate_of_id "
        "WHERE NOT d.is_delisted AND c.is_delisted AND c.duplicate_of_id IS NULL "
        "ORDER BY d.duplicate_of_id, d.first_seen_at, d.id"
    )).all()
    moves = {old_id: new_id for old_id, new_id in rows}
    if not moves:
        return 0
    old_ids = list(moves)
    session.execute(sql_text(
        "WITH m AS (SELECT * FROM unnest(CAST(:old AS bigint[]), CAST(:new AS bigint[])) AS t(old_id, new_id)) "
        "UPDATE listings l SET duplicate_of_id = CASE WHEN l.id = m.new_id THEN NULL ELSE m.new_id END "
        "FROM m WHERE l.duplicate_of_id = m.old_id OR l.id = m.old_id"
    ), {"old": old_ids, "new": [moves[old] for old in old_ids]})
    _move_user_state(session, moves)
    session.commit()
    return len(moves)


# Every pair of live, shown rows from two different sites that agree on deal, city, rooms, floor and street NAME (house
# number cut off) - the coarse part, done in SQL; the street/price/size rules themselves are checked in Python with the
# same functions the insert-time check uses. Both directions, so uniqueness can be judged from each side.
_LINK_CANDIDATES_SQL = r"""
WITH a AS (
  SELECT id, source, deal_type, city, rooms, floor, price, size_sqm, street, first_seen_at,
         nullif(regexp_replace(trim(regexp_replace(lower(regexp_replace(regexp_replace(trim(street),
           '^(רחוב|רח[''׳]?)\s+', ''), '["''׳`]', '', 'g')), '\s*[0-9].*$', '')), '\s+', ' ', 'g'), '') AS name
  FROM listings
  WHERE NOT is_delisted AND duplicate_of_id IS NULL AND city IS NOT NULL AND rooms IS NOT NULL
    AND floor IS NOT NULL AND price IS NOT NULL AND coalesce(street, '') <> ''
)
SELECT n.id, n.source, n.first_seen_at, n.street, n.size_sqm, n.price,
       o.id, o.source, o.first_seen_at, o.street, o.size_sqm, o.price
FROM a n JOIN a o ON o.source <> n.source AND o.deal_type = n.deal_type AND o.city = n.city
                 AND o.rooms = n.rooms AND o.floor = n.floor AND o.name = n.name
ORDER BY n.id, o.first_seen_at, o.id
"""


def link_missed_duplicates(session) -> int:
    """2026-10-15: links shown rows that are the same apartment on two sites but were never linked - the insert-time
    check only runs once, before the description fills in a floor or size and before a price moves closer, and ads
    older than that check were never compared at all (live: ~1,000 such Komo/Yad2 pairs). The newer row is linked to
    the older one, with the same rules as find_duplicate_listing: the exact street, or the street name when only one
    side has a house number (sizes agreeing, and the two ads the ONLY such match for each other).

    Conservative on purpose: never builds a chain (a row already linked this pass is not a target), and never puts
    two ads of the SAME site into one apartment - two identical-looking Yad2 ads may be two flats in one building.
    Returns how many rows were linked."""
    rows = session.execute(sql_text(_LINK_CANDIDATES_SQL)).all()
    if not rows:
        return 0
    info: dict[int, tuple] = {}
    exact: dict[int, list[int]] = {}
    loose: dict[int, set[int]] = {}
    for n_id, group in groupby(rows, key=lambda row: row[0]):
        for row in group:
            _, n_source, n_seen, n_street, n_size, n_price, o_id, o_source, o_seen, o_street, o_size, o_price = row
            info[n_id] = (n_seen, n_id, n_source)
            info[o_id] = (o_seen, o_id, o_source)
            if not _prices_plausibly_match(n_price, o_price):
                continue
            if _normalize_street_for_matching(n_street) == _normalize_street_for_matching(o_street):
                exact.setdefault(n_id, []).append(o_id)
            elif same_apartment_by_street_name(n_street, n_size, o_street, o_size):
                loose.setdefault(n_id, set()).add(o_id)
    rows = None

    involved = list(info)
    group_sources: dict[int, set[str]] = {row_id: {info[row_id][2]} for row_id in involved}
    for canonical_id, source in session.execute(sql_text(
        "SELECT duplicate_of_id, source FROM listings WHERE NOT is_delisted AND duplicate_of_id = ANY(CAST(:ids AS bigint[]))"
    ), {"ids": involved}).all():
        group_sources[canonical_id].add(source)

    links: dict[int, int] = {}
    targets: set[int] = set()
    for n_id in sorted(involved, key=lambda row_id: info[row_id]):
        older = [o_id for o_id in exact.get(n_id, []) if info[o_id] < info[n_id]]
        if not exact.get(n_id):  # the looser rule only for an ad with no exact match at all
            only = loose.get(n_id, set())
            if len(only) == 1:
                (o_id,) = only
                if loose.get(o_id) == {n_id} and info[o_id] < info[n_id]:
                    older = [o_id]
        for o_id in older:  # oldest first
            if o_id in links or n_id in targets or group_sources[o_id] & group_sources[n_id]:
                continue
            links[n_id] = o_id
            targets.add(o_id)
            group_sources[o_id] |= group_sources[n_id]
            break
    if not links:
        return 0
    new_ids = list(links)
    session.execute(sql_text(
        "WITH m AS (SELECT * FROM unnest(CAST(:old AS bigint[]), CAST(:new AS bigint[])) AS t(old_id, new_id)) "
        "UPDATE listings l SET duplicate_of_id = m.new_id FROM m WHERE l.id = m.old_id OR l.duplicate_of_id = m.old_id"
    ), {"old": new_ids, "new": [links[row_id] for row_id in new_ids]})
    _move_user_state(session, links)
    session.commit()
    return len(links)
