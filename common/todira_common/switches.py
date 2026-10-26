"""On/off switches the owner flips from the site's admin dashboard (website /admin), stored in app_flags as
"switch:<name>" = "1"/"0" (2026-10-26, owner: "so I can control things too, not only you"). A switch never set from the
dashboard keeps the default its caller passes (usually the old environment setting), so nothing changes until he
flips it. Read at most every 30 seconds per process; a database problem returns the default rather than failing."""
from __future__ import annotations

import logging
import threading
import time

from todira_common.app_flags import get_flag, set_flag
from todira_common.db import get_session

logger = logging.getLogger(__name__)

# name -> (Hebrew label, what it does) for the dashboard, in display order
SWITCHES: dict[str, tuple[str, str]] = {
    "assistant": ("העוזר באתר", "בועת הצ׳אט עם ה-AI בכל דפי האתר"),
    "share_button": ("כפתור שיתוף בבוט", "״📤 שיתוף הדירה״ מתחת לכל דירה שנשלחת"),
    "voice": ("הודעות קוליות בבוט", "הבוט מבין הקלטות כמו טקסט"),
    "facebook": ("סריקת פייסבוק", "קריאת דירות מקבוצות פייסבוק (אפשר לעצור אם החשבון בסיכון)"),
}
_TTL = 30.0
_cache: dict[str, tuple[float, str | None]] = {}
_lock = threading.Lock()


def _key(name: str) -> str:
    return f"switch:{name}"


def is_on(name: str, default: bool) -> bool:
    now = time.monotonic()
    with _lock:
        hit = _cache.get(name)
    if hit is None or now - hit[0] > _TTL:
        try:
            with get_session() as session:
                value = get_flag(session, _key(name))
        except Exception:
            logger.warning("could not read switch %s", name, exc_info=True)
            return default
        with _lock:
            _cache[name] = (now, value)
    else:
        value = hit[1]
    if value in ("1", "0"):
        return value == "1"
    return default


def set_switch(session, name: str, on: bool) -> None:
    if name not in SWITCHES:
        raise ValueError(name)
    set_flag(session, _key(name), "1" if on else "0")
    with _lock:
        _cache.pop(name, None)
