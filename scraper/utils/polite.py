"""Polite pacing: a random pause before a request, so a site we read never gets a steady burst from us.

2026-11-12 (owner: polite scraping). The pause is random rather than fixed, so several workers do not fire in lockstep.
Tests turn it off through POLITE_JITTER_DISABLED (see tests/conftest.py).
"""

from __future__ import annotations

import os
import random
import time

DISABLE_ENV_VAR = "POLITE_JITTER_DISABLED"


def jitter_sleep(low: float, high: float, *, sleep=time.sleep, uniform=random.uniform) -> float:
    """Sleeps a random number of seconds between `low` and `high` and returns it (0 when turned off)."""
    if os.environ.get(DISABLE_ENV_VAR, "").strip().lower() in ("1", "true"):
        return 0.0
    seconds = max(0.0, uniform(low, high))
    if seconds:
        sleep(seconds)
    return seconds
