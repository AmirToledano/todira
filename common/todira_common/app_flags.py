"""Small persistent key/value switches shared by every pod (the app_flags table, models.AppFlag): the scraper's
one-time seeding markers and cursors."""
from __future__ import annotations

from sqlalchemy.orm import Session

from todira_common.models import AppFlag


def get_flag(session: Session, key: str) -> str | None:
    row = session.get(AppFlag, key)
    return None if row is None else row.value


def set_flag(session: Session, key: str, value: str) -> None:
    row = session.get(AppFlag, key)
    if row is None:
        session.add(AppFlag(key=key, value=value))
    else:
        row.value = value
    session.commit()
