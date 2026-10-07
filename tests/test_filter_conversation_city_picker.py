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
    message = SimpleNamespace(text=text, chat_id=999, reply_text=AsyncMock())
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
    markup = kb.city_picker_keyboard(draft, "he")
    buttons = [b for row in markup.inline_keyboard for b in row]
    haifa_button = next(b for b in buttons if "חיפה" in b.text)
    assert haifa_button.text.startswith("☑️")
    other_button = next(b for b in buttons if "רמת גן" in b.text)
    assert other_button.text.startswith("⬜")


def test_city_picker_keyboard_callback_data_indexes_into_cities():
    draft = _default_draft()
    markup = kb.city_picker_keyboard(draft, "he")
    buttons = [b for row in markup.inline_keyboard for b in row]
    tel_aviv_idx = CITIES.index("תל אביב יפו")
    tel_aviv_button = next(b for b in buttons if "תל אביב יפו" in b.text)
    assert tel_aviv_button.callback_data == f"f:loc:togc:{tel_aviv_idx}"


def test_city_search_results_keyboard_has_one_button_per_match_plus_back():
    matches = ["רמת גן", "רמת השרון"]
    markup = kb.city_search_results_keyboard(matches, "he")
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert len(buttons) == 3  # 2 matches + back
    ramat_gan_idx = CITIES.index("רמת גן")
    assert any(b.callback_data == f"f:loc:pickc:{ramat_gan_idx}" for b in buttons)


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


def test_typed_city_search_clears_the_previous_menu_messages_keyboard():
    # 2026-09-29 real owner report: typing an answer always sends a FRESH message for the next
    # menu screen (see _category_view's own docstring for why) — left unfixed, the PREVIOUS
    # screen's own inline keyboard just sits there, still live and tappable, and a second typed
    # search stacks yet another one on top, several large button grids deep. The previously
    # tracked message's keyboard must now be cleared before the new one is sent.
    update = _make_update("רמת")
    context = _make_context("city")
    context.user_data["menu_message_id"] = 4242
    context.bot = SimpleNamespace(edit_message_reply_markup=AsyncMock())

    asyncio.run(text_input(update, context))

    context.bot.edit_message_reply_markup.assert_awaited_once_with(
        chat_id=999, message_id=4242, reply_markup=None
    )
    # the tracked id now points at the FRESH message this search just sent, not the old one
    assert context.user_data["menu_message_id"] != 4242


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


def test_menu_callback_pickc_adds_city_and_returns_to_city_summary_not_checkbox_list():
    """2026-10-05 real owner report: typing a city and tapping the result opened the whole checkbox
    list instead of returning to the chosen-cities view."""
    idx = CITIES.index("מבשרת ציון")
    query = SimpleNamespace(
        data=f"f:loc:pickc:{idx}", answer=AsyncMock(), edit_message_text=AsyncMock()
    )
    update = SimpleNamespace(callback_query=query)
    context = _make_context(None)

    result = asyncio.run(filter_conversation.menu_callback(update, context))

    assert result == MENU
    assert context.user_data["draft"]["cities"] == ["מבשרת ציון"]
    _, kwargs = query.edit_message_text.call_args
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert any(b.callback_data == "f:loc:rmc:מבשרת ציון" for b in buttons)  # chosen-cities view
    assert not any(b.callback_data.startswith("f:loc:togc:") for b in buttons)  # not the big list


# 2026-09-15: real owner report — cities=[] already means "no city restriction at all" (matching.py
# skips the city hard-filter entirely when a filter's own cities list is empty, matching EVERY
# city/town, not just the 42 bundled ones), but the only way to add cities was one at a time, with
# no way back to that true "all" state short of removing every selection individually. The owner
# instead selected all 42 bundled cities by hand, believing that meant "all cities" — it doesn't:
# confirmed live, 1,153 of 3,794 active rent listings are in real towns (אריאל, חריש, נשר, ...) that
# aren't in the curated list at all, so selecting all 42 individually silently excludes them.


def test_location_keyboard_omits_clear_all_button_when_no_cities_selected():
    draft = _default_draft()
    markup = kb.location_keyboard(draft, "he")
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert not any(b.callback_data == "f:loc:clearall" for b in buttons)


def test_location_keyboard_shows_clear_all_button_when_cities_selected():
    draft = _default_draft()
    draft["cities"] = ["חיפה", "רמת גן"]
    markup = kb.location_keyboard(draft, "he")
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
    title, _ = filter_conversation._category_view(_default_draft(), "loc", "he")
    assert "כל הערים" in title


def test_loc_category_title_has_no_unconstrained_note_when_cities_selected():
    draft = _default_draft()
    draft["cities"] = ["חיפה"]
    title, _ = filter_conversation._category_view(draft, "loc", "he")
    assert "כל הערים" not in title


# --- rmc (remove-selected-city) real bug fix, 2026-09-25 — this used to encode the city's LIST
# INDEX, which goes stale the instant one city is removed (the list shifts). A real double-tap (or
# any tap racing a slow re-render) on the same rendered button sent the SAME stale index twice,
# silently removing whatever city had shifted into that position on the second tap — the wrong
# city. Now encodes the city's own name and removes by value, which is naturally idempotent. ---


def test_location_keyboard_rmc_callback_data_carries_the_city_name_not_an_index():
    draft = _default_draft()
    draft["cities"] = ["חיפה", "רמת גן"]
    markup = kb.location_keyboard(draft, "he")
    buttons = [b for row in markup.inline_keyboard for b in row]
    haifa_button = next(b for b in buttons if "חיפה" in b.text)
    assert haifa_button.callback_data == "f:loc:rmc:חיפה"


def test_menu_callback_rmc_removes_the_named_city():
    draft = _default_draft()
    draft["cities"] = ["חיפה", "רמת גן"]
    query = SimpleNamespace(
        data="f:loc:rmc:חיפה", answer=AsyncMock(), edit_message_text=AsyncMock()
    )
    update = SimpleNamespace(callback_query=query)
    context = _make_context(None, draft=draft)

    result = asyncio.run(filter_conversation.menu_callback(update, context))

    assert result == MENU
    assert context.user_data["draft"]["cities"] == ["רמת גן"]


def test_menu_callback_rmc_double_tap_never_removes_the_wrong_city():
    """The exact real bug this fixes: with the old index-based scheme, removing "חיפה" (index 0)
    shifted "רמת גן" into index 0 — a second, stale tap of the SAME rendered button (still index 0)
    then wrongly removed "רמת גן" too. Removing by name twice is a safe no-op the second time."""
    draft = _default_draft()
    draft["cities"] = ["חיפה", "רמת גן"]
    context = _make_context(None, draft=draft)

    first_tap = SimpleNamespace(
        data="f:loc:rmc:חיפה", answer=AsyncMock(), edit_message_text=AsyncMock()
    )
    asyncio.run(
        filter_conversation.menu_callback(SimpleNamespace(callback_query=first_tap), context)
    )
    assert context.user_data["draft"]["cities"] == ["רמת גן"]

    # A second, stale delivery of the exact same tap (data="...rmc:חיפה" again) — must be a no-op,
    # never removing "רמת גן".
    second_tap = SimpleNamespace(
        data="f:loc:rmc:חיפה", answer=AsyncMock(), edit_message_text=AsyncMock()
    )
    asyncio.run(
        filter_conversation.menu_callback(SimpleNamespace(callback_query=second_tap), context)
    )
    assert context.user_data["draft"]["cities"] == ["רמת גן"]


def test_city_picker_is_alphabetical_and_has_back_on_top_and_bottom():
    """2026-10-05 real owner report: the list was in an arbitrary order, and the only way out was a
    "back" button at the very bottom of a screen-high list."""
    markup = kb.city_picker_keyboard({"cities": ["חיפה", "אשדוד"]}, "he")
    rows = markup.inline_keyboard
    assert rows[0][0].callback_data == "f:cat:loc"  # back, first row
    assert rows[-1][0].callback_data == "f:cat:loc"  # back, last row
    city_buttons = [
        b for row in rows for b in row if b.callback_data.startswith("f:loc:togc:")
    ]
    names = [b.text.split(" ", 1)[1] for b in city_buttons]
    assert names == sorted(names)
    assert len(names) == len(CITIES)
    for b in city_buttons:  # sorting the display must not change what a tap selects
        assert CITIES[int(b.callback_data.rsplit(":", 1)[1])] == b.text.split(" ", 1)[1]


def test_location_keyboard_lists_chosen_cities_alphabetically():
    markup = kb.location_keyboard({"cities": ["חיפה", "אשדוד", "ירושלים"]}, "he")
    removals = [
        b.text for row in markup.inline_keyboard for b in row if b.callback_data.startswith("f:loc:rmc:")
    ]
    assert [t.split(": ", 1)[1] for t in removals] == ["אשדוד", "חיפה", "ירושלים"]


def test_selected_cities_say_remove_not_just_a_trash_icon():
    """2026-10-07 real owner report: the per-city button was a bare trash icon with no hint that tapping removes the city."""
    draft = _default_draft()
    draft["cities"] = ["הר גילה", "ירושלים"]
    markup = kb.location_keyboard(draft, "he")
    labels = {b.callback_data: b.text for row in markup.inline_keyboard for b in row}
    assert labels["f:loc:rmc:הר גילה"] == "❌ הסר: הר גילה"
    assert labels["f:loc:rmc:ירושלים"] == "❌ הסר: ירושלים"


def test_location_screen_explains_that_tapping_a_city_removes_it():
    draft = _default_draft()
    draft["cities"] = ["ירושלים"]
    title, _markup = filter_conversation._category_view(draft, "loc", "he")
    assert "לחיצה על עיר מסירה אותה" in title
    empty_title, _ = filter_conversation._category_view(_default_draft(), "loc", "he")
    assert "לחיצה על עיר מסירה אותה" not in empty_title
