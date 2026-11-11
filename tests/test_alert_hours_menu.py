"""2026-10-31: the bot menu for choosing the hours and days alerts come in (handlers/alert_hours_menu.py)."""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import keyboards as kb  # noqa: E402
from handlers import alert_hours_menu as menu  # noqa: E402

from todira_common.bot_strings import bot_text  # noqa: E402


def _update(data):
    query = SimpleNamespace(
        data=data, answer=AsyncMock(), edit_message_text=AsyncMock(), edit_message_reply_markup=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=555))


def _buttons(markup):
    return [(button.text, button.callback_data) for row in markup.inline_keyboard for button in row]


def test_the_filter_menu_has_the_hours_button():
    assert (bot_text("hours.filter_button", "he"), "hours:menu") in _buttons(kb.root_keyboard("he"))


def test_the_menu_shows_the_default_hours_every_day():
    text, markup = menu._menu("he", "08:30", "23:00", True, False)
    assert text == (
        "⏰ <b>שעות התראות</b>\n\n"
        "כרגע, ברירת המחדל של שליחת מודעות אליכם היא כל יום בין השעות 08:30 עד 23:00.\n\n"
        "שוכרים מעלים דירות גם מחוץ לשעות שליחת המודעות, אז מודעות שעלו מחוץ לשעות השליחה יישלחו בבוקר שלמחרת.\n\n"
        "אם אתם לא רוצים לקבל מודעות בסופ״ש, לחצו על „📅 גם בשישי ושבת” והמודעות יגיעו רק מראשון עד חמישי."
    )
    assert _buttons(markup) == [
        ("🕘 לשנות שעות", "hours:from"), ("📅 גם בשישי ושבת: כן", "hours:wk"), ("✔️ סיום", "hours:done"),
    ]


def test_custom_hours_without_the_weekend():
    text, markup = menu._menu("he", "09:00", "20:00", False, True)
    assert "כרגע, המודעות נשלחות אליכם מראשון עד חמישי בין השעות 09:00 עד 20:00." in text
    assert "יישלחו כשהשעות שלכם מתחילות" in text
    assert "בסופ״ש" not in text  # the weekend is already off
    assert ("↩️ כל השעות", "hours:all") in _buttons(markup)
    assert ("📅 גם בשישי ושבת: לא", "hours:wk") in _buttons(markup)


def test_menu_opens_as_a_new_message():
    update = _update("hours:menu")
    with patch.object(menu, "_apply_sync", return_value=("he", "08:30", "23:00", True, False)):
        asyncio.run(menu._answer(update, SimpleNamespace()))
    update.callback_query.message.reply_text.assert_awaited_once()
    update.callback_query.edit_message_text.assert_not_called()


def test_choosing_the_first_hour_offers_only_later_last_hours():
    update = _update("hours:f:16")
    with patch.object(menu, "_apply_sync", return_value=("he", "08:30", "23:00", True, False)):
        asyncio.run(menu._answer(update, SimpleNamespace()))
    args, kwargs = update.callback_query.edit_message_text.await_args
    assert args[0] == "ועד איזו שעה?"
    assert _buttons(kwargs["reply_markup"]) == [
        ("18:00", "hours:t:16:18"), ("20:00", "hours:t:16:20"), ("21:00", "hours:t:16:21"),
        ("22:00", "hours:t:16:22"), ("23:00", "hours:t:16:23"),
    ]


def test_saving_hours_passes_both_and_shows_the_menu_again():
    update = _update("hours:t:9:20")
    with patch.object(menu, "_apply_sync", return_value=("he", "09:00", "20:00", True, True)) as apply:
        asyncio.run(menu._answer(update, SimpleNamespace()))
    apply.assert_called_once_with(555, "t", ["9", "20"])
    assert "בין השעות 09:00 עד 20:00" in update.callback_query.edit_message_text.await_args.args[0]


def test_a_forged_pair_is_not_saved():
    user = SimpleNamespace(alert_from_hour=None, alert_to_hour=None, alerts_on_weekend=True, language="he")
    session = SimpleNamespace(scalar=lambda q: user, commit=lambda: None)

    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    with patch.object(menu, "get_session", _Ctx):
        menu._apply_sync(555, "t", ["20", "9"])
        menu._apply_sync(555, "t", ["3", "23"])
        assert (user.alert_from_hour, user.alert_to_hour) == (None, None)
        menu._apply_sync(555, "t", ["9", "20"])
        assert (user.alert_from_hour, user.alert_to_hour) == (9, 20)
        menu._apply_sync(555, "wk", [])
        assert user.alerts_on_weekend is False
        menu._apply_sync(555, "all", [])
        assert (user.alert_from_hour, user.alert_to_hour) == (None, None)


def test_the_approved_onboarding_line():
    assert bot_text("hours.onboarding", "he") == (
        "⏰ ההתראות מגיעות כל יום בין 08:30 ל־23:00, מיד כשדירה עולה. ככה לא מפספסים אף דירה. "
        "אפשר לבחור שעות אחרות, או בלי שישי ושבת:"
    )


# --- 2026-11-09 (owner: easier filter buttons, and "save and search" got stuck) ---


def test_filter_menu_fits_a_phone_and_marks_what_was_changed():
    from todira_common.schemas import FilterData

    draft = FilterData().model_dump()
    rows = kb.root_keyboard("he", draft).inline_keyboard
    assert len(rows) <= 8  # was 9; 2026-11-10: one more row for "neighbourhoods and streets"
    assert [b.callback_data for b in rows[0]] == ["f:cat:loc", "f:cat:price", "f:cat:rooms"]
    assert rows[-2][0].callback_data == "f:save" and len(rows[-2]) == 1
    assert not any("✏️" in b.text for row in rows for b in row)
    draft.update(cities=["חיפה"], price_max=5000, require_parking=True)
    marked = {b.callback_data for row in kb.root_keyboard("he", draft).inline_keyboard for b in row if "✏️" in b.text}
    assert marked == {"f:cat:loc", "f:cat:price", "f:cat:req"}
    # long labels (Russian) stay two to a row instead of being cut off
    assert all(len(row) <= 2 for row in kb.root_keyboard("ru", draft).inline_keyboard)


def test_filter_summary_has_no_long_dashes():
    from todira_common.schemas import FilterData

    for lang in ("he", "en", "ru"):
        summary = kb.render_root_summary(FilterData().model_dump(), lang)
        assert "—" not in summary and "–" not in summary


# --- 2026-11-10 (owner): neighbourhoods and streets in /filter ---


def test_filter_menu_has_a_neighbourhoods_and_streets_screen():
    from handlers import filter_conversation as fc
    from todira_common.schemas import FilterData

    draft = FilterData().model_dump()
    assert (bot_text("kb.title.hood", "he"), "f:cat:hood") in _buttons(kb.root_keyboard("he", draft))
    title, markup = fc._category_view(draft, "hood", "he")
    assert "הרבה מודעות לא מציינות" in title and "—" not in title and "–" not in title
    assert {data for _text, data in _buttons(markup)} == {"f:hood:nb", "f:hood:st", "f:hood:clear", "f:root"}
    draft.update(neighborhoods_include=["רחביה", "<b>"], streets_include=["הרצל"])
    title, _markup = fc._category_view(draft, "hood", "he")
    assert "רחביה, &lt;b&gt;" in title and "הרצל" in title and "<b>" not in title.replace("<b>הסינון", "")
    marked = {b.callback_data for row in kb.root_keyboard("he", draft).inline_keyboard for b in row if "✏️" in b.text}
    assert marked == {"f:cat:hood"}
    summary = kb.render_root_summary(draft, "he")
    assert "שכונות ורחובות: רחביה, &lt;b&gt;, הרצל" in summary


def test_typed_place_names_are_split_trimmed_and_capped():
    from handlers import filter_conversation as fc

    assert fc._parse_place_names(" רחביה ,בקעה،  נווה   צדק\nרחביה,, ") == ["רחביה", "בקעה", "נווה צדק"]
    assert len(fc._parse_place_names(",".join(f"שכונה {i}" for i in range(50)))) == 20
    assert len(fc._parse_place_names("א" * 200)[0]) == 40
    assert fc._parse_place_names("") == []


def test_typing_neighbourhoods_stores_them_and_returns_to_the_screen():
    from handlers import filter_conversation as fc
    from todira_common.schemas import FilterData

    draft = FilterData().model_dump()
    context = SimpleNamespace(user_data={"draft": draft, "draft_base": dict(draft), "awaiting": "streets_include", "lang": "he"})
    update = SimpleNamespace(message=SimpleNamespace(text="הרצל, יפו", reply_text=AsyncMock()), effective_user=SimpleNamespace(id=5))
    with patch.object(fc, "_send_category", AsyncMock()) as send:
        result = asyncio.run(fc.text_input(update, context))
    assert result == fc.MENU and draft["streets_include"] == ["הרצל", "יפו"]
    assert send.await_args.args[3] == "hood"
