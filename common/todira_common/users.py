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
    # (telegram.User.language_code) — auto-detect silently at creation time rather than asking,
    # unlike WhatsApp (get_or_create_whatsapp_user below), which has no such signal at all. Only
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
        # race — a real one here, not hypothetical, since website/whatsapp_webhook.py's own
        # BackgroundTasks (and any other concurrent delivery for the same user) can genuinely run
        # this function twice before either commit lands. Whichever request loses the unique
        # constraint on telegram_user_id used to bubble up as an unhandled exception and silently
        # drop that entire message/update — the same real incident class as the Google
        # account-creation race already fixed in website/main.py's auth_google_create_account.
        session.rollback()
        existing = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
        if existing is None:
            raise
        return existing
    return user


def get_or_create_whatsapp_user(
    session: Session, phone_number: str, first_name: str | None = None
) -> User:
    """`phone_number` is WhatsApp's own `wa_id` (E.164 digits, no leading '+') from the webhook
    payload's `messages[].from` field — stable per WhatsApp account, used the same way
    telegram_user_id identifies a Telegram user."""
    user = session.scalar(select(User).where(User.whatsapp_phone_number == phone_number))
    if user is not None:
        return user
    user = User(whatsapp_phone_number=phone_number, first_name=first_name)
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        # See get_or_create_user's own comment — the identical race, on WhatsApp's own unique
        # phone-number column: a new WhatsApp user's first two messages can arrive as genuinely
        # concurrent webhook deliveries, and losing this race used to silently swallow the whole
        # message instead of just resolving to the row the winning request already created.
        session.rollback()
        existing = session.scalar(select(User).where(User.whatsapp_phone_number == phone_number))
        if existing is None:
            raise
        return existing
    return user
