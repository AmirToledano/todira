"""Shared "get or create the DB User row for this Telegram user" helper — used by handlers that
just need the row to exist, without the extra reactivation/username-refresh logic /start's own
handler does on top of this (see bot/handlers/start.py)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from todira_common.language import normalize_language_code
from todira_common.models import User


def get_or_create_user(session: Session, tg_user) -> User:
    user = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
    if user is not None:
        return user
    # 2026-09-26: Telegram gives us the user's own device language for free on every update
    # (telegram.User.language_code) — auto-detect silently at creation time rather than asking. Only
    # normalized to one of our 5 supported languages; an unrecognized/regional code (or none at
    # all) leaves this None, same as it already was before this column existed — every read site
    # treats None as todira_common.language.DEFAULT_LANG.
    user = User(
        telegram_user_id=tg_user.id,
        telegram_username=tg_user.username,
        first_name=tg_user.first_name,
        language=normalize_language_code(getattr(tg_user, "language_code", None)),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        # 2026-09-25 real bug fix, found via a live code-review pass: a plain SELECT-then-INSERT
        # race — a real one here, not hypothetical, since two concurrent updates for the same user
        # can genuinely run this function twice before either commit lands. Whichever request loses the unique
        # constraint on telegram_user_id used to bubble up as an unhandled exception and silently
        # drop that entire message/update — the same real incident class as the Google
        # account-creation race already fixed in website/main.py's auth_google_create_account.
        session.rollback()
        existing = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
        if existing is None:
            raise
        return existing
    return user
