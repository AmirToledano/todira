"""Tests for bot/handlers/support.py's looks_like_help_request — the detector that lets
onboarding.py and filter_conversation.py recognize a mid-conversation support request instead of
trying (and failing) to parse it as apartment criteria or a field value. escalate_to_owner itself
is already exercised via tests/test_contact_fallback.py, which calls it end-to-end through
handle_stray_message.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from handlers.support import looks_like_a_sentence, looks_like_help_request


def test_recognizes_hebrew_help_phrases():
    assert looks_like_help_request("אני רוצה לדבר עם נציג")
    assert looks_like_help_request("איך מקבלים תמיכה?")
    assert looks_like_help_request("יש לי תלונה")


def test_recognizes_english_help_phrases():
    assert looks_like_help_request("Hello where is the support")
    assert looks_like_help_request("I want to talk to the customer service")
    assert looks_like_help_request("can I speak to a human")


def test_does_not_flag_ordinary_apartment_criteria():
    assert not looks_like_help_request("מחפש דירת 3 חדרים בתל אביב עד 6000 שקל")
    assert not looks_like_help_request("Tel Aviv, 2 rooms, up to 6000")


def test_empty_text_is_not_a_help_request():
    assert not looks_like_help_request("")
    assert not looks_like_help_request(None)


def test_single_token_typo_is_not_a_sentence():
    assert not looks_like_a_sentence("500rf")
    assert not looks_like_a_sentence("3.5.2")
    assert not looks_like_a_sentence("")
    assert not looks_like_a_sentence(None)


def test_multi_word_text_is_a_sentence():
    assert looks_like_a_sentence("כמה זמן זה לוקח בדרך כלל")
    assert looks_like_a_sentence("why is this taking so long")
