"""Cross-channel account linking — a short `ref_xxxxxx` code that attaches a NEW channel
(WhatsApp phone number, Telegram user id) to an EXISTING user, matching the reference product's
own confirmed UX: the website generates a code for an already-logged-in user, who then sends it
FROM the channel they want to add (a plain WhatsApp text message, or opens it as a Telegram
`/start` deep-link payload — `t.me/<bot>?start=ref_xxxxxx`).

Consumers: website/main.py's /account (generation) and bot/handlers/start.py +
website/whatsapp_webhook.py (consumption, one each per channel).
"""
from __future__ import annotations

import datetime as dt
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from dorin_common.models import User

CODE_PREFIX = "ref_"
_CODE_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_CODE_LENGTH = 6
_CODE_TTL = dt.timedelta(minutes=15)


def generate_link_code(session: Session, user: User) -> str:
    """(Re)generates a link code for `user`, valid for 15 minutes. Safe to call repeatedly — e.g.
    the user reopens the linking page after the previous code expired — each call just replaces
    whatever code was there before."""
    code = CODE_PREFIX + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
    user.channel_link_code = code
    user.channel_link_code_expires_at = dt.datetime.now(dt.timezone.utc) + _CODE_TTL
    session.commit()
    return code


def resolve_link_code(session: Session, raw_text: str) -> User | None:
    """Looks up the user waiting on this code, if any, and consumes it (one-time use) so the same
    code can't be replayed. Returns None for anything that isn't a live, unexpired code — callers
    should treat that as "not a link code" and fall through to their normal per-channel handling,
    NOT as an error."""
    code = raw_text.strip().lower()
    if not code.startswith(CODE_PREFIX):
        return None
    user = session.scalar(select(User).where(User.channel_link_code == code))
    if user is None:
        return None
    if (
        user.channel_link_code_expires_at is None
        or dt.datetime.now(dt.timezone.utc) > user.channel_link_code_expires_at
    ):
        return None
    user.channel_link_code = None
    user.channel_link_code_expires_at = None
    session.commit()
    return user
