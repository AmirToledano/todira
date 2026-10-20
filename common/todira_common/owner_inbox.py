"""Where messages for the owner go.

2026-10-20 (owner): his private chat with the bot is muted, because that is where every apartment alert for his own
search lands, so messages from people got lost in it. Messages people send (the site's contact form and feedback,
help requests in the bot) and payment alerts now go to a private Telegram group he made for them, once he has added
the bot to it: bot/handlers/owner_inbox.py saves that group's id here (the app_flags table). Apartment alerts stay in
the private chat. Until there is a group, or when sending to it fails, everything goes to the private chat as before.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from todira_common.app_flags import get_flag, set_flag
from todira_common.db import get_session

logger = logging.getLogger(__name__)

INBOX_FLAG = "owner_inbox_chat_id"
_CACHE_SECONDS = 60
_cache: dict = {"at": float("-inf"), "value": None}


def inbox_chat_id(fresh: bool = False) -> str | None:
    """The group's chat id, or None. Read from the database at most once a minute per process, unless `fresh`."""
    now = time.monotonic()
    if not fresh and now - _cache["at"] < _CACHE_SECONDS:
        return _cache["value"]
    try:
        with get_session() as session:
            value = get_flag(session, INBOX_FLAG) or None
    except Exception:
        logger.warning("Could not read the owner's inbox group; using the private chat", exc_info=True)
        value = None
    _cache.update(at=now, value=value)
    return value


def set_inbox_chat_id(session: Session, chat_id: int | str | None) -> None:
    set_flag(session, INBOX_FLAG, "" if chat_id is None else str(chat_id))
    _cache.update(at=float("-inf"), value=None)


def owner_chat_ids(owner_private_chat_id: str | None) -> list[str]:
    """The chats to try for a message to the owner, in order: the inbox group, then his private chat."""
    chats = []
    inbox = inbox_chat_id()
    if inbox:
        chats.append(inbox)
    if owner_private_chat_id and str(owner_private_chat_id) not in chats:
        chats.append(str(owner_private_chat_id))
    return chats
