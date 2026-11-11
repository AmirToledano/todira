"""Answering "דירה" under our own Facebook Page and Instagram posts with the link, at once (2026-11-11, owner: "whoever
comments 'דירה', my bot answers him straight away with the link, I don't go and answer").

Meta calls website/main.py's /meta/webhook for every new comment on our Page or Instagram posts. A comment that asks
for the link (asks_for_link) gets one public reply under it (reply_text): a short, varied wording with the link, and
the city when the comment names one ("אני חולון"). Each comment is answered once (app_flags keeps the ids). Our own
comments are never answered. Only comments on our own posts reach here; nothing is ever posted anywhere else.
"""
from __future__ import annotations

import re

from todira_common import cities
from todira_common.app_flags import get_flag, set_flag

_FLAG = "social_replied_comments"
KEEP_IDS = 5000
SITE_LINK = "https://todira.app/?src={source}"

# "דירה" as the post asks, and the other ways people ask for it
_ASK_RE = re.compile(
    r"(?<![א-ת])(?:ו|ה|ב)?(?:דירה|דירות|דירהה+|לינק|קישור|מעוניין|מעוניינת|מעוניינים|אשמח|פרטים|רוצה|רוצים)(?![א-ת])"
    r"|^\s*אני(?![א-ת])"
)

_OPENERS = ("בשמחה!", "הנה,", "בכיף!", "היי,", "בטח!")
_BODIES = (
    "כאן מגדירים מה מחפשים, וכל דירה חדשה{where} שמתאימה מגיעה אליך לטלגרם:",
    "טודירה תשלח לך כל דירה חדשה{where} שמתאימה לחיפוש שלך, ברגע שהיא עולה:",
    "מגדירים עיר, מחיר וחדרים, ומקבלים התראה על כל דירה חדשה{where}:",
    "זה הקישור, עם ניסיון בחינם. כל דירה חדשה{where} שמתאימה תגיע אליך:",
)


def asks_for_link(text: str | None) -> bool:
    return bool(_ASK_RE.search(text or ""))


def city_in(text: str | None) -> str | None:
    """The locality a comment names ("אני חולון", "דירה בבת ים"), or None."""
    words = re.findall(r"[א-ת\"'׳״\-]+", text or "")
    for size in (3, 2, 1):
        for start in range(len(words) - size + 1):
            phrase = " ".join(words[start:start + size])
            for candidate in (phrase, phrase[1:] if phrase[:1] in "בל" and len(phrase) > 3 else None):
                found = cities.resolve_locality(candidate) if candidate else None
                if found:
                    return found
    return None


def reply_text(comment_id: str, text: str | None, source: str) -> str:
    """The public reply: a short opener, one sentence (with the city when named) and the link, picked by the comment
    so the same words don't repeat under one post."""
    place = city_in(text)
    seed = sum((i + 1) * ord(ch) for i, ch in enumerate(str(comment_id)))
    opener = _OPENERS[seed % len(_OPENERS)]
    body = _BODIES[(seed // len(_OPENERS)) % len(_BODIES)].format(where=f" ב{place}" if place else "")
    return f"{opener} {body} {SITE_LINK.format(source=source)}"


def already_answered(session, comment_id: str) -> bool:
    return comment_id in (get_flag(session, _FLAG) or "").split(",")


def mark_answered(session, comment_id: str) -> None:
    ids = [i for i in (get_flag(session, _FLAG) or "").split(",") if i]
    ids.append(comment_id)
    set_flag(session, _FLAG, ",".join(ids[-KEEP_IDS:]))
