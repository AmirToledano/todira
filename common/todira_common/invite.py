"""Invite a friend (2026-10-20, owner: "whoever brings a friend gets 5 more days on top of the 10").

2026-10-21 (owner: "this way people just send each other links and nobody ever pays"): the reward now comes only when
the friend PAYS for the first time. The friend still gets the regular free trial like everyone else; the inviter's
INVITE_BONUS days are added on the friend's first confirmed payment - on top of a paid period that is still running,
else on top of the trial (from today when it already ended).

Every user has an invite link, t.me/<bot>?start=inv_<user id>_<signature> (/invite in the bot). When someone who has
never used the bot starts it through that link, app_flags "invite:<new user id>" remembers the inviter; once that
friend pays, "invite_paid:<new user id>" marks the reward as given, so it is given once. The signature (HMAC with the
session secret) keeps anyone from writing a link for someone else's account.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os

from sqlalchemy.orm import Session

from todira_common.app_flags import get_flag, set_flag
from todira_common.models import User

PREFIX = "inv_"
INVITE_BONUS = dt.timedelta(days=5)
# A /start counts as a new friend only for an account made this recently (the same /start that created it).
NEW_ACCOUNT_WINDOW = dt.timedelta(minutes=10)
BOT_URL = "https://t.me/AmirDirotBot"


def _signature(user_id: int) -> str:
    secret = os.environ.get("SESSION_SECRET_KEY", "dev-only-insecure-session-key").encode()
    return hmac.new(secret, f"invite:{user_id}".encode(), hashlib.sha256).hexdigest()[:12]


def invite_code(user_id: int) -> str:
    return f"{PREFIX}{user_id}_{_signature(user_id)}"


def invite_link(user_id: int) -> str:
    return f"{BOT_URL}?start={invite_code(user_id)}"


def inviter_id(payload: str | None) -> int | None:
    """The inviting user's id from a /start payload, or None when it is not a genuine invite link."""
    if not payload or not payload.startswith(PREFIX):
        return None
    try:
        raw_id, signature = payload[len(PREFIX):].split("_", 1)
        user_id = int(raw_id)
    except ValueError:
        return None
    return user_id if hmac.compare_digest(signature, _signature(user_id)) else None


def record_invite(session: Session, new_user: User, payload: str | None, now: dt.datetime) -> int | None:
    """Remembers who invited `new_user` when they just joined through a link. Returns the inviter's id, else None."""
    inviter = inviter_id(payload)
    if inviter is None or inviter == new_user.id:
        return None
    created = new_user.created_at
    if created is None or created < now - NEW_ACCOUNT_WINDOW:
        return None  # an existing user opening a friend's link is not a new friend
    flag = f"invite:{new_user.id}"
    if get_flag(session, flag) or session.get(User, inviter) is None:
        return None
    set_flag(session, flag, str(inviter))
    return inviter


def reward_for_payment(session: Session, payer: User, now: dt.datetime) -> User | None:
    """Gives the inviter their days when `payer` (a friend they invited) pays for the first time. Returns the
    rewarded inviter, else None. Saving the flag commits the extension with it."""
    invited_by = get_flag(session, f"invite:{payer.id}")
    if not invited_by or get_flag(session, f"invite_paid:{payer.id}"):
        return None
    try:
        user = session.get(User, int(invited_by))
    except ValueError:
        return None
    if user is None:
        return None
    if user.paid_until is not None and user.paid_until > now:
        user.paid_until = user.paid_until + INVITE_BONUS
    else:
        user.trial_ends_at = max(user.trial_ends_at or now, now) + INVITE_BONUS
    set_flag(session, f"invite_paid:{payer.id}", str(user.id))
    return user


def access_end(user: User, now: dt.datetime) -> dt.datetime:
    if user.paid_until is not None and user.paid_until > now:
        return user.paid_until
    return user.trial_ends_at
