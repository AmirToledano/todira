"""Signed, time-limited tokens for a WhatsApp-only account's ?wid= login link.

2026-09-25 real security bug found via a live code-review pass: ?wid= used to carry the bare
WhatsApp phone number, and website/main.py's _resolve_user wid branch established a FULL logged-in
session for ANYONE who presented it — no verification at all. A phone number isn't a secret
(contacts, SIM-swap, straightforward E.164-format guessing all know/find it), so this was a real,
zero-effort account-takeover: visiting /account?wid=<any real user's number> logged the visitor in
as that user outright, no OAuth, no password, nothing.

Lives in common/todira_common (not website/main.py) specifically so website/whatsapp_webhook.py can
generate a token too, without a circular import — main.py does `from whatsapp_webhook import
router`, so whatsapp_webhook.py importing back from main.py would fail at module load time.
"""
from __future__ import annotations

import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# Mirrors website/main.py's own SESSION_SECRET_KEY exactly (same env var, same dev-only fallback)
# — a single source of truth for this secret, read independently here rather than imported, to
# avoid the circular-import problem described above.
_SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "dev-only-insecure-session-key")
_wid_serializer = URLSafeTimedSerializer(_SESSION_SECRET_KEY, salt="todira-wid-link")

# 30 days: these links go out over WhatsApp and may sit unread for a while before the user taps
# one — generous, but still a bounded, revocable-by-rotating-SESSION_SECRET_KEY window, unlike the
# old scheme's "valid forever, no way to revoke short of changing the user's phone number" one.
WID_TOKEN_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


def generate_wid_token(phone_number: str) -> str:
    """Signed, time-limited token for a ?wid= link."""
    return _wid_serializer.dumps(phone_number)


def verify_wid_token(token: str) -> str | None:
    """Returns the phone number if `token` is a genuine, non-expired generate_wid_token() output;
    None on any failure (forged, tampered, expired, or — transitionally — an old bare phone number
    from a link generated before this fix that's still sitting unread in someone's WhatsApp)."""
    try:
        phone_number = _wid_serializer.loads(token, max_age=WID_TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return phone_number if isinstance(phone_number, str) else None
