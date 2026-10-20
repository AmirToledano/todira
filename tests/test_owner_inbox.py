"""2026-10-20 (owner: "send what people write to me somewhere else, the bot chat is muted because of the apartment
alerts"): messages for the owner go to his inbox group once he adds the bot to one, and to his private chat otherwise
or when that fails."""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.owner_inbox as bot_inbox  # noqa: E402
import handlers.support as support  # noqa: E402
from telegram.constants import ChatMemberStatus, ChatType  # noqa: E402
from telegram.error import TelegramError  # noqa: E402
from telegram.ext import ApplicationHandlerStop  # noqa: E402
from todira_common import owner_inbox  # noqa: E402

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))
_spec = importlib.util.spec_from_file_location("website_main_owner_inbox", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

OWNER = "999"
GROUP = "-100123"


@pytest.fixture
def stored(monkeypatch):
    """A stand-in for the app_flags row."""
    state = {"value": None}
    monkeypatch.setattr(owner_inbox, "inbox_chat_id", lambda fresh=False: state["value"])

    @contextmanager
    def _session():
        yield SimpleNamespace()

    monkeypatch.setattr(bot_inbox, "get_session", _session)
    monkeypatch.setattr(owner_inbox, "set_inbox_chat_id",
                        lambda session, chat_id: state.update(value=None if chat_id is None else str(chat_id)))
    monkeypatch.setenv("OWNER_TELEGRAM_USER_ID", OWNER)
    return state


# ---------- where messages go ----------

def test_the_group_comes_first_then_the_private_chat(monkeypatch):
    monkeypatch.setattr(owner_inbox, "inbox_chat_id", lambda fresh=False: GROUP)
    assert owner_inbox.owner_chat_ids(OWNER) == [GROUP, OWNER]


def test_without_a_group_everything_goes_to_the_private_chat():
    assert owner_inbox.owner_chat_ids(OWNER) == [OWNER]


class _Resp:
    def __init__(self, code):
        self.status_code, self.text = code, ""


def test_a_site_message_goes_to_the_group(monkeypatch):
    monkeypatch.setattr(owner_inbox, "inbox_chat_id", lambda fresh=False: GROUP)
    with patch.object(website_main, "TELEGRAM_BOT_TOKEN", "t"), patch.object(website_main, "OWNER_TELEGRAM_USER_ID", OWNER), \
            patch.object(website_main.httpx, "post", return_value=_Resp(200)) as post:
        assert website_main._notify_owner_sync("Dana", "", "hi", None, feedback=True) is True
    assert [c.kwargs["json"]["chat_id"] for c in post.call_args_list] == [GROUP]
    assert "משוב חדש על האתר" in post.call_args.kwargs["json"]["text"]


def test_when_the_group_fails_the_message_still_reaches_the_private_chat(monkeypatch):
    monkeypatch.setattr(owner_inbox, "inbox_chat_id", lambda fresh=False: GROUP)
    with patch.object(website_main, "TELEGRAM_BOT_TOKEN", "t"), patch.object(website_main, "OWNER_TELEGRAM_USER_ID", OWNER), \
            patch.object(website_main.httpx, "post", side_effect=[_Resp(400), _Resp(200)]) as post:
        assert website_main._notify_owner_sync("Dana", "", "hi", None) is True
    assert [c.kwargs["json"]["chat_id"] for c in post.call_args_list] == [GROUP, OWNER]


def test_a_help_request_in_the_bot_goes_to_the_group_and_falls_back(monkeypatch):
    monkeypatch.setattr(owner_inbox, "inbox_chat_id", lambda fresh=False: GROUP)
    monkeypatch.setattr(support, "OWNER_TELEGRAM_USER_ID", OWNER)
    monkeypatch.setattr(support, "_save_sync", lambda *a: 1)
    monkeypatch.setattr(support, "_mark_notified_sync", lambda *a: None)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=5, first_name="Dana", username=None))
    send = AsyncMock(side_effect=[TelegramError("gone"), None])
    context = SimpleNamespace(bot=SimpleNamespace(send_message=send))
    assert asyncio.run(support.escalate_to_owner(update, context, "צריך עזרה")) is True
    assert [c.kwargs["chat_id"] for c in send.call_args_list] == [GROUP, OWNER]


# ---------- the bot in a group ----------

def _member_update(chat_type, adder, old, new, chat_id=-100123):
    change = SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, type=chat_type), from_user=SimpleNamespace(id=adder),
        old_chat_member=SimpleNamespace(status=old), new_chat_member=SimpleNamespace(status=new),
    )
    return SimpleNamespace(my_chat_member=change)


def _context():
    return SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock(), leave_chat=AsyncMock()))


def test_added_by_the_owner_the_group_becomes_the_inbox(stored):
    ctx = _context()
    asyncio.run(bot_inbox.on_my_chat_member(
        _member_update(ChatType.GROUP, int(OWNER), ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER), ctx))
    assert stored["value"] == GROUP
    ctx.bot.send_message.assert_awaited_once()
    assert "התראות על דירות" in ctx.bot.send_message.call_args.kwargs["text"]


def test_made_admin_later_it_does_not_announce_itself_again(stored):
    ctx = _context()
    asyncio.run(bot_inbox.on_my_chat_member(
        _member_update(ChatType.SUPERGROUP, int(OWNER), ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR), ctx))
    assert stored["value"] == GROUP
    ctx.bot.send_message.assert_not_awaited()


def test_added_by_anyone_else_the_bot_leaves(stored):
    ctx = _context()
    asyncio.run(bot_inbox.on_my_chat_member(
        _member_update(ChatType.GROUP, 1234, ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER), ctx))
    assert stored["value"] is None
    ctx.bot.leave_chat.assert_awaited_once_with(-100123)


def test_removed_from_the_inbox_group_it_forgets_it(stored):
    stored["value"] = GROUP
    asyncio.run(bot_inbox.on_my_chat_member(
        _member_update(ChatType.GROUP, int(OWNER), ChatMemberStatus.MEMBER, ChatMemberStatus.LEFT), _context()))
    assert stored["value"] is None


def test_a_private_chat_block_is_not_about_the_inbox(stored):
    ctx = _context()
    asyncio.run(bot_inbox.on_my_chat_member(
        _member_update(ChatType.PRIVATE, 5, ChatMemberStatus.MEMBER, ChatMemberStatus.BANNED, chat_id=5), ctx))
    assert stored["value"] is None
    ctx.bot.leave_chat.assert_not_awaited()


def test_an_upgraded_group_keeps_being_the_inbox(stored):
    stored["value"] = "-555"
    msg = SimpleNamespace(migrate_to_chat_id=-100777, migrate_from_chat_id=None, chat=SimpleNamespace(id=-555))
    asyncio.run(bot_inbox.on_group_upgraded(SimpleNamespace(effective_message=msg), _context()))
    assert stored["value"] == "-100777"


def test_nothing_written_in_a_group_reaches_the_bots_conversations():
    group_msg = SimpleNamespace(effective_chat=SimpleNamespace(type=ChatType.GROUP), my_chat_member=None)
    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(bot_inbox.ignore_groups(group_msg, _context()))
    private_msg = SimpleNamespace(effective_chat=SimpleNamespace(type=ChatType.PRIVATE), my_chat_member=None)
    asyncio.run(bot_inbox.ignore_groups(private_msg, _context()))  # goes on as before
