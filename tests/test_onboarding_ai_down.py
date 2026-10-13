"""2026-10-13 owner report: Gemini's prepaid balance ran out (HTTP 402 on every model) and every new user who sent /start
and described the search got only "technical hiccup". Onboarding now reads the message with free rules first
(todira_common/search_text.py), asks for whatever is missing with buttons, and uses the AI only as an optional helper
behind a per-user daily limit and a pause after failures (bot/ai_gate.py)."""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import ai_gate
import handlers.onboarding as onboarding
from telegram.ext import ConversationHandler
from todira_common.bot_strings import bot_text


@pytest.fixture(autouse=True)
def _fresh_gate(monkeypatch):
    ai_gate.reset()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    yield
    ai_gate.reset()


def _update(text: str):
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=555, first_name="A", username=None),
        effective_chat=SimpleNamespace(id=555),
        message=message,
        effective_message=message,
        callback_query=None,
    )


def _context(**user_data):
    return SimpleNamespace(
        user_data={"onboarding_lang": "he", "onboarding": dict(onboarding._EMPTY_STATE), **user_data},
        bot=SimpleNamespace(send_chat_action=AsyncMock(), send_message=AsyncMock()),
    )


def _no_ai(*args, **kwargs):
    raise AssertionError("the AI must not be called")


def _run(update, context, ai=_no_ai, saved=None):
    saved = saved if saved is not None else []

    def _save(tg_user, state):
        saved.append(dict(state))
        return 3

    with (
        patch.object(onboarding.gemini_client, "parse_onboarding_message", side_effect=ai),
        patch.object(onboarding, "_save_filter_sync", _save),
        patch.object(onboarding, "signed_login_query", lambda uid: "t=x"),
    ):
        return asyncio.run(onboarding._handle_freetext(update, context)), saved


def _texts(update):
    return [c.args[0] for c in update.message.reply_text.await_args_list]


def test_a_complete_message_is_saved_by_the_rules_alone_without_any_ai_call():
    update = _update("מחפש שכירות בתל אביב, 3 חדרים, עד 8,500 ש\"ח עם מרפסת")
    result, saved = _run(update, _context())
    assert result == ConversationHandler.END
    assert saved[0]["deal_type"] == "rent" and saved[0]["cities"] == ["תל אביב יפו"]
    assert saved[0]["price_max"] == 8500 and saved[0]["rooms_min"] == 3 and saved[0]["keywords"] == ["מרפסת"]
    assert _texts(update)[0] == "🔎 החיפוש שלך פעיל: שכירות · תל אביב יפו · 3–3.5 חדרים · עד ₪8,500 · מרפסת"


def test_a_missing_deal_type_is_asked_with_buttons_when_the_ai_is_unavailable():
    update = _update("אני רוצה דירת 5 חדרים בירושלים")
    context = _context()
    result, saved = _run(update, context)
    assert result == onboarding.AWAIT_FREETEXT and not saved
    call = update.message.reply_text.await_args_list[-1]
    assert "הבנתי: ירושלים · 5–5.5 חדרים." in call.args[0] and bot_text("onboarding.ask_deal", "he") in call.args[0]
    buttons = [b.callback_data for row in call.kwargs["reply_markup"].inline_keyboard for b in row]
    assert buttons == ["ob:deal:rent", "ob:deal:sale", "ob:deal:sublet"]
    assert context.user_data["onboarding"]["cities"] == ["ירושלים"]


def test_tapping_a_deal_button_completes_and_saves():
    context = _context()
    context.user_data["onboarding"]["cities"] = ["ירושלים"]
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(data="ob:deal:sale", answer=AsyncMock(), edit_message_reply_markup=AsyncMock(), message=message)
    update = SimpleNamespace(
        callback_query=query, effective_message=message, effective_user=SimpleNamespace(id=555)
    )
    saved = []
    with (
        patch.object(onboarding, "_save_filter_sync", lambda u, s: saved.append(dict(s)) or 0),
        patch.object(onboarding, "signed_login_query", lambda uid: "t=x"),
    ):
        result = asyncio.run(onboarding._handle_button(update, context))
    assert result == ConversationHandler.END and saved[0]["deal_type"] == "sale"


def test_after_asking_for_a_city_a_bare_city_word_is_accepted():
    context = _context(onboarding_asked="city")
    context.user_data["onboarding"]["deal_type"] = "rent"
    result, saved = _run(_update("מגדל"), context)
    assert result == ConversationHandler.END and saved[0]["cities"] == ["מגדל"]


def test_a_misspelled_city_gets_suggestion_buttons():
    context = _context(onboarding_asked="city")
    context.user_data["onboarding"]["deal_type"] = "rent"
    update = _update("רמת גם")
    result, _ = _run(update, context)
    call = update.message.reply_text.await_args_list[-1]
    assert result == onboarding.AWAIT_FREETEXT and call.args[0] == bot_text("onboarding.city_suggest", "he")
    first = call.kwargs["reply_markup"].inline_keyboard[0][0]
    assert first.text == "רמת גן"


def test_a_failed_ai_call_pauses_the_ai_and_still_asks_for_what_is_missing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    update = _update("משהו לא ברור לגמרי")
    result, _ = _run(update, _context(), ai=lambda *a, **k: None)
    assert result == onboarding.AWAIT_FREETEXT
    assert bot_text("onboarding.ask_deal", "he") in _texts(update)[-1]
    # paused: the next message doesn't wait on the AI again
    result, _ = _run(_update("עוד משהו"), _context())
    assert result == onboarding.AWAIT_FREETEXT


def test_each_user_gets_a_limited_number_of_ai_calls_a_day(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    user_data = {}
    for _ in range(ai_gate.DAILY_LIMIT):
        assert ai_gate.allowed(user_data)
        ai_gate.used(user_data)
    assert not ai_gate.allowed(user_data)


def test_the_promo_reels_own_message_is_understood_and_saved_without_any_question():
    # the exact message the user types in the Instagram reel (promo/reel/content.json "userMsg"): no deal word, so the
    # budget settles it - and the reply matches the reel's "🔎 החיפוש שלך פעיל"
    update = _update("היי, אני מחפש דירה בתל אביב עם 3+ חדרים. התקציב שלי עד 8,500₪ ואשמח שתהיה גם מרפסת.")
    result, saved = _run(update, _context())
    assert result == ConversationHandler.END
    assert _texts(update)[0] == "🔎 החיפוש שלך פעיל: שכירות · תל אביב יפו · 3+ חדרים · עד ₪8,500 · מרפסת"
    assert saved[0]["deal_type"] == "rent" and saved[0]["rooms_min"] == 3 and saved[0]["rooms_max"] is None


def test_a_purchase_budget_means_buying():
    update = _update("דירה ברמת גן עד 2.5 מיליון")
    _, saved = _run(update, _context())
    assert saved[0]["deal_type"] == "sale"
