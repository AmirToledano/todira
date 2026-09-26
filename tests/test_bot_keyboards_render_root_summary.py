"""Tests for keyboards.render_root_summary's HTML-escaping of free-text keywords.

Found live-code-review 2026-09-22: every other field render_root_summary shows comes from a
controlled source (enum labels, the fixed CITIES list) — keywords is genuine free user text
(typed directly, or Gemini-extracted from free text; see onboarding.py/filter_conversation.py),
and this summary is always sent to Telegram with parse_mode=ParseMode.HTML. An unescaped "<"/"&"
in a keyword makes Telegram's HTML parser reject the whole message outright — and since this
same render is what /filter always shows first, that made /filter permanently unusable for that
user until the DB row was fixed manually. Same escaping already used everywhere else user text
meets parse_mode=HTML in this project (todira_common/cards.py, handlers/support.py).
"""
from __future__ import annotations

import keyboards as kb
from handlers.filter_conversation import _default_draft


def test_render_root_summary_escapes_html_special_chars_in_keywords():
    draft = _default_draft()
    draft["keywords"] = ["AC & heating", "<3 חדרים"]

    text = kb.render_root_summary(draft, "he")

    assert "AC &amp; heating" in text
    assert "&lt;3 חדרים" in text
    # The raw, unescaped forms must never appear — that's exactly what breaks Telegram's HTML parser.
    assert "AC & heating" not in text
    assert "<3 חדרים" not in text


def test_render_root_summary_shows_dash_for_no_keywords():
    draft = _default_draft()
    draft["keywords"] = []

    text = kb.render_root_summary(draft, "he")

    assert "🔍 מילות מפתח: —" in text
