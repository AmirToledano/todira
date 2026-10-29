"""2026-10-27 (plan item 2): the one question for a search with more than 30 new apartments a day."""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from handlers.many_matches import FEATURES, MANY_PER_DAY, pick_question, question_markup  # noqa: E402

from todira_common.bot_strings import bot_text  # noqa: E402


def _rows(n, **values):
    base = {"has_balcony": None, "has_parking": None, "has_elevator": None}
    return [SimpleNamespace(**{**base, **values}) for _ in range(n)]


_NO_SWITCHES = SimpleNamespace(require_balcony=False, require_parking=False, require_elevator=False)


def test_no_question_for_a_normal_search():
    assert pick_question(_rows(MANY_PER_DAY * 7, has_balcony=True), 7, _NO_SWITCHES) is None


def test_asks_about_the_feature_that_narrows_most_and_shows_what_would_remain():
    rows = _rows(63, has_balcony=True, has_parking=True) + _rows(287, has_balcony=False, has_parking=True)  # 50 a day
    feature, after = pick_question(rows, 7, _NO_SWITCHES)
    assert (feature, after) == ("balcony", 9)
    assert bot_text("many.q_balcony", "he", n=after) == "זה הרבה 🙂 רק 9 מהן עם מרפסת. מרפסת זה חובה?"


def test_a_mostly_unknown_feature_is_never_offered():
    rows = _rows(20, has_balcony=True) + _rows(280, has_balcony=None)
    assert pick_question(rows, 7, _NO_SWITCHES) is None


def test_a_feature_already_required_is_not_asked_again():
    rows = _rows(63, has_balcony=True) + _rows(287, has_balcony=False)
    switches = SimpleNamespace(require_balcony=True, require_parking=False, require_elevator=False)
    assert pick_question(rows, 7, switches) is None


def test_every_feature_has_its_question_and_buttons_in_every_language():
    for name, _, _ in FEATURES:
        for lang in ("he", "en", "ru", "fr", "ar"):
            assert "{n}" not in bot_text(f"many.q_{name}", lang, n=5)
            markup = question_markup(name, lang)
            assert [b.callback_data for row in markup.inline_keyboard for b in row] == [f"mm:{name}", "mm:no"]


def test_no_question_for_a_flexible_search():
    rows = _rows(63, has_balcony=True) + _rows(287, has_balcony=False)
    flexible = SimpleNamespace(require_balcony=False, require_parking=False, require_elevator=False, flexible_match=True)
    assert pick_question(rows, 7, flexible) is None
