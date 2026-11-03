"""People asking in the Facebook groups for a flat, sent to the owner as they are found (2026-11-03, owner: "find posts
of people looking for a flat and send me straight away, with a direct link, so I can answer them about Todira").

The groups feed already reads every post the dedicated account sees and set the "looking for a flat" ones aside
(facebook_groups_text_parser.looks_like_seeker). Each one new to us, written in the last MAX_AGE, goes to the owner's
leads group (todira_common/owner_inbox.py), or his usual inbox until he has one: the place and what they ask for as the
post says it, a short quote and a link to the post. The owner answers by hand; nothing is ever posted to Facebook from
here. Each post is sent once: the ids sent are kept in app_flags. The poster's name is not sent and nothing about a post
is logged.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import logging
import os

import httpx

from todira_common import owner_inbox
from todira_common.app_flags import get_flag, set_flag
from todira_common.db import get_session

logger = logging.getLogger(__name__)

MAX_AGE = dt.timedelta(hours=48)
MAX_PER_RUN = 25  # a first run, or a busy hour, does not flood the group
QUOTE_CHARS = 350
KEEP_IDS = 3000
_FLAG = "seeker_leads_sent"
_GROUPS_BASE = "https://www.facebook.com/groups/"


def post_url(post: dict) -> str:
    return f"{_GROUPS_BASE}{post['group_id']}/posts/{post['post_id']}/"


def fresh(post: dict, now: dt.datetime) -> bool:
    created = post.get("creation_time")
    if not isinstance(created, int):
        return True  # no time on it: the feed shows recent posts, so treat it as new
    return now - dt.datetime.fromtimestamp(created, tz=dt.timezone.utc) <= MAX_AGE


def message(post: dict, place: str | None, deal: str | None) -> str:
    text = " ".join(post["text"].split())
    quote = text if len(text) <= QUOTE_CHARS else text[:QUOTE_CHARS].rsplit(" ", 1)[0] + "..."
    head = "מחפשים דירה"
    if deal == "sale":
        head = "מחפשים לקנות דירה"
    elif deal == "sublet":
        head = "מחפשים סאבלט"
    if place:
        head += f" ב{place}"
    return (
        f"<b>{html.escape(head)}</b>\n\n"
        f"{html.escape(quote)}\n\n"
        f'<a href="{html.escape(post_url(post))}">לפוסט בפייסבוק</a>\n\n'
        f"תגובה מוכנה (לחיצה מעתיקה):\n<code>{html.escape(reply_text(post, place, deal))}</code>"
    )


# 2026-11-03: a ready reply the owner copies into the comments. A few wordings, picked by the post, so his comments
# are not the same text again and again (Facebook treats repeated identical comments as spam). The link is the site
# with ?src=fblead, so visits from these replies are counted (website/main.py, _ActivityMiddleware).
REPLY_LINK = "https://todira.app/?src=fblead"
_REPLIES = (
    "היי, אם עוד לא מצאת: טודירה סורקת את כל אתרי הדירות וקבוצות הפייסבוק ושולחת לך בטלגרם כל דירה חדשה{where} "
    "שמתאימה לחיפוש שלך, ברגע שהיא עולה. יש תקופת ניסיון בחינם: {link}",
    "בהצלחה בחיפוש! טיפ: טודירה שולחת התראה בטלגרם על כל דירה חדשה{where} שמתאימה למה שביקשת, "
    "מכל האתרים והקבוצות. אפשר לנסות בחינם: {link}",
    "אם מתיש לעבור על כל האתרים והקבוצות כל יום, טודירה עושה את זה בשבילך ושולחת לטלגרם רק דירות{where} "
    "שמתאימות לך, מיד כשהן עולות. ניסיון בחינם: {link}",
)


def reply_text(post: dict, place: str | None, deal: str | None) -> str:
    where = (" למכירה" if deal == "sale" else "") + (f" ב{place}" if place else "")
    wording = _REPLIES[sum(map(ord, post["post_id"])) % len(_REPLIES)]
    return wording.format(where=where, link=REPLY_LINK)


def _chats() -> list[str]:
    leads = owner_inbox.leads_chat_id()
    if leads:
        return [leads]
    return owner_inbox.owner_chat_ids(os.environ.get("OWNER_TELEGRAM_USER_ID"))


def _send(token: str, chats: list[str], text: str) -> bool:
    for chat_id in chats:
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=10.0,
            )
        except httpx.HTTPError:
            continue
        if resp.status_code == 200:
            return True
    return False


def send_leads(posts: list[dict], describe, now: dt.datetime | None = None) -> int:
    """Sends the seekers among `posts` (already picked by the caller) not sent before. `describe(post)` gives
    (place, deal) for it. Returns how many went out. Never raises."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or not posts:
        return 0
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        with get_session() as session:
            sent_ids: list[str] = json.loads(get_flag(session, _FLAG) or "[]")
            done = set(sent_ids)
            new = [p for p in posts if p["post_id"] not in done and fresh(p, now)][:MAX_PER_RUN]
            if not new:
                return 0
            chats = _chats()
            count = 0
            for post in new:
                try:
                    place, deal = describe(post)
                except Exception:
                    place, deal = None, None
                if _send(token, chats, message(post, place, deal)):
                    sent_ids.append(post["post_id"])
                    count += 1
            set_flag(session, _FLAG, json.dumps(sent_ids[-KEEP_IDS:]))
    except Exception:
        logger.exception("seeker leads: sending failed")
        return 0
    logger.info("seeker leads: %d sent to the owner", count)
    return count
