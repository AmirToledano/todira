"""Gemini-backed free-text onboarding parser.

The user describes what they're looking for in their own words (one messy paragraph, or several
back-and-forth turns) — mirrors the reference bot's WhatsApp onboarding rather than a rigid
step-by-step Q&A. Each turn, `parse_onboarding_message` is handed the raw text plus whatever
fields onboarding.py already collected in earlier turns, and returns the merged, updated state
plus a natural-language reply (either a clarifying question for whatever's still missing, or a
confirmation once deal_type + at least one city are known).

Fails soft: if GEMINI_API_KEY isn't set, or the API call/parse fails for any reason,
`parse_onboarding_message` returns None — onboarding.py shows a "technical hiccup, try again"
message and stays in the same state rather than crashing or silently losing the user's answer.
"""
from __future__ import annotations

import json
import os

from google import genai
from google.genai import types

_MODEL = "gemini-2.0-flash"

_client: genai.Client | None = None
_client_checked = False

_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "deal_type": {"type": "STRING", "enum": ["rent", "sale", "sublet", "unknown"]},
        "cities": {"type": "ARRAY", "items": {"type": "STRING"}},
        "rooms_min": {"type": "NUMBER"},
        "rooms_max": {"type": "NUMBER"},
        "price_max": {"type": "NUMBER"},
        "keywords": {"type": "ARRAY", "items": {"type": "STRING"}},
        "missing_required": {"type": "ARRAY", "items": {"type": "STRING", "enum": ["deal_type", "cities"]}},
        "response_message": {"type": "STRING"},
    },
    "required": ["deal_type", "cities", "missing_required", "response_message"],
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
        "אתה עוזר בבוט טלגרם ישראלי שמוצא דירות למגורים. המשתמש מתאר בשפה חופשית מה הוא מחפש "
        "(יכול לכלול שגיאות כתיב, קיצורים כמו 'ראשל\"צ'/'ב\"ש', וניסוח לא מסודר) — תפקידך לחלץ "
        "מהטקסט שדות מובנים ולמזג אותם עם מה שכבר ידוע מתשובות קודמות של אותו משתמש.\n\n"
        f"מה שכבר ידוע מתשובות קודמות (JSON): {json.dumps(known_state, ensure_ascii=False)}\n\n"
        f"רשימת הערים התקפות היחידה שהמערכת מכירה: {known_cities}\n"
        "cities חייב להכיל אך ורק ערים מהרשימה הזו, בכתיב המדויק שלהן. אל תמציא ערים שלא ברשימה.\n\n"
        f"ההודעה החדשה מהמשתמש: {text!r}\n\n"
        "החזר את המצב המלא והמעודכן (משלב את הידוע כבר עם מה שנלמד מההודעה החדשה — אל תאבד מידע "
        "קודם אם ההודעה החדשה לא סתרה אותו). deal_type ו-cities (לפחות עיר אחת) הם שדות חובה; "
        "rooms_min/rooms_max/price_max/keywords הם רשות (השאר ריק/None אם לא ידוע). "
        "ב-missing_required פרט אילו מבין deal_type/cities עדיין לא ידועים.\n"
        "ב-response_message כתוב תגובה טבעית וידידותית בעברית: אם עדיין חסר מידע חובה, שאל שאלה "
        "ממוקדת רק על מה שחסר (אל תשאל שוב על מה שכבר ידוע); אם כל החובה ידוע, כתוב אישור קצר וחם "
        "שמסכם את מה שהבנת."
    )

    try:
        response = client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_SCHEMA,
            ),
        )
        result = json.loads(response.text)
    except Exception:
        return None

    result["cities"] = [c for c in (result.get("cities") or []) if c in known_cities]
    if result.get("deal_type") not in ("rent", "sale", "sublet"):
        result["deal_type"] = None
    return result
