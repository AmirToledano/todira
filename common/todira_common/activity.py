"""How much people really use the bot and the site, day by day - counts only.

2026-10-21 (owner: "I want to know, when I ask, whether there was activity"): free-text messages to the bot and visits
to the site were not recorded anywhere. One row per (Israel day, kind, person) with a hit count; never the text of a
message, the page, an IP address or a name. A person is "t<telegram id>" in the bot, "u<user id>" on the site when
signed in, and otherwise "v" plus a hash of the address and browser that changes every day, so an anonymous visitor
can't be followed from one day to the next. Read with .github/workflows/diagnose-user-activity.yaml.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert

from todira_common.db import get_session
from todira_common.models import ActivityDay

logger = logging.getLogger(__name__)

BOT_MESSAGE = "bot_message"
BOT_BUTTON = "bot_button"
SITE_VISIT = "site_visit"
_ISRAEL = ZoneInfo("Asia/Jerusalem")


def today() -> dt.date:
    return dt.datetime.now(_ISRAEL).date()


def visitor_key(address: str, user_agent: str, secret: str, day: dt.date) -> str:
    """An anonymous visitor for one day only: the same address and browser on the same day count once."""
    digest = hashlib.sha256(f"{secret}|{day.isoformat()}|{address}|{user_agent}".encode()).hexdigest()
    return "v" + digest[:16]


def record(kind: str, who: str, day: dt.date | None = None) -> None:
    """Counts one hit. Never raises: a counting problem must never break the bot or a page."""
    try:
        with get_session() as session:
            statement = insert(ActivityDay).values(day=day or today(), kind=kind, who=who, hits=1)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=["day", "kind", "who"], set_={"hits": ActivityDay.hits + 1}
                )
            )
            session.commit()
    except Exception:
        logger.warning("Could not record %s activity", kind, exc_info=True)
