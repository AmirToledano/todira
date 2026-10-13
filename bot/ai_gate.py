"""When the bot may call Gemini (2026-10-13, owner report).

Gemini's prepaid balance ran out (HTTP 402 on every model), and every new user only got "technical hiccup". Two guards,
so the AI can neither block the bot nor be drained:
- Each user gets at most DAILY_LIMIT AI calls a day (kept in their own persisted user_data). Plain rules
  (todira_common.search_text) handle the common messages, so a normal user rarely uses any; someone flooding the bot
  with unrelated messages stops reaching the AI after a few.
- After a failed call, nobody calls the AI for a while (todira_common.gemini_client.pause): a balance problem lasts
  hours or days, and each failing call only made the user wait for nothing.
The bot works fully without the AI either way: onboarding asks for what the rules didn't find, with buttons.
"""
from __future__ import annotations

import datetime as dt

from todira_common import gemini_client

DAILY_LIMIT = 8


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def allowed(user_data: dict) -> bool:
    """True when this user may make one more AI call right now (call `used` right before making it)."""
    if not gemini_client.available():
        return False
    quota = user_data.get("ai_quota") or {}
    today = _now().date().isoformat()
    return quota.get("day") != today or quota.get("used", 0) < DAILY_LIMIT


def used(user_data: dict) -> None:
    today = _now().date().isoformat()
    quota = user_data.get("ai_quota") or {}
    count = quota.get("used", 0) if quota.get("day") == today else 0
    user_data["ai_quota"] = {"day": today, "used": count + 1}


def failed() -> None:
    gemini_client.pause()


def reset() -> None:
    """Tests only."""
    gemini_client.reset_pause()
