"""Shared "get or create the DB User row for this Telegram user" helper — used by handlers that
just need the row to exist, without the extra reactivation/username-refresh logic /start's own
handler does on top of this (see bot/handlers/start.py)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from dorin_common.models import User


def get_or_create_user(session: Session, tg_user) -> User:
    user = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
    if user is None:
        user = User(
            telegram_user_id=tg_user.id,
            telegram_username=tg_user.username,
            first_name=tg_user.first_name,
        )
        session.add(user)
        session.commit()
    return user
