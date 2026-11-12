"""People asking in the Facebook groups for a flat, sent to the owner as they are found (2026-11-03, owner: "find posts
of people looking for a flat and send me straight away, with a direct link, so I can answer them about Todira").

The groups feed already reads every post the dedicated account sees and set the "looking for a flat" ones aside
(facebook_groups_text_parser.looks_like_seeker). Each one new to us, written in the last MAX_AGE, goes to the owner's
leads group (todira_common/owner_inbox.py), or his usual inbox until he has one: the place and what they ask for as the
post says it, a short quote and a link to the post. The owner answers by hand; nothing is ever posted to Facebook from
here. Each post is sent once: the ids sent are kept in app_flags. The poster's name is not sent and nothing about a post
is logged.

2026-11-04 (owner: "find leads properly, read the whole post, not only the words, and send me many more"): every new
post with a looking-for word anywhere in it (CANDIDATE_RE, wider than the listing rule) is read whole by a small
language model (Gemini flash-lite, the free key the scraper already has) that answers whether the writer is looking
for a home, what kind and where. Only a "yes" is sent. Each post is decided once (sent or not, kept in app_flags), at
most MAX_AI_PER_RUN a run. Without the model (no key, quota, error) the old rule decides, as before.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import logging
import os

import re
import time

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
_CHECKED_FLAG = "seeker_leads_checked"
KEEP_CHECKED = 6000
MAX_AI_PER_RUN = 20
_AI_SPACING_SECONDS = 2.0
_AI_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
_AI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Wider than facebook_groups_text_parser._SEEKER_RE: a looking-for word anywhere, near a home word or a question to
# the group ("מישהו מכיר", "יש למישהו"). The model then reads the whole post.
CANDIDATE_RE = re.compile(
    r"(?<![א-ת])(?:ו|ש|וש|כש|ה)?(?:מחפש|מחפשת|מחפשים|מחפשות|דרוש|דרושה|דרושים|צריך|צריכה|צריכים|מעוניין|מעוניינת|מעוניינים|"
    r"מישהו\s+מכיר|מישהי\s+מכירה|מכירים|יש\s+למישהו|יש\s+למישהי)(?![א-ת])"
    r"[^\n]{0,80}?(?<![א-ת])(?:דירה|דירת|דירות|חדר|יחידה|יחידת|סאבלט|סבלט|בית|להשכרה|לשכירות|לקנות|לרכוש|מגורים)"
)
_AI_PROMPT = (
    "You read one post from an Israeli Facebook apartments group (usually Hebrew). Decide if the WRITER is personally "
    "looking for a home to rent, buy, sublet or a room for themselves (or their family). An ad offering a flat, a room "
    "or a service is NOT, even if it asks a question like 'מחפשים דירה?'; someone offering their room and looking for a "
    "roommate or replacement is NOT; an agent advertising is NOT. Answer only JSON: "
    '{"looking": true|false, "deal": "rent"|"sale"|"sublet"|"room"|"unknown", "place": "<city or area in Hebrew, or empty>"}'
)
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


def is_candidate(text: str) -> bool:
    return bool(text) and bool(CANDIDATE_RE.search(text[:1500]))


def ai_verdict(text: str) -> dict | None:
    """{"looking", "deal", "place"} from the model, or None when it could not answer (no key, quota, error)."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    body = {
        "contents": [{"parts": [{"text": f"{_AI_PROMPT}\n\nPOST:\n{text[:2500]}"}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    for model in _AI_MODELS:
        try:
            resp = httpx.post(_AI_URL.format(model=model), headers={"x-goog-api-key": key}, json=body, timeout=20.0)
        except httpx.HTTPError:
            continue
        if resp.status_code != 200:
            continue
        try:
            answer = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            verdict = json.loads(answer)
        except (KeyError, IndexError, ValueError, TypeError):
            continue
        if isinstance(verdict, dict) and isinstance(verdict.get("looking"), bool):
            return verdict
    return None


def pick_leads(posts: list[dict], rule, checked: set[str], now: dt.datetime) -> tuple[list[tuple[dict, dict]], list[str]]:
    """([(post, verdict)], ids decided "not looking"). `rule(text)` is the old seeker rule, used when the model cannot
    answer. A lead counts as decided only once it was sent (send_leads), so a failed send is tried again."""
    leads: list[tuple[dict, dict]] = []
    decided: list[str] = []
    asked = 0
    use_ai = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    for post in posts:
        if post["post_id"] in checked or not fresh(post, now) or not is_candidate(post.get("text") or ""):
            continue
        verdict = None
        if use_ai and asked < MAX_AI_PER_RUN:
            if asked:
                time.sleep(_AI_SPACING_SECONDS)
            asked += 1
            verdict = ai_verdict(post["text"])
        if verdict is None:
            if use_ai and asked >= MAX_AI_PER_RUN:
                continue  # decided on a later run, when the model has room again
            verdict = {"looking": bool(rule(post["text"])), "deal": "unknown", "place": "", "by": "rule"}
        if verdict.get("looking"):
            leads.append((post, verdict))
        else:
            decided.append(post["post_id"])
    return leads, decided


_DEALS = {"rent": None, "room": None, "unknown": None, "sale": "sale", "sublet": "sublet"}


def send_leads(posts: list[dict], describe, now: dt.datetime | None = None, rule=None) -> int:
    """Sends the people looking for a home among `posts` (all the run's new posts) not decided before.
    `describe(post)` gives (place, deal) from the text and the group; the model's place and deal win when it has them.
    Returns how many went out. Never raises."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or not posts:
        return 0
    now = now or dt.datetime.now(dt.timezone.utc)
    rule = rule or (lambda text: True)
    try:
        with get_session() as session:
            sent_ids: list[str] = json.loads(get_flag(session, _FLAG) or "[]")
            checked_ids: list[str] = json.loads(get_flag(session, _CHECKED_FLAG) or "[]")
            checked = set(sent_ids) | set(checked_ids)
            leads, decided = pick_leads(posts, rule, checked, now)
            chats = _chats() if leads else []
            count = 0
            for post, verdict in leads[:MAX_PER_RUN]:
                try:
                    place, deal = describe(post)
                except Exception:
                    place, deal = None, None
                place = (verdict.get("place") or "").strip() or place
                deal = _DEALS.get(verdict.get("deal"), deal) if verdict.get("by") != "rule" else deal
                if _send(token, chats, message(post, place, deal)):
                    sent_ids.append(post["post_id"])
                    decided.append(post["post_id"])
                    count += 1
            set_flag(session, _FLAG, json.dumps(sent_ids[-KEEP_IDS:]))
            set_flag(session, _CHECKED_FLAG, json.dumps((checked_ids + decided)[-KEEP_CHECKED:]))
    except Exception:
        logger.exception("seeker leads: sending failed")
        return 0
    logger.info("seeker leads: %d sent to the owner, %d posts decided this run", count, len(decided))
    return count
