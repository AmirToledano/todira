"""2026-11-03: people asking in the Facebook groups for a flat go to the owner's leads group (scraper/seeker_leads.py)."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.owner_inbox as bot_inbox  # noqa: E402
import seeker_leads  # noqa: E402
from telegram.constants import ChatMemberStatus, ChatType  # noqa: E402

from todira_common import owner_inbox  # noqa: E402

NOW = dt.datetime(2026, 11, 3, 10, tzinfo=dt.timezone.utc)


def _post(post_id, text="מחפשת דירת 2 חדרים בגבעתיים עד 5000", hours_ago=1, group="555"):
    return {"post_id": post_id, "group_id": group, "text": text,
            "creation_time": int((NOW - dt.timedelta(hours=hours_ago)).timestamp()), "author": "Someone"}


class _Flags:
    def __init__(self):
        self.value = None


def _wire(monkeypatch, leads="-100777", ok=True):
    flags, sent = _Flags(), []

    @contextmanager
    def _session():
        yield SimpleNamespace()

    monkeypatch.setattr(seeker_leads, "get_session", _session)
    monkeypatch.setattr(seeker_leads, "get_flag", lambda s, k: flags.value)
    monkeypatch.setattr(seeker_leads, "set_flag", lambda s, k, v: setattr(flags, "value", v))
    monkeypatch.setattr(owner_inbox, "leads_chat_id", lambda: leads)
    monkeypatch.setattr(owner_inbox, "owner_chat_ids", lambda owner: ["-100inbox", "999"])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")

    def _post_http(url, json, timeout):
        sent.append(json)
        return SimpleNamespace(status_code=200 if ok else 400)

    monkeypatch.setattr(seeker_leads.httpx, "post", _post_http)
    return flags, sent


def test_each_new_seeker_goes_once_to_the_leads_group_with_a_link(monkeypatch):
    flags, sent = _wire(monkeypatch)
    posts = [_post("1"), _post("2", hours_ago=72)]  # the second is too old
    assert seeker_leads.send_leads(posts, lambda p: ("גבעתיים", "rent"), now=NOW) == 1
    assert sent[0]["chat_id"] == "-100777"
    body = sent[0]["text"]
    assert "<b>מחפשים דירה בגבעתיים</b>" in body
    assert 'href="https://www.facebook.com/groups/555/posts/1/"' in body
    assert "Someone" not in body and "—" not in body
    assert json.loads(flags.value) == ["1"]
    assert seeker_leads.send_leads(posts, lambda p: (None, None), now=NOW) == 0  # not again


def test_without_a_leads_group_they_go_to_the_inbox(monkeypatch):
    _, sent = _wire(monkeypatch, leads=None)
    seeker_leads.send_leads([_post("1")], lambda p: (None, "sale"), now=NOW)
    assert sent[0]["chat_id"] == "-100inbox"
    assert "<b>מחפשים לקנות דירה</b>" in sent[0]["text"]


def test_a_failed_send_is_tried_again_next_run_and_a_burst_is_capped(monkeypatch):
    flags, sent = _wire(monkeypatch, ok=False)
    assert seeker_leads.send_leads([_post("1")], lambda p: (None, None), now=NOW) == 0
    assert json.loads(flags.value) == []
    flags2, sent2 = _wire(monkeypatch)
    many = [_post(str(i)) for i in range(40)]
    assert seeker_leads.send_leads(many, lambda p: (None, None), now=NOW) == seeker_leads.MAX_PER_RUN


def test_a_long_post_is_cut_on_a_word():
    text = "מחפש דירה " + "מילה " * 200
    body = seeker_leads.message(_post("1", text=text), None, None)
    quote = body.split("\n\n")[1]
    assert quote.endswith("...") and len(quote) <= seeker_leads.QUOTE_CHARS + 3


def test_leads_group_by_name_or_command(monkeypatch):
    saved = {"leads": None, "inbox": None}
    monkeypatch.setattr(bot_inbox, "_save_leads", lambda chat_id: saved.update(leads=chat_id))
    monkeypatch.setattr(bot_inbox, "_save", lambda chat_id: saved.update(inbox=chat_id))
    monkeypatch.setattr(bot_inbox, "_current", lambda: None)
    monkeypatch.setattr(owner_inbox, "leads_chat_id", lambda: None)
    monkeypatch.setenv("OWNER_TELEGRAM_USER_ID", "999")
    bot = SimpleNamespace(send_message=AsyncMock(), leave_chat=AsyncMock())
    context = SimpleNamespace(bot=bot)

    def _added(title, by="999"):
        chat = SimpleNamespace(id=-100777, type=ChatType.GROUP, title=title)
        change = SimpleNamespace(
            chat=chat, from_user=SimpleNamespace(id=int(by)),
            old_chat_member=SimpleNamespace(status=ChatMemberStatus.LEFT),
            new_chat_member=SimpleNamespace(status=ChatMemberStatus.MEMBER),
        )
        return SimpleNamespace(my_chat_member=change)

    asyncio.run(bot_inbox.on_my_chat_member(_added("טודירה לידים"), context))
    assert saved == {"leads": -100777, "inbox": None}
    assert "מחפשים דירה" in bot.send_message.await_args.kwargs["text"]
    asyncio.run(bot_inbox.on_my_chat_member(_added("פניות"), context))
    assert saved["inbox"] == -100777

    saved.update(leads=None)
    monkeypatch.setattr(bot_inbox, "_current", lambda: "-100888")
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=-100888, type=ChatType.SUPERGROUP),
                             effective_user=SimpleNamespace(id=999))
    asyncio.run(bot_inbox.on_leads_command(update, context))
    assert saved["leads"] == -100888 and saved["inbox"] is None  # no longer the inbox
    stranger = SimpleNamespace(effective_chat=update.effective_chat, effective_user=SimpleNamespace(id=1))
    saved.update(leads=None)
    asyncio.run(bot_inbox.on_leads_command(stranger, context))
    assert saved["leads"] is None
