"""Paid-access gate — 2026-09-04 pricing decision: a 3-day free trial, then ₪10/week or ₪20/month,
informal/manual payment (a Bit transfer outside this system — no payment-gateway webhook), so
`paid_until` is set directly by the user's own plan-selection click (website's /upgrade route),
trusted rather than verified against a real charge. The owner can also grant free access to anyone
via the admin panel, independent of trial/payment. This module is the ONE place that answers
"does this user get the real thing, or the free lite tier" — bot/website/notifier all call it
rather than re-deriving the rule themselves.
"""
from __future__ import annotations

import datetime as dt

from dorin_common.models import User

PLAN_DURATIONS: dict[str, dt.timedelta] = {
    "weekly": dt.timedelta(days=7),
    "monthly": dt.timedelta(days=30),
}
PLAN_PRICES_ILS: dict[str, int] = {
    "weekly": 10,
    "monthly": 20,
}


def has_full_access(user: User, *, is_owner: bool = False) -> bool:
    """`is_owner` is passed in, not derived here — each surface (bot/website) already has its own
    way of checking OWNER_TELEGRAM_USER_ID, and this module stays free of that env-var lookup."""
    if is_owner or user.free_access_granted:
        return True
    now = dt.datetime.now(dt.timezone.utc)
    if user.trial_ends_at is not None and now < user.trial_ends_at:
        return True
    if user.paid_until is not None and now < user.paid_until:
        return True
    return False


def extend_paid_until(user: User, plan: str) -> None:
    """Extends from the LATER of "now" or the user's current paid_until — paying again before the
    previous period expires stacks the new period on top instead of wasting the remaining time,
    standard subscription-renewal semantics. Mutates `user` in place; the caller commits."""
    if plan not in PLAN_DURATIONS:
        raise ValueError(f"Unknown plan: {plan!r}")
    now = dt.datetime.now(dt.timezone.utc)
    base = user.paid_until if (user.paid_until is not None and user.paid_until > now) else now
    user.paid_until = base + PLAN_DURATIONS[plan]
