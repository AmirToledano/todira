"""Paid-access gate — a 3-day free trial, then a single recurring ₪49.90/month subscription
(2026-09-21 SaaS pivot, replacing the earlier one-time weekly/biweekly/monthly plans — those two
keys are kept below ONLY so historical Payment rows priced under them still mean something; /upgrade
no longer offers them). Payment itself is website/takbull_client.py's job (Takbull's recurring-
order API, DealType=4 — see that module's own comment for the real API docs this is built from);
website/main.py's /upgrade falls back to Grow, then the earlier informal click-trust model, when
Takbull's recurring API isn't configured yet. This module only answers "does this user get the
real thing, or the free lite tier" and "how long does a given plan extend access for" — bot/
website/notifier all call it rather than re-deriving the rule themselves.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from todira_common.models import User

SUBSCRIPTION_PLAN = "monthly_subscription"

PLAN_DURATIONS: dict[str, dt.timedelta] = {
    # Kept for historical Payment rows only — no longer offered on /upgrade (2026-09-21).
    "weekly": dt.timedelta(days=7),
    "biweekly": dt.timedelta(days=14),
    "monthly": dt.timedelta(days=30),
    SUBSCRIPTION_PLAN: dt.timedelta(days=30),
}
PLAN_PRICES_ILS: dict[str, Decimal] = {
    # Kept for historical Payment rows only — no longer offered on /upgrade (2026-09-21).
    "weekly": Decimal("1"),
    "biweekly": Decimal("25"),
    "monthly": Decimal("40"),
    # The only plan /upgrade actually offers now — single recurring monthly subscription.
    SUBSCRIPTION_PLAN: Decimal("49.90"),
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
