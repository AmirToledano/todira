"""2026-10-29 (bot review): the bot's number prompts took only bare digits - "5000 ש"ח", "4,500" and "8 אלף" were
refused, and the longer ones even went to the owner as support messages."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from handlers.filter_conversation import _parse_optional_int  # noqa: E402


@pytest.mark.parametrize(("raw", "value"), [
    ("4500", 4500), ("4,500", 4500), ("8 אלף", 8000), ("5000 ש\"ח", 5000), ("₪6000", 6000), ("-", None), ("", None),
])
def test_number_answers_people_actually_type(raw, value):
    assert _parse_optional_int(raw) == (True, value)


@pytest.mark.parametrize("raw", ["abc", "3.5", "שלוש"])
def test_not_a_whole_number(raw):
    assert _parse_optional_int(raw) == (False, None)
