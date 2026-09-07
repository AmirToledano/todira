"""Tests for find_matching_listings' (bot/handlers/apartments.py) own SQL query — specifically
that it scopes by the filter's city as well as deal_type before applying RECENT_LISTINGS_SCANNED.

Found live 2026-09-07: this used to only filter by deal_type, so a narrow filter for one specific
(less active) city could have its own matching listings permanently pushed out of the
RECENT_LISTINGS_SCANNED window by newer listings scraped for every OTHER city — a real, live
"silently show fewer/zero matches" bug for exactly the users a narrow filter is meant to serve
well. website/main.py's /apartments had the identical gap (see
tests/test_website_content_gating.py's own regression test for that side).
"""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.apartments as apartments_module

find_matching_listings = apartments_module.find_matching_listings


class _RecordingSession:
    """Only scalars() is exercised by find_matching_listings: once for hidden-listing-ids, once
    for the listings query itself — both captured so the test can pick out the one selecting from
    "listings"."""

    def __init__(self):
        self.captured_stmts = []

    def scalars(self, stmt):
        self.captured_stmts.append(stmt)
        return []


def _filter(deal_type="rent", cities=None):
    return SimpleNamespace(deal_type=deal_type, cities=cities or [])


def test_query_is_scoped_by_city_when_filter_has_cities():
    session = _RecordingSession()
    find_matching_listings(session, user_id=1, filter_row=_filter(cities=["חיפה"]), limit=10)

    listings_stmt = next(s for s in session.captured_stmts if "FROM listings" in str(s))
    compiled_sql = str(listings_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "deal_type" in compiled_sql and "rent" in compiled_sql
    assert "city" in compiled_sql and "חיפה" in compiled_sql


def test_query_is_not_city_scoped_when_filter_has_no_cities():
    # An intentionally city-agnostic filter must not be narrowed by a city clause that isn't there.
    session = _RecordingSession()
    find_matching_listings(session, user_id=1, filter_row=_filter(cities=[]), limit=10)

    listings_stmt = next(s for s in session.captured_stmts if "FROM listings" in str(s))
    compiled_sql = str(listings_stmt.compile(compile_kwargs={"literal_binds": True}))
    where_clause = compiled_sql.split("WHERE", 1)[1]
    assert "listings.city" not in where_clause
