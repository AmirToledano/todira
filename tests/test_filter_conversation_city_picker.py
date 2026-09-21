"""Tests for the button-driven city picker added 2026-09-02, replacing free-typing as the only
way to add a city in /filter. Two real reports drove this: (1) Telegram has no "live filter while
typing" input, so a full-list picker (mirrors "סוג נכס") is now the primary path; (2) typed search
used to silently add matches[0] - a real user asked for that "ניחוש אוטומטי" to go away, so a
search now shows every candidate as a tappable button instead.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import keyboards as kb
import handlers.filter_conversation as filter_conversation
from todira_common.cities import CITIES
from handlers.filter_conversation import MENU, _default_draft, _toggle_city, text_input


def _make_update(text: str):
    user = SimpleNamespace(id=555, first_name="Amir", username="amirt")
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    return SimpleNamespace(effective_user=user, message=message)


def _make_context(awaiting: str, draft: dict | None = None):
    return SimpleNamespace(
        user_data={"awaiting": awaiting, "draft": draft or _default_draft()},
    )


def test_toggle_city_adds_when_absent():
    draft = _default_draft()
    idx = CITIES.index("רמת גן")
    _toggle_city(draft, idx)
    assert draft["cities"] == ["רמת גן"]


def test_toggle_city_removes_when_present():
    draft = _default_draft()
    draft["cities"] = ["רמת גן", "חיפה"]
    _toggle_city(draft, CITIES.index("רמת גן"))
    assert draft["cities"] == ["חיפה"]


def test_city_picker_keyboard_marks_selected_cities():
    draft = _default_draft()
    draft["cities"] = ["חיפה"]
    markup = kb.city_picker_keyboard(draft)
    buttons = [b for row in markup.inline_keyboard for b in row]
    haifa_button = next(b for b in buttons if "חיפה" in b.text)
    assert haifa_button.text.startswith("☑️")
    other_button = next(b for b in buttons if "רמת גן" in b.text)
    assert other_button.text.startswith("⬜")


def test_city_picker_keyboard_callback_data_indexes_into_cities():
    draft = _default_draft()
    markup = kb.city_picker_keyboard(draft)
    buttons = [b for row in markup.inline_keyboard for b in row]
    tel_aviv_idx = CITIES.index("תל אביב יפו")
    tel_aviv_button = next(b for b in buttons if "תל אביב יפו" in b.text)
    assert tel_aviv_button.callback_data == f"f:loc:togc:{tel_aviv_idx}"


def test_city_search_results_keyboard_has_one_button_per_match_plus_back():
    matches = ["רמת גן", "רמת השרון"]
    markup = kb.city_search_results_keyboard(matches)
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert len(buttons) == 3  # 2 matches + back
    ramat_gan_idx = CITIES.index("רמת גן")
    assert any(b.callback_data == f"f:loc:togc:{ramat_gan_idx}" for b in buttons)


def test_typed_city_search_shows_button_results_not_auto_add():
    # the real bug report this fixes: typing a city used to silently add matches[0] to the
    # filter - it must now just show candidates, leaving draft["cities"] untouched until the
    # user actually taps one.
    update = _make_update("רמת")
    context = _make_context("city")

    result = asyncio.run(text_input(update, context))

    assert result == MENU
    assert context.user_data["draft"]["cities"] == []
    update.message.reply_text.assert_awaited_once()
    _, kwargs = update.message.reply_text.call_args
    markup = kwargs["reply_markup"]
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert any("רמת גן" in b.text for b in buttons)


def test_menu_callback_full_shows_locpick_category():
    query = SimpleNamespace(data="f:loc:full", answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(callback_query=query)
    context = _make_context(None)

    result = asyncio.run(filter_conversation.menu_callback(update, context))

    assert result == MENU
    query.edit_message_text.assert_awaited_once()
    _, kwargs = query.edit_message_text.call_args
    assert kwargs["reply_markup"].inline_keyboard  # a real keyboard was rendered


def test_menu_callback_togc_toggles_and_stays_on_locpick():
    idx = CITIES.index("חיפה")
    query = SimpleNamespace(
        data=f"f:loc:togc:{idx}", answer=AsyncMock(), edit_message_text=AsyncMock()
    )
    update = SimpleNamespace(callback_query=query)
    context = _make_context(None)

    result = asyncio.run(filter_conversation.menu_callback(update, context))

    assert result == MENU
    assert context.user_data["draft"]["cities"] == ["חיפה"]
    _, kwargs = query.edit_message_text.call_args
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    haifa_button = next(b for b in buttons if "חיפה" in b.text)
    assert haifa_button.text.startswith("☑️")  # still on the picker, now checked


# 2026-09-15: real owner report — cities=[] already means "no city restriction at all" (matching.py
# skips the city hard-filter entirely when a filter's own cities list is empty, matching EVERY
# city/town, not just the 42 bundled ones), but the only way to add cities was one at a time, with
# no way back to that true "all" state short of removing every selection individually. The owner
# instead selected all 42 bundled cities by hand, believing that meant "all cities" — it doesn't:
# confirmed live, 1,153 of 3,794 active rent listings are in real towns (אריאל, חריש, נשר, ...) that
# aren't in the curated list at all, so selecting all 42 individually silently excludes them.


def test_location_keyboard_omits_clear_all_button_when_no_cities_selected():
    draft = _default_draft()
    markup = kb.location_keyboard(draft)
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert not any(b.callback_data == "f:loc:clearall" for b in buttons)


def test_location_keyboard_shows_clear_all_button_when_cities_selected():
    draft = _default_draft()
    draft["cities"] = ["חיפה", "רמת גן"]
    markup = kb.location_keyboard(draft)
    buttons = [b for row in markup.inline_keyboard for b in row]
    clear_all = next(b for b in buttons if b.callback_data == "f:loc:clearall")
    assert "כל הערים" in clear_all.text


def test_menu_callback_clearall_empties_cities_and_returns_to_loc():
    query = SimpleNamespace(
        data="f:loc:clearall", answer=AsyncMock(), edit_message_text=AsyncMock()
    )
    update = SimpleNamespace(callback_query=query)
    draft = _default_draft()
    draft["cities"] = list(CITIES)  # the exact real-world state that triggered this report
    context = _make_context(None, draft=draft)

    result = asyncio.run(filter_conversation.menu_callback(update, context))

    assert result == MENU
    assert context.user_data["draft"]["cities"] == []
    title = query.edit_message_text.call_args[0][0]
    assert "כל הערים" in title


def test_loc_category_title_notes_unconstrained_state_when_empty():
    title, _ = filter_conversation._category_view(_default_draft(), "loc")
    assert "כל הערים" in title


def test_loc_category_title_has_no_unconstrained_note_when_cities_selected():
    draft = _default_draft()
    draft["cities"] = ["חיפה"]
    title, _ = filter_conversation._category_view(draft, "loc")
    assert "כל הערים" not in title
