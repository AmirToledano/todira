"""Cross-BROWSER-CONTEXT Google account linking (2026-09-05) — completes a pending Google sign-in
entirely server-side, the moment the visitor does /start with a matching token, instead of relying
on a session cookie surviving the round-trip through Telegram's own in-app browser. That in-app
browser is a SEPARATE cookie jar from whatever browser/app the visitor started the Google sign-in
in, so the earlier session-cookie-only approach (auth_google_callback stashing pending_google_sub,
_resolve_user completing it) silently never fires for that — the real bug behind repeated "I opened
the bot and tapped the link, it still shows unlinked" reports even when the visitor did everything
asked of them.

Consumers: website/main.py's auth_google_callback (generation, when a Google sign-in finds no
home) and bot/handlers/start.py (consumption, on a `t.me/<bot>?start=gl_xxxxx` deep link).
"""
from __future__ import annotations

import datetime as dt
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from dorin_common.models import PendingGoogleLink

TOKEN_PREFIX = "gl_"
_TOKEN_TTL = dt.timedelta(minutes=15)


def generate_google_link_token(session: Session, google_sub: str) -> str:
    """Stores `google_sub` server-side under a fresh, opaque, single-use token, valid for 15
    minutes — embedded in the bot deep-link shown on google_pending.html so ANY later /start, from
    ANY device or browser, can finish the link without needing to be the same browser context the
    OAuth callback itself ran in."""
    token = TOKEN_PREFIX + secrets.token_urlsafe(16)
    session.add(
        PendingGoogleLink(
            token=token,
            google_sub=google_sub,
            expires_at=dt.datetime.now(dt.timezone.utc) + _TOKEN_TTL,
        )
    )
    session.commit()
    return token


def resolve_google_link_token(session: Session, raw_text: str) -> str | None:
    """Looks up the pending google_sub for this token, if any, and consumes it (one-time use) so
    the same token can't be replayed. Returns None for anything that isn't a live, unexpired token
    — callers should fall through to normal /start handling, not treat it as an error."""
    token = raw_text.strip()
    if not token.startswith(TOKEN_PREFIX):
        return None
    pending = session.scalar(select(PendingGoogleLink).where(PendingGoogleLink.token == token))
    if pending is None:
        return None
    google_sub = pending.google_sub
    expired = pending.expires_at is None or dt.datetime.now(dt.timezone.utc) > pending.expires_at
    session.delete(pending)
    session.commit()
    return None if expired else google_sub
