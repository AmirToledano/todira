"""Unit tests for dorin_common/access.py — the paid-access gate (2026-09-04 pricing decision).
SimpleNamespace stands in for a real User row, same approach test_matching.py/test_cards.py use.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from dorin_common.access import PLAN_DURATIONS, extend_paid_until, has_full_access

NOW = dt.datetime.now(dt.timezone.utc)
PAST = NOW - dt.timedelta(days=1)
FUTURE = NOW + dt.timedelta(days=1)


def make_user(**overrides):
    defaults = dict(trial_ends_at=PAST, paid_until=None, free_access_granted=False)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_owner_always_has_access_regardless_of_trial_or_payment():
    user = make_user(trial_ends_at=PAST, paid_until=None, free_access_granted=False)
    assert has_full_access(user, is_owner=True) is True


def test_free_access_granted_overrides_expired_trial_and_no_payment():
    user = make_user(trial_ends_at=PAST, paid_until=None, free_access_granted=True)
    assert has_full_access(user) is True


def test_within_trial_window_has_access():
    user = make_user(trial_ends_at=FUTURE, paid_until=None)
    assert has_full_access(user) is True


def test_expired_trial_no_payment_has_no_access():
    user = make_user(trial_ends_at=PAST, paid_until=None)
    assert has_full_access(user) is False


def test_expired_trial_but_paid_until_future_has_access():
    user = make_user(trial_ends_at=PAST, paid_until=FUTURE)
    assert has_full_access(user) is True


def test_expired_trial_and_expired_payment_has_no_access():
    user = make_user(trial_ends_at=PAST, paid_until=PAST)
    assert has_full_access(user) is False


def test_extend_paid_until_weekly_from_no_prior_payment():
    user = make_user(paid_until=None)
    before = dt.datetime.now(dt.timezone.utc)
    extend_paid_until(user, "weekly")
    assert user.paid_until - before >= PLAN_DURATIONS["weekly"] - dt.timedelta(seconds=5)
    assert user.paid_until - before <= PLAN_DURATIONS["weekly"] + dt.timedelta(seconds=5)


def test_extend_paid_until_monthly_from_no_prior_payment():
    user = make_user(paid_until=None)
    before = dt.datetime.now(dt.timezone.utc)
    extend_paid_until(user, "monthly")
    assert user.paid_until - before >= PLAN_DURATIONS["monthly"] - dt.timedelta(seconds=5)


def test_extend_paid_until_biweekly_from_no_prior_payment():
    user = make_user(paid_until=None)
    before = dt.datetime.now(dt.timezone.utc)
    extend_paid_until(user, "biweekly")
    assert user.paid_until - before >= PLAN_DURATIONS["biweekly"] - dt.timedelta(seconds=5)
    assert user.paid_until - before <= PLAN_DURATIONS["biweekly"] + dt.timedelta(seconds=5)


def test_extend_paid_until_stacks_on_top_of_a_still_valid_period():
    # Paying again before the current period expires should ADD to it, not reset from "now" and
    # waste the remaining time.
    existing_expiry = NOW + dt.timedelta(days=3)
    user = make_user(paid_until=existing_expiry)
    extend_paid_until(user, "weekly")
    assert user.paid_until == existing_expiry + PLAN_DURATIONS["weekly"]


def test_extend_paid_until_restarts_from_now_when_previous_period_already_expired():
    user = make_user(paid_until=PAST)
    before = dt.datetime.now(dt.timezone.utc)
    extend_paid_until(user, "monthly")
    assert user.paid_until > before  # not based on the stale PAST expiry


def test_extend_paid_until_rejects_unknown_plan():
    user = make_user()
    with pytest.raises(ValueError):
        extend_paid_until(user, "yearly")
