"""2026-10-21 (owner: "when I ask, I want to know whether there was activity"): counts per person per day."""
from __future__ import annotations

import asyncio
import datetime as dt
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from telegram.constants import ChatType

from todira_common import activity

_ROOT = Path(__file__).resolve().parent.parent


def test_an_anonymous_visitor_is_the_same_all_day_and_different_the_next():
    day = dt.date(2026, 10, 21)
    one = activity.visitor_key("1.2.3.4", "Safari", "s", day)
    assert one == activity.visitor_key("1.2.3.4", "Safari", "s", day)
    assert one != activity.visitor_key("1.2.3.4", "Safari", "s", day + dt.timedelta(days=1))
    assert one != activity.visitor_key("1.2.3.5", "Safari", "s", day)
    assert one.startswith("v") and "1.2.3.4" not in one


def test_record_never_raises(monkeypatch):
    importlib.reload(activity)  # the real record(), not the conftest stub

    def broken():
        raise RuntimeError("no database")

    monkeypatch.setattr(activity, "get_session", broken)
    activity.record(activity.SITE_VISIT, "u1")


def _bot_update(chat_type, *, button=False, text="שלום"):
    return SimpleNamespace(
        effective_chat=SimpleNamespace(type=chat_type),
        effective_user=SimpleNamespace(id=42),
        callback_query=object() if button else None,
        message=None if button else SimpleNamespace(text=text),
    )


def test_bot_counts_private_messages_and_buttons_but_not_groups(monkeypatch):
    sys.path.insert(0, str(_ROOT / "bot"))
    from handlers import activity as bot_activity

    seen = []
    monkeypatch.setattr(activity, "record", lambda kind, who: seen.append((kind, who)))
    asyncio.run(bot_activity.count_activity(_bot_update(ChatType.PRIVATE), None))
    asyncio.run(bot_activity.count_activity(_bot_update(ChatType.PRIVATE, button=True), None))
    asyncio.run(bot_activity.count_activity(_bot_update(ChatType.GROUP), None))
    assert seen == [(activity.BOT_MESSAGE, "t42"), (activity.BOT_BUTTON, "t42")]


def _website():
    spec = importlib.util.spec_from_file_location("website_main_activity", _ROOT / "website" / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(_ROOT / "website"))
    spec.loader.exec_module(module)
    return module


def test_site_counts_pages_for_people_only(monkeypatch):
    site = _website()
    seen = []
    monkeypatch.setattr(activity, "record", lambda kind, who: seen.append((kind, who)))
    from fastapi.testclient import TestClient

    client = TestClient(site.app)
    browser = {"user-agent": "Mozilla/5.0 (iPhone) Safari"}
    client.get("/contact", headers=browser)
    client.get("/contact", headers={"user-agent": "Googlebot/2.1"})
    client.get("/static/style.css", headers=browser)
    assert [kind for kind, _ in seen] == [activity.SITE_VISIT]
    assert seen[0][1].startswith("v")
