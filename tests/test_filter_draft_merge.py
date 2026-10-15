"""2026-10-15 bug: an unsaved /filter draft in the bot, resumed after the filter was edited on the website, put the old
values back over the website's on Save. The draft now remembers the saved filter it started from (draft_base)."""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.filter_conversation as fc


def _filter(**changes):
    values = fc._default_draft()
    values.update(changes)
    return values


def _start(monkeypatch, user_data, saved):
    monkeypatch.setattr(fc, "_load_draft_and_lang_from_db_sync", lambda tg_user: (dict(saved), "he"))
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=SimpleNamespace(reply_text=AsyncMock()))
    context = SimpleNamespace(user_data=user_data)
    asyncio.run(fc.filter_start(update, context))
    return context.user_data


def test_resuming_brings_in_website_edits_and_keeps_the_bots(monkeypatch):
    base = _filter(cities=["חיפה"], price_max=5000)
    draft = _filter(cities=["חיפה"], price_max=6000)  # changed in the bot, not saved
    saved = _filter(cities=["חיפה", "עכו"], price_max=5000)  # cities changed on the website meanwhile

    user_data = _start(monkeypatch, {"draft": draft, "draft_base": base}, saved)

    assert user_data["draft"]["cities"] == ["חיפה", "עכו"]
    assert user_data["draft"]["price_max"] == 6000
    assert user_data["draft_base"]["cities"] == ["חיפה", "עכו"]


def test_a_draft_that_does_not_know_its_start_is_replaced_by_the_saved_filter(monkeypatch):
    saved = _filter(cities=["עכו"])
    user_data = _start(monkeypatch, {"draft": _filter(cities=["חיפה"])}, saved)

    assert user_data["draft"]["cities"] == ["עכו"]


def test_save_writes_only_what_changed_in_the_bot():
    base = _filter(cities=["חיפה"], price_max=5000)
    values = fc.FilterData(**_filter(cities=["חיפה"], price_max=6000)).model_dump()
    saved_now = _filter(cities=["חיפה", "עכו"], price_max=5000, rooms_min=3)

    merged = fc._merge_onto_saved(saved_now, values, base)

    assert merged["price_max"] == 6000
    assert merged["cities"] == ["חיפה", "עכו"]
    assert merged["rooms_min"] == 3


def test_save_with_nothing_changed_elsewhere_is_the_draft_itself():
    base = _filter(cities=["חיפה"])
    values = fc.FilterData(**_filter(cities=["חיפה"], price_max=6000)).model_dump()

    assert fc._merge_onto_saved(dict(base), values, base) == values


def test_an_impossible_combination_falls_back_to_the_bots_filter():
    base = _filter(cities=["חיפה"])
    values = fc.FilterData(**_filter(cities=["חיפה"], price_max=3000)).model_dump()
    saved_now = _filter(cities=["חיפה"], price_min=5000)  # website raised the minimum above the bot's new maximum

    assert fc._merge_onto_saved(saved_now, values, base) == values


def test_a_menu_tap_with_no_draft_loads_the_saved_filter_not_empty_defaults(monkeypatch):
    saved = _filter(cities=["עכו"], price_max=4000)
    monkeypatch.setattr(fc, "_load_draft_and_lang_from_db_sync", lambda tg_user: (dict(saved), "he"))
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1))
    context = SimpleNamespace(user_data={})

    draft = asyncio.run(fc._ensure_draft(update, context))

    assert draft["cities"] == ["עכו"] and draft["price_max"] == 4000
    assert context.user_data["draft_base"] == saved
