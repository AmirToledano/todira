"""Pure filter-vs-listing matching logic — no I/O, fully unit-testable.

Design (per the plan, Section 4): a fixed set of "hard filters" (deal type, location, price,
rooms, floor, area, keywords, move-in date) must ALWAYS pass, regardless of flexible_match. A
separate pool of "mandatory criteria" (the 7 boolean amenity toggles, plus
safe_room_pref/furniture_pref/no_brokers when not left at their default "any"/false) is where
flexible_match's fuzziness applies: normally all must pass, but with flexible_match=True up to
one may fail.

"Miss at most one requirement" (not "exactly one") is a deliberate reading of the reference
bot's slightly ambiguous "flexible filter" description — the more user-friendly interpretation.
Revisit if it doesn't feel right once weighed against real dorin.app behavior.

Every mandatory-criteria field except no_brokers now gives an unknown (None/missing) listing value
the benefit of the doubt, i.e. never fails on it — see `_check_mandatory_criteria`'s own comment.
Not the original design (missing data used to count as a failure, "can't confirm the requirement
is met"), but the scraper doesn't populate any of this data at all yet (amenities live on a
listing's own detail page, not the search-results cards this project actually scrapes), so the
stricter behavior meant every filter using one of these toggles matched zero listings, always.
Revisit once per-listing detail scraping exists and these fields carry real data again.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from dorin_common.cities import normalize_spelling


@dataclass
class MatchResult:
    matched: bool
    failed_hard_filters: list[str] = field(default_factory=list)
    failed_mandatory_criteria: list[str] = field(default_factory=list)


def _in_range(value, lo, hi) -> bool:
    if lo is not None and value < lo:
        return False
    if hi is not None and value > hi:
        return False
    return True


def _check_hard_filters(filter_row, listing_row) -> list[str]:
    failed: list[str] = []

    if filter_row.deal_type != listing_row.deal_type:
        failed.append("deal_type")

    # listing_row.property_type is never actually populated by the scraper today (see
    # scraper/normalize.py - nothing sets NormalizedListing.property_type, so it's always None) -
    # an unknown property type gets the benefit of the doubt here rather than failing every
    # single listing outright, the same treatment safe_room_type/is_broker_listing already get
    # elsewhere in this file for the same reason (missing data isn't "doesn't match"). Found live
    # 2026-09-02: a real filter with all 7 property types checked (so filter_row.property_types
    # was non-empty, entering this branch) silently zeroed out every match, city/price/rooms
    # notwithstanding, since `None not in [...]` is always true.
    if filter_row.property_types and listing_row.property_type is not None:
        if listing_row.property_type not in filter_row.property_types:
            failed.append("property_type")

    if filter_row.cities:
        if listing_row.city not in filter_row.cities:
            failed.append("city")

    # normalize_spelling collapses כתיב מלא/חסר doubling (יי->י, וו->ו) — the same fix that made
    # city search tolerate "קרית מוצקין" vs "קריית מוצקין" (2026-09-02), generalized here to every
    # free-text place name this filter checks, not just cities (2026-09-02 follow-up request:
    # "לכל י' 1 או דאבל י' ... עיר רחוב או כל דבר אחר"). Neighborhood/street matching isn't reachable
    # from any UI yet (see filter_conversation.py's module docstring) but is future-proofed the same
    # way regardless, since it's a one-line cost and the whole point is not re-discovering this bug
    # per field.
    if filter_row.neighborhoods_include:
        key = normalize_spelling(f"{listing_row.city}:{listing_row.neighborhood}")
        wanted = {normalize_spelling(s) for s in filter_row.neighborhoods_include}
        if key not in wanted:
            failed.append("neighborhood_include")
    if filter_row.neighborhoods_exclude:
        key = normalize_spelling(f"{listing_row.city}:{listing_row.neighborhood}")
        excluded = {normalize_spelling(s) for s in filter_row.neighborhoods_exclude}
        if key in excluded:
            failed.append("neighborhood_exclude")

    if filter_row.streets_include:
        street = normalize_spelling((listing_row.street or "").strip().lower())
        wanted = {normalize_spelling(s.strip().lower()) for s in filter_row.streets_include}
        if street not in wanted:
            failed.append("street_include")
    if filter_row.streets_exclude:
        street = normalize_spelling((listing_row.street or "").strip().lower())
        excluded = {normalize_spelling(s.strip().lower()) for s in filter_row.streets_exclude}
        if street in excluded:
            failed.append("street_exclude")

    if listing_row.price is None:
        if filter_row.require_price:
            failed.append("price_required_but_missing")
        # else: a NULL price passes price filtering entirely, per the "show only listings with a
        # price" toggle semantics
    elif not _in_range(listing_row.price, filter_row.price_min, filter_row.price_max):
        failed.append("price_range")

    if filter_row.rooms_min is not None or filter_row.rooms_max is not None:
        if listing_row.rooms is None or not _in_range(
            listing_row.rooms, filter_row.rooms_min, filter_row.rooms_max
        ):
            failed.append("rooms_range")

    if filter_row.ground_floor_only:
        if listing_row.floor != 0:
            failed.append("ground_floor_only")
    elif filter_row.floor_min is not None or filter_row.floor_max is not None:
        if listing_row.floor is None or not _in_range(
            listing_row.floor, filter_row.floor_min, filter_row.floor_max
        ):
            failed.append("floor_range")

    if filter_row.min_area_sqm is not None:
        if listing_row.size_sqm is None or listing_row.size_sqm < filter_row.min_area_sqm:
            failed.append("min_area_sqm")

    if filter_row.keywords:
        description = (listing_row.description or "").lower()
        # "match any" interpretation of keyword search — a documented v1 choice
        if not any(kw.lower() in description for kw in filter_row.keywords):
            failed.append("keywords")

    if listing_row.move_in_date is not None:
        if filter_row.move_in_earliest and listing_row.move_in_date < filter_row.move_in_earliest:
            failed.append("move_in_too_early")
        if filter_row.move_in_latest and listing_row.move_in_date > filter_row.move_in_latest:
            failed.append("move_in_too_late")
    # a listing with no move-in date is treated as "available now" and always passes date
    # filtering — a listing simply never fails this check for missing data

    return failed


def _check_mandatory_criteria(filter_row, listing_row) -> list[str]:
    failed: list[str] = []

    # (filter attr, listing attr, human label) — an unknown (None) value on the listing side gets
    # the benefit of the doubt, same as property_type/is_broker_listing below. This USED to be
    # enforced conservatively (NULL counted as a failure, "we can't confirm the requirement is
    # met") — that was a deliberate, tested design choice, but turned into the exact same class of
    # bug property_type was: found live 2026-09-02 that scraper/yad2_client.py's card parser never
    # extracts ANY of has_parking/has_elevator/has_balcony/pets_allowed/is_renovated/
    # is_roommate_friendly at all (that data only exists on a listing's own detail page, not the
    # search-results cards this project scrapes — a real, separate, costlier scraping feature, not
    # yet built). So every one of these fields is None for every real listing, meaning any filter
    # with even one of these require_* toggles on got zero matches, always, regardless of
    # flexible_match. Until per-listing amenity scraping exists, "we don't know" has to mean "don't
    # reject on this" rather than "assume no."
    boolean_pairs = (
        ("require_parking", "has_parking", "parking"),
        ("require_elevator", "has_elevator", "elevator"),
        ("require_balcony", "has_balcony", "balcony"),
        ("require_pets_allowed", "pets_allowed", "pets_allowed"),
        ("require_renovated", "is_renovated", "renovated"),
        ("require_roommate_friendly", "is_roommate_friendly", "roommate_friendly"),
    )
    for filter_attr, listing_attr, label in boolean_pairs:
        listing_value = getattr(listing_row, listing_attr)
        if getattr(filter_row, filter_attr) and listing_value is not None and listing_value is not True:
            failed.append(label)

    # image_urls is likewise always [] today (never populated — see the boolean_pairs comment
    # above, same root cause) with no way to tell "no photos" apart from "never scraped photos" —
    # an empty list is not evidence either way, so this can't be enforced without also rejecting
    # every listing; left inert until real photo scraping exists rather than doing that.

    if filter_row.safe_room_pref == "safe_room_only":
        if listing_row.safe_room_type is not None and listing_row.safe_room_type != "safe_room":
            failed.append("safe_room_only")
    elif filter_row.safe_room_pref == "safe_room_or_shelter":
        if listing_row.safe_room_type is not None and listing_row.safe_room_type not in (
            "safe_room",
            "building_shelter",
        ):
            failed.append("safe_room_or_shelter")

    if filter_row.furniture_pref in ("furnished", "unfurnished"):
        if listing_row.furniture is not None and listing_row.furniture != filter_row.furniture_pref:
            failed.append("furniture_pref")

    # unknown broker status (None) gets the benefit of the doubt — only an explicit True fails
    if filter_row.no_brokers and listing_row.is_broker_listing is True:
        failed.append("no_brokers")

    return failed


def evaluate(filter_row, listing_row) -> MatchResult:
    """`filter_row`/`listing_row` are anything exposing the `filters`/`listings` column names as
    attributes — SQLAlchemy `Filter`/`Listing` instances in production, plain namespaces in
    tests.
    """
    failed_hard = _check_hard_filters(filter_row, listing_row)
    if failed_hard:
        return MatchResult(matched=False, failed_hard_filters=failed_hard)

    failed_mandatory = _check_mandatory_criteria(filter_row, listing_row)
    max_allowed_failures = 1 if filter_row.flexible_match else 0
    matched = len(failed_mandatory) <= max_allowed_failures
    return MatchResult(
        matched=matched, failed_hard_filters=[], failed_mandatory_criteria=failed_mandatory
    )
