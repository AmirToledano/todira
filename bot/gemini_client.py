"""Gemini-backed fallback parsing for onboarding free-text answers.

Only called when the cheap keyword/regex parse in onboarding.py already came up empty — this
keeps API usage (and the free-tier rate limit) low while fixing exactly the failure mode found by
manual testing: typos ("שגירות" instead of "שכירות"), abbreviations ("ראשל\"צ"), and misspellings
("רמת גם" instead of "רמת גן") that plain substring matching can't catch.

Fails soft everywhere: if GEMINI_API_KEY isn't set, or the API call/parse fails for any reason,
every function here returns None/[] so onboarding.py falls back to its existing "לא הצלחתי להבין"
retry prompt instead of crashing.
"""
from __future__ import annotations

import json
import os

from google import genai
from google.genai import types

_MODEL = "gemini-2.0-flash"

_client: genai.Client | None = None
_client_checked = False


def _get_client() -> genai.Client | None:
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        _client = genai.Client(api_key=api_key)
    return _client


def _generate_json(prompt: str, schema: dict) -> dict | None:
    client = _get_client()
    if client is None:
        return None
    try:
        response = client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        return json.loads(response.text)
    except Exception:
        return None


def parse_deal_type(text: str) -> str | None:
    schema = {
        "type": "OBJECT",
        "properties": {"deal_type": {"type": "STRING", "enum": ["rent", "sale", "sublet", "unknown"]}},
        "required": ["deal_type"],
    }
    prompt = (
        "משתמש עונה בבוט טלגרם ישראלי לחיפוש דירות על השאלה 'מה את/ה מחפש/ת - שכירות, מכירה או "
        "סבלט?'. גם אם יש שגיאת כתיב או ניסוח לא סטנדרטי, תבין את הכוונה ותחזיר rent (שכירות), "
        "sale (מכירה) או sublet (סבלט). אם באמת לא ברור, תחזיר unknown.\n"
        f"תשובת המשתמש: {text!r}"
    )
    result = _generate_json(prompt, schema)
    value = (result or {}).get("deal_type")
    return value if value in ("rent", "sale", "sublet") else None


def parse_cities(text: str, known_cities: list[str]) -> list[str]:
    schema = {
        "type": "OBJECT",
        "properties": {"cities": {"type": "ARRAY", "items": {"type": "STRING"}}},
        "required": ["cities"],
    }
    prompt = (
        "משתמש כתב שמות ערים/יישובים בישראל בבוט חיפוש דירות, יכול לכלול שגיאות כתיב, קיצורים "
        "(כמו 'ראשל\"צ' או 'ב\"ש') או ניסוחים לא מדויקים. הרשימה הבאה היא רשימת הערים התקפות "
        "היחידה שהמערכת מכירה - תחזיר אך ורק ערים מהרשימה הזו שמתאימות לכוונת המשתמש, בכתיב "
        "המדויק שלהן כפי שמופיע ברשימה. אל תמציא ערים שלא נמצאות ברשימה.\n"
        f"רשימת ערים תקפות: {known_cities}\n"
        f"טקסט המשתמש: {text!r}"
    )
    result = _generate_json(prompt, schema)
    matched = (result or {}).get("cities") or []
    return [c for c in matched if c in known_cities]


def parse_rooms(text: str) -> tuple[float, float] | None:
    schema = {
        "type": "OBJECT",
        "properties": {"rooms_min": {"type": "NUMBER"}, "rooms_max": {"type": "NUMBER"}},
        "required": ["rooms_min", "rooms_max"],
    }
    prompt = (
        "משתמש עונה כמה חדרים הוא מחפש בדירה - יכול להיות מספר בודד, טווח, או ניסוח חופשי "
        "(כולל חצאי חדרים כמו 2.5). תחזיר rooms_min ו-rooms_max; אם זה מספר בודד, שניהם שווים.\n"
        f"תשובת המשתמש: {text!r}"
    )
    result = _generate_json(prompt, schema)
    if not result or "rooms_min" not in result or "rooms_max" not in result:
        return None
    return float(result["rooms_min"]), float(result["rooms_max"])
