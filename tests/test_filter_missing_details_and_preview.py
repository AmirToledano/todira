"""2026-10-27 (plan item 7): "show also listings without rooms / size" in matching, the price chart of the site's live
filter preview, and the shared form reader the save and the preview both use."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_filter_preview", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from test_matching import make_filter, make_listing  # noqa: E402

from todira_common.matching import evaluate  # noqa: E402


def test_unknown_rooms_fails_a_rooms_range_by_default():
    assert not evaluate(make_filter(rooms_min=3), make_listing(rooms=None)).matched


def test_unknown_rooms_and_size_pass_when_asked():
    f = make_filter(rooms_min=3, rooms_max=4, min_area_sqm=80, include_missing_details=True)
    assert evaluate(f, make_listing(rooms=None, size_sqm=None)).matched


def test_known_values_are_still_checked_when_unknown_ones_pass():
    f = make_filter(rooms_min=3, min_area_sqm=80, include_missing_details=True)
    assert not evaluate(f, make_listing(rooms=2, size_sqm=None)).matched
    assert not evaluate(f, make_listing(rooms=None, size_sqm=60)).matched


def test_price_chart_needs_enough_prices():
    assert website_main._price_chart([5000] * 5) is None
    assert website_main._price_chart([5000] * 50) is None  # one price only, nothing to spread


def test_price_chart_counts_every_price_inside_the_range():
    prices = list(range(3000, 8000, 10))
    chart = website_main._price_chart(prices)
    assert len(chart["bars"]) == website_main._PRICE_CHART_BARS
    inside = [p for p in prices if chart["from"] <= p <= chart["from"] + chart["step"] * len(chart["bars"])]
    assert sum(chart["bars"]) >= len(inside) * 0.9


def test_form_reader_sets_every_checkbox_and_swaps_reversed_ranges():
    f = SimpleNamespace()
    website_main._apply_filter_form(f, {
        "cities": [], "all_cities": "on", "price_min": "7,000", "price_max": "4000", "rooms_min": "", "rooms_max": "",
        "property_types": [], "floor_min": "", "floor_max": "", "include_missing_details": "on",
        "require_parking": None, "safe_room_pref": "nope", "furniture_pref": "any", "min_area_sqm": "", "keywords": "",
    })
    assert (f.price_min, f.price_max) == (4000, 7000)
    assert f.include_missing_details is True and f.require_parking is False
    assert f.cities == [] and f.safe_room_pref == "any"


def test_the_form_field_list_matches_both_routes():
    import inspect

    for route in (website_main.filter_update, website_main.filter_preview):
        params = set(inspect.signature(route).parameters) - {"request", "uid", "welcome"}
        assert params == set(website_main._FILTER_FORM_FIELDS), route.__name__
