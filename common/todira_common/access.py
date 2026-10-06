"""Paid-access gate — a 3-day free trial, then a single recurring ₪49.90/month subscription
(2026-09-21 SaaS pivot, replacing the earlier one-time weekly/biweekly/monthly plans — those two
keys are kept below ONLY so historical Payment rows priced under them still mean something; /upgrade
no longer offers them). Payment itself is website/takbull_client.py's job (Takbull's recurring-
order API, DealType=4 — see that module's own comment for the real API docs this is built from);
website/main.py's /upgrade falls back to the earlier informal click-trust model when
Takbull's recurring API isn't configured yet. This module only answers "does this user get the
real thing, or the free lite tier" and "how long does a given plan extend access for" — bot/
website/notifier all call it rather than re-deriving the rule themselves.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from todira_common.models import User

SUBSCRIPTION_PLAN = "monthly_subscription"

# 2026-10-06: the FREE Takbull flow sells one-time access passes (no auto-renewal), like dorin.app: 7 / 14 / 30 days.
# The paid recurring SUBSCRIPTION_PLAN above stays for when Takbull's API package is ever bought.
PASS_PLANS = ("pass_7", "pass_14", "pass_30")

PLAN_DURATIONS: dict[str, dt.timedelta] = {
    # Kept for historical Payment rows only — no longer offered on /upgrade (2026-09-21).
    "weekly": dt.timedelta(days=7),
    "biweekly": dt.timedelta(days=14),
    "monthly": dt.timedelta(days=30),
    SUBSCRIPTION_PLAN: dt.timedelta(days=30),
    "pass_7": dt.timedelta(days=7),
    "pass_14": dt.timedelta(days=14),
    "pass_30": dt.timedelta(days=30),
}
PLAN_PRICES_ILS: dict[str, Decimal] = {
    # Kept for historical Payment rows only — no longer offered on /upgrade (2026-09-21).
    "weekly": Decimal("1"),
    "biweekly": Decimal("25"),
    "monthly": Decimal("40"),
    # The only plan /upgrade actually offers now — single recurring monthly subscription.
    SUBSCRIPTION_PLAN: Decimal("49.90"),
    "pass_7": Decimal("19.90"),
    "pass_14": Decimal("29.90"),
    "pass_30": Decimal("49.90"),
}


def plan_for_amount(amount: Decimal) -> str | None:
    """Which one-time access pass an amount paid on the Takbull hosted page buys, or None when it matches no pass
    (e.g. the owner's NIS 1 test payment, or a stale price). The paid amount - Takbull's own record - decides how many
    days are granted, never the plan the customer happened to click on our site first."""
    for plan in PASS_PLANS:
        if PLAN_PRICES_ILS[plan] == amount:
            return plan
    return None


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


def has_paid_access(user: User, *, is_owner: bool = False) -> bool:
    """2026-09-27 real owner decision: same as has_full_access, EXCEPT the 3-day trial no longer
    counts. Reaching a listing's actual poster (WhatsApp message / phone number button) now needs
    a genuine paid subscription (or the owner/free-access-grant equivalents, which still count —
    those represent real access already granted, not a time-limited trial) — a trial user sees the
    upgrade-subscription popup on those two buttons specifically, same as a fully expired user.
    Everything else this project gates on access (the listing description, "view original
    listing") is UNCHANGED and still uses has_full_access above — only these two contact buttons
    tightened. See website/main.py's own _effective_paid_access for where this is actually used."""
    if is_owner or user.free_access_granted:
        return True
    now = dt.datetime.now(dt.timezone.utc)
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
