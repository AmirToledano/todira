"""Paid-access gate — a 3-day free trial, then a weekly/biweekly/monthly plan (₪15/₪25/₪40,
2026-09-05 pricing revision). Payment itself is website/grow_client.py's job (Grow/Meshulam,
2026-09-05 — real gateway once the owner's עוסק פטור registration + Grow account are ready;
website/main.py's /upgrade falls back to the earlier informal click-trust model when Grow isn't
configured yet, see that module's own comment). This module only answers "does this user get the
real thing, or the free lite tier" and "how long does a given plan extend access for" — bot/
website/notifier all call it rather than re-deriving the rule themselves.
"""
from __future__ import annotations

import datetime as dt

from dorin_common.models import User

PLAN_DURATIONS: dict[str, dt.timedelta] = {
    "weekly": dt.timedelta(days=7),
    "biweekly": dt.timedelta(days=14),
    "monthly": dt.timedelta(days=30),
}
PLAN_PRICES_ILS: dict[str, int] = {
    "weekly": 15,
    "biweekly": 25,
    "monthly": 40,
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
