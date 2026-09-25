"""Tests for _parse_optional_int/_parse_optional_float's real bug fix (2026-09-25), found via a
live code-review pass: price_min/price_max/floor_min/floor_max/min_area_sqm are plain Postgres
Integer columns (±2.1 billion), and rooms_min/rooms_max are NUMERIC(3,1) columns (max magnitude
99.9). int(raw)/float(raw) alone gladly parse a much bigger number than either column can hold,
which used to fail at the DB layer as an unhandled numeric-overflow error at save time instead of
a normal "not a valid number" reply at input time. float() also accepts "nan"/"inf" without
raising — a NaN rooms value would silently fail every comparison in matching.py's own room-range
check (any comparison against NaN is always False in IEEE 754), so the filter looked saved and
normal yet silently matched nothing, ever.
"""
from __future__ import annotations

from handlers.filter_conversation import _parse_optional_int, _parse_optional_float


def test_a_normal_int_still_parses():
    assert _parse_optional_int("5000") == (True, 5000)


def test_dash_and_empty_mean_no_value():
    assert _parse_optional_int("-") == (True, None)
    assert _parse_optional_float("") == (True, None)


def test_int_beyond_the_postgres_integer_column_is_rejected():
    ok, value = _parse_optional_int("99999999999999")
    assert ok is False


def test_int_at_the_real_column_boundary_still_parses():
    ok, value = _parse_optional_int("2147483647")
    assert ok is True
    assert value == 2147483647


def test_a_normal_float_still_parses():
    assert _parse_optional_float("3.5") == (True, 3.5)


def test_float_beyond_the_numeric_3_1_column_is_rejected():
    ok, value = _parse_optional_float("100")
    assert ok is False


def test_float_at_the_real_column_boundary_still_parses():
    ok, value = _parse_optional_float("99.9")
    assert ok is True
    assert value == 99.9


def test_nan_is_rejected_not_silently_saved():
    ok, value = _parse_optional_float("nan")
    assert ok is False


def test_infinity_is_rejected_not_silently_saved():
    ok, value = _parse_optional_float("inf")
    assert ok is False
    ok, value = _parse_optional_float("-infinity")
    assert ok is False
