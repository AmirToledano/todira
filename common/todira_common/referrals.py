"""Invite a friend (2026-10-31, owner: "everything that can sell Todira").

Every user has a link t.me/AmirDirotBot?start=inv_<id>_<signature> (/profile shows it). Someone new who opens it is
remembered as invited by that user (users.referred_by_user_id), and when they finish signing up (their first search is
saved) both get REWARD_DAYS free days, added after whatever access they already have, the same way the owner's gift days
work. A user is rewarded for at most MAX_REWARDS friends. The inviter hears about it the next morning
(scraper/checkin.py), since messages to users go out in the morning only.

The signature (keyed by SESSION_SECRET_KEY, like todira_common.share) stops anyone from making up a code for someone
else's id.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import re

from sqlalchemy import func, select

from todira_common.models import User

PREFIX = "inv_"
REWARD_DAYS = 7
MAX_REWARDS = 10
_SIG_LEN = 10
_CODE_RE = re.compile(r"^inv_([0-9a-z]{1,12})_([0-9a-f]{10})$")
BOT_LINK = "https://t.me/AmirDirotBot?start="


def _secret() -> bytes:
    return os.environ.get("SESSION_SECRET_KEY", "dev-only-insecure-session-key").encode()


def _base36(number: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        number, rest = divmod(number, 36)
        out = digits[rest] + out
        if number == 0:
            return out


def _signature(user_id: int) -> str:
    return hmac.new(_secret(), f"invite:{user_id}".encode(), hashlib.sha256).hexdigest()[:_SIG_LEN]


def invite_code(user_id: int) -> str:
    return f"{PREFIX}{_base36(user_id)}_{_signature(user_id)}"


def invite_link(user_id: int) -> str:
    return BOT_LINK + invite_code(user_id)


def inviter_id(code: str | None) -> int | None:
    """The inviting user's id, or None for anything that is not a code we signed."""
    match = _CODE_RE.match(code or "")
    if not match:
        return None
    user_id = int(match.group(1), 36)
    return user_id if hmac.compare_digest(match.group(2), _signature(user_id)) else None


def add_free_days(user: User, days: int, now: dt.datetime) -> None:
    start = max(value for value in (now, user.trial_ends_at, user.paid_until) if value is not None)
    user.trial_ends_at = start + dt.timedelta(days=days)
    user.trial_reminder_sent_at = None  # remind again before the new end


def reward(session, friend: User, now: dt.datetime) -> bool:
    """Gives the friend and their inviter REWARD_DAYS each, once, when the friend finished signing up. Does not commit.
    True when the friend got the days."""
    if friend.referred_by_user_id is None or friend.referral_rewarded_at is not None:
        return False
    inviter = session.get(User, friend.referred_by_user_id)
    if inviter is None or inviter.id == friend.id:
        return False
    friend.referral_rewarded_at = now
    add_free_days(friend, REWARD_DAYS, now)
    rewarded_before = session.scalar(
        select(func.count()).select_from(User).where(
            User.referred_by_user_id == inviter.id, User.referral_rewarded_at.is_not(None), User.id != friend.id
        )
    ) or 0
    if rewarded_before < MAX_REWARDS:
        add_free_days(inviter, REWARD_DAYS, now)
        inviter.referral_days_unannounced = (inviter.referral_days_unannounced or 0) + REWARD_DAYS
    return True
