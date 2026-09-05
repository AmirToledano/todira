"""Gemini-backed free-text onboarding parser — channel-agnostic, shared by the Telegram bot
(bot/handlers/onboarding.py) and the WhatsApp webhook (website/whatsapp_webhook.py). Lives in
dorin_common (not bot/) precisely so both can import it identically; moved here 2026-09-01 when
the WhatsApp integration was added — was bot/gemini_client.py before that, Telegram-only.

The user describes what they're looking for in their own words (one messy paragraph, or several
back-and-forth turns) — mirrors the reference bot's WhatsApp onboarding rather than a rigid
step-by-step Q&A. Each turn, `parse_onboarding_message` is handed the raw text plus whatever
fields the caller already collected in earlier turns, and returns the merged, updated state
plus a natural-language reply (either a clarifying question for whatever's still missing, or a
confirmation once deal_type + at least one city are known).

Fails soft: if GEMINI_API_KEY isn't set, or the API call/parse fails for any reason,
`parse_onboarding_message` returns None — callers show a "technical hiccup, try again" message
and stay in the same state rather than crashing or silently losing the user's answer.
"""
from __future__ import annotations

import json
import logging
import os
import time

import requests
from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.6-flash"

# 2026-09-06: real production logs (pulled via the diagnose-website-webhook workflow after the
# owner reported 2 of 3 live WhatsApp messages getting the "technical hiccup" fallback) showed the
# 10s-timeout fix above working exactly as intended — one attempt per message, no more duplicates
# — but a chunk of those single attempts hitting a genuine `google.genai.errors.ServerError: 503
# UNAVAILABLE ... This model is currently experiencing high demand` straight from Gemini itself.
# Google's own error message calls these spikes "usually temporary," which is exactly the case a
# single retry is for. A SECOND round of live logs (same day, next report) showed a different
# failure shape hitting this same "still get the hiccup" complaint: a plain
# `requests.exceptions.ReadTimeout` — Gemini just not answering within the 10s budget at all, no
# error response, nothing to do with the SDK's own retry policy. Both are retried the same way:
# `requests` is imported directly (not relying on it as google-genai's undeclared transitive
# dependency — matches this project's own existing convention, see bot/requirements.txt's httpx
# comment) specifically so `requests.exceptions.Timeout` can be caught by name instead of guessed
# at. Retrying was NOT safe before the ack-first webhook fix (website/whatsapp_webhook.py) shipped
# earlier today — back then, every extra second here just made Meta's own webhook redelivery race
# more likely. Now that Meta is acked before this function is ever called, one bounded retry only
# affects how long the (already-backgrounded) reply takes to arrive, never whether Meta
# double-processes the message. Scoped tight — a malformed-response or bad-request error still
# fails immediately, since retrying those would just fail identically a second time.
_MAX_ATTEMPTS = 2
_RETRY_DELAY_SECONDS = 1.0
_RETRYABLE_ERRORS = (errors.ServerError, requests.exceptions.Timeout)

_client: genai.Client | None = None
_client_checked = False

_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "deal_type": {"type": "STRING", "enum": ["rent", "sale", "sublet", "unknown"]},
        "cities": {"type": "ARRAY", "items": {"type": "STRING"}},
        "rooms_min": {"type": "NUMBER"},
        "rooms_max": {"type": "NUMBER"},
        "price_min": {"type": "NUMBER"},
        "price_max": {"type": "NUMBER"},
        "keywords": {"type": "ARRAY", "items": {"type": "STRING"}},
        "missing_required": {"type": "ARRAY", "items": {"type": "STRING", "enum": ["deal_type", "cities"]}},
        "response_message": {"type": "STRING"},
        "needs_human_help": {"type": "BOOLEAN"},
    },
    "required": ["deal_type", "cities", "missing_required", "response_message", "needs_human_help"],
}


def _get_client() -> genai.Client | None:
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        _client = genai.Client(api_key=api_key)
    return _client


def parse_onboarding_message(text: str, known_state: dict, known_cities: list[str]) -> dict | None:
    client = _get_client()
    if client is None:
        return None

    prompt = (
        "אתה עוזר בצ'אט ישראלי שמוצא דירות למגורים. המשתמש מתאר בשפה חופשית מה הוא מחפש "
        "(יכול לכלול שגיאות כתיב, קיצורים כמו 'ראשל\"צ'/'ב\"ש', וניסוח לא מסודר) — תפקידך לחלץ "
        "מהטקסט שדות מובנים ולמזג אותם עם מה שכבר ידוע מתשובות קודמות של אותו משתמש.\n\n"
        f"מה שכבר ידוע מתשובות קודמות (JSON): {json.dumps(known_state, ensure_ascii=False)}\n\n"
        f"רשימת הערים התקפות היחידה שהמערכת מכירה: {known_cities}\n"
        "cities חייב להכיל אך ורק ערים מהרשימה הזו, בכתיב המדויק שלהן. אל תמציא ערים שלא ברשימה.\n\n"
        f"ההודעה החדשה מהמשתמש: {text!r}\n\n"
        "החזר את המצב המלא והמעודכן (משלב את הידוע כבר עם מה שנלמד מההודעה החדשה — אל תאבד מידע "
        "קודם אם ההודעה החדשה לא סתרה אותו). deal_type ו-cities (לפחות עיר אחת) הם שדות חובה; "
        "rooms_min/rooms_max/price_min/price_max/keywords הם רשות (השאר ריק/None אם לא ידוע). "
        "אם המשתמש נתן טווח מחירים (למשל 'בין 3200 ל-8700' או '3200-8700') — price_min הוא הערך "
        "הנמוך ו-price_max הוא הגבוה. אם ניתן רק מספר אחד/תקרה (למשל 'עד 6000') — רק price_max. "
        "ב-missing_required פרט אילו מבין deal_type/cities עדיין לא ידועים.\n"
        "ב-response_message כתוב תגובה טבעית וידידותית בעברית: אם עדיין חסר מידע חובה, שאל שאלה "
        "ממוקדת רק על מה שחסר (אל תשאל שוב על מה שכבר ידוע); אם כל החובה ידוע, כתוב אישור קצר וחם "
        "שמסכם את מה שהבנת.\n\n"
        "needs_human_help: החזר true אם ההודעה החדשה עצמה לא מתארת קריטריון חיפוש דירה כלשהו — "
        "למשל שאלה כללית שלא קשורה לחיפוש, תלונה, בקשה לדבר עם בן אדם/נציג/תמיכה, בלבול, או כל "
        "דבר אחר שלא נועד לענות על מה שביקשת. אם ההודעה כן מכילה מידע רלוונטי (גם אם חלקי, וגם אם "
        "יש בה גם שאלה נוספת בצד) — false."
    )

    response = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_SCHEMA,
                    # 2026-09-05 fix: found live via the WhatsApp webhook — a real onboarding
                    # reply took ~1 minute (WhatsApp users perceive that as "the bot is broken").
                    # Root cause confirmed from the SDK's own field docs: HttpOptions.retry_options
                    # defaults to up to 5 attempts on 408/429/5xx with exponential backoff up to a
                    # 60s max delay — exactly what a Gemini "high demand" 503 triggers — and this
                    # call never overrode it, so it silently applied. This isn't a bug in our code,
                    # just an unsuitable default for a synchronous chat reply the user is actively
                    # waiting on. types.HttpRetryOptions isn't constructible directly in the
                    # installed SDK version (not exported / rejects a plain dict here), so bounding
                    # just the per-call timeout is the safe fix available: a real outage now fails
                    # within ~10s and falls through to the existing "technical hiccup, try again"
                    # message (below) instead of leaving the user staring at an unanswered chat for
                    # up to a minute. Revisit if a future SDK version exposes retry tuning cleanly.
                    http_options=types.HttpOptions(timeout=10_000),
                ),
            )
            break
        except _RETRYABLE_ERRORS as exc:
            if attempt < _MAX_ATTEMPTS:
                logger.warning(
                    "Gemini call failed (attempt %d/%d), retrying once: %s",
                    attempt,
                    _MAX_ATTEMPTS,
                    exc,
                )
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            logger.exception("Gemini onboarding parse failed (retry budget exhausted)")
            return None
        except Exception:
            logger.exception("Gemini onboarding parse failed")
            return None

    try:
        result = json.loads(response.text)
    except Exception:
        logger.exception("Gemini onboarding parse failed")
        return None

    result["cities"] = [c for c in (result.get("cities") or []) if c in known_cities]
    if result.get("deal_type") not in ("rent", "sale", "sublet"):
        result["deal_type"] = None
    return result
