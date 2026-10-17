"""Signed, time-limited token for a Telegram user's website login link (the `?t=` parameter).

2026-10-02 real security fix. The bot used to link to the website as `/apartments?uid=<telegram id>`
and the site trusted that bare number: anyone who knew or guessed a Telegram user id could open that
user's apartments/filter/account pages, change their filter, and (via /auth/google/start?uid=) link
their own Google account to the victim's account and take it over. A Telegram id is not a secret, and
this repository is public, so one was visible in old workflow files.

The bot, the scraper notifier and the check-in now put `?t=<this token>` in every link instead. The
site verifies the signature, establishes the normal signed session cookie, and from then on a bare
`?uid=` is never trusted. It lives in todira_common because bot, scraper and website all need it, and
the website's main.py cannot be imported from the others.
"""
from __future__ import annotations

import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# Same single secret as website/main.py's SESSION_SECRET_KEY, read independently here to
# avoid a circular import.
_SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "dev-only-insecure-session-key")
_serializer = URLSafeTimedSerializer(_SESSION_SECRET_KEY, salt="todira-tid-link")

# Links sit in a Telegram chat for a long time and people tap old ones, so this is generous: 180 days.
# Rotating SESSION_SECRET_KEY revokes every outstanding link at once.
UID_TOKEN_MAX_AGE_SECONDS = 180 * 24 * 60 * 60


def generate_uid_token(telegram_user_id: int) -> str:
    return _serializer.dumps(int(telegram_user_id))


def verify_uid_token(token: str) -> int | None:
    """The Telegram user id if `token` is a genuine, unexpired generate_uid_token() output, else None
    (forged, tampered, expired, or a bare number — a bare number is never accepted)."""
    try:
        value = _serializer.loads(token, max_age=UID_TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def signed_login_query(telegram_user_id: int) -> str:
    """`t=<token>` — the query-string fragment every bot/notifier link to the website uses."""
    return f"t={generate_uid_token(telegram_user_id)}"


# 2026-10-17 (owner, launch day): someone who signed in inside Instagram's (or Facebook's, TikTok's...) in-app
# browser and then moves to Safari/Chrome lands logged out - each app keeps its own cookies, nothing can share
# them. The "open in your browser" button carries this short-lived token instead, and /auth/handoff turns it
# into the normal session in the new browser. Ten minutes, and the website accepts each token once.
_handoff_serializer = URLSafeTimedSerializer(_SESSION_SECRET_KEY, salt="todira-browser-handoff")
HANDOFF_TOKEN_MAX_AGE_SECONDS = 10 * 60


def generate_handoff_token(user_id: int) -> str:
    return _handoff_serializer.dumps({"u": int(user_id), "n": os.urandom(8).hex()})


def verify_handoff_token(token: str) -> int | None:
    """The website user id (users.id) if `token` is a genuine, unexpired generate_handoff_token() output."""
    try:
        value = _handoff_serializer.loads(token, max_age=HANDOFF_TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    user_id = value.get("u") if isinstance(value, dict) else None
    return user_id if isinstance(user_id, int) and not isinstance(user_id, bool) else None
