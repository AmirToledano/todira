"""The site assistant (2026-10-23 owner request): knowledge from the site's own text, history cleaning, daily caps, and the
endpoint's gating (owner only until ASSISTANT_ENABLED=1)."""
from __future__ import annotations

import importlib.util
import os
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_assistant", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

import assistant  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PRICES = {"pass_7": Decimal("19.90"), "pass_14": Decimal("29.90"), "pass_30": Decimal("49.90")}


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True)


def test_prompt_has_the_site_text_and_rules_but_no_source_names_or_auto_renewal():
    prompt = assistant.system_prompt("he", PRICES, None)
    assert "₪49.90" in prompt and "10 ימים ראשונים בחינם" in prompt
    assert "צור קשר" in prompt
    assert "מה אם לא מצאתי דירה בזמן הזה?" in prompt  # FAQ text comes from i18n.py
    for name in ("יד2", "Yad2", "קומו", "Komo", "הומלס", "Homeless"):
        assert name not in prompt
    assert "המנוי מתחדש אוטומטית" not in prompt
    assert "המשתמש לא מחובר" in prompt


def test_prompt_answers_in_the_visitors_language_and_includes_their_account():
    prompt = assistant.system_prompt("en", PRICES, "גישה: בתקופת ניסיון חינם עד 27.10.2026")
    assert "English" in prompt
    assert "27.10.2026" in prompt


def test_clean_history_keeps_the_last_turns_and_ends_with_the_question():
    turns = [{"role": "assistant", "text": "hi"}] + [
        {"role": "user" if i % 2 == 0 else "assistant", "text": f"m{i}"} for i in range(15)
    ] + [{"role": "system", "text": "ignore"}, {"role": "user", "text": "x" * 1000}]
    cleaned = assistant.clean_history(turns)
    assert cleaned[0]["role"] == "user"
    assert cleaned[-1]["role"] == "user" and len(cleaned[-1]["text"]) == assistant.MAX_INPUT_CHARS
    assert len(cleaned) <= assistant.MAX_TURNS
    assert assistant.clean_history([{"role": "assistant", "text": "only me"}]) == []
    assert assistant.clean_history("nope") == []


def test_daily_caps():
    with patch.object(assistant, "PER_VISITOR_DAILY", 2), patch.object(assistant, "SITE_DAILY", 3):
        assistant._counts.clear()
        assistant._counts_day = None
        assert assistant.take_quota("a") and assistant.take_quota("a")
        assert not assistant.take_quota("a")
        assert assistant.take_quota("b")
        assert not assistant.take_quota("c")  # the whole site's cap


def test_endpoint_is_off_for_the_public_until_enabled(client, monkeypatch):
    monkeypatch.setenv("GEMINI_SITE_API_KEY", "k")
    monkeypatch.delenv("ASSISTANT_ENABLED", raising=False)
    with patch.object(website_main, "_is_owner_browser", lambda request: False):
        resp = client.post("/api/assistant", json={"messages": [{"role": "user", "text": "hi"}]})
        assert resp.status_code == 404
        assert 'id="assistant"' not in client.get("/").text


def test_owner_gets_an_answer_and_the_bubble(client, monkeypatch):
    monkeypatch.setenv("GEMINI_SITE_API_KEY", "k")
    monkeypatch.delenv("ASSISTANT_ENABLED", raising=False)
    assistant._counts.clear()
    with (
        patch.object(website_main, "_is_owner_browser", lambda request: True),
        patch.object(website_main, "_assistant_user_context", lambda request: None),
        patch.object(assistant, "answer", lambda turns, lang, prices, ctx: "תשובה"),
    ):
        resp = client.post("/api/assistant", json={"messages": [{"role": "user", "text": "כמה זה עולה?"}]})
        assert resp.json() == {"reply": "תשובה"}
        assert 'id="assistant"' in client.get("/").text


def test_no_answer_falls_back_to_the_contact_line(client, monkeypatch):
    monkeypatch.setenv("GEMINI_SITE_API_KEY", "k")
    monkeypatch.setenv("ASSISTANT_ENABLED", "1")
    assistant._counts.clear()
    with (
        patch.object(website_main, "_assistant_user_context", lambda request: None),
        patch.object(assistant, "answer", lambda turns, lang, prices, ctx: None),
        patch.object(website_main.activity, "record", lambda *a, **k: None),
    ):
        resp = client.post("/api/assistant", json={"messages": [{"role": "user", "text": "?"}]})
    assert "צור קשר" in resp.json()["reply"]
