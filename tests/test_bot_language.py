"""2026-10-18 (owner report): a friend's bot opened in English, following the phone's language, and there was no way to
switch it. New users now start in Hebrew whatever the phone says, and /language (also a button in /profile) switches
it - bot/handlers/language.py."""
from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import handlers.language as language_module
import handlers.profile as profile_module
import handlers.start as start_module
from todira_common import users as users_module


class _Session:
    def __init__(self, results=()):
        self._results = list(results)
        self.added: list = []
        self.committed = False

    def scalar(self, stmt):
        return self._results.pop(0) if self._results else None

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _english_phone_user(id=555):
    return SimpleNamespace(id=id, username="friend", first_name="Dan", language_code="en-US")


def test_a_new_user_from_start_gets_hebrew_whatever_the_phone_language():
    session = _Session(results=[None])
    with patch.object(start_module, "get_session", lambda: session):
        start_module._upsert_or_link_user_sync(_english_phone_user(), None)
    created = session.added[0]
    assert created.language is None  # None = Hebrew, todira_common.language.DEFAULT_LANG


def test_a_new_user_from_any_other_handler_gets_hebrew_too():
    session = _Session(results=[None])
    user = users_module.get_or_create_user(session, _english_phone_user())
    assert user.language is None


def test_the_picker_offers_every_language_in_its_own_name_and_marks_the_current_one():
    keyboard = language_module.language_keyboard("en")
    labels = [row[0].text for row in keyboard.inline_keyboard]
    data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert labels == ["עברית", "✅ English", "Русский", "Français", "العربية"]
    assert data == ["lang:set:he", "lang:set:en", "lang:set:ru", "lang:set:fr", "lang:set:ar"]


def test_choosing_a_language_stores_it_and_hebrew_is_stored_as_none():
    user = SimpleNamespace(language="en")
    session = _Session()
    with (
        patch.object(language_module, "get_session", lambda: session),
        patch.object(language_module, "get_or_create_user", lambda s, u: user),
    ):
        language_module._set_language_sync(_english_phone_user(), "ru")
        assert user.language == "ru"
        language_module._set_language_sync(_english_phone_user(), "he")
        assert user.language is None
    assert session.committed


def _callback_update(data):
    query = SimpleNamespace(
        data=data, answer=AsyncMock(), edit_message_text=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    return SimpleNamespace(callback_query=query, effective_user=_english_phone_user()), query


def test_the_choice_also_switches_a_conversation_already_open():
    update, query = _callback_update("lang:set:he")
    context = SimpleNamespace(user_data={"onboarding_lang": "en", "lang": "en"})
    with patch.object(language_module, "_set_language_sync") as set_mock:
        asyncio.run(language_module.language_callback(update, context))
    set_mock.assert_called_once_with(update.effective_user, "he")
    assert context.user_data == {"onboarding_lang": "he", "lang": "he"}
    assert "בעברית" in query.edit_message_text.call_args.args[0]


def test_an_unknown_language_code_changes_nothing():
    update, query = _callback_update("lang:set:xx")
    context = SimpleNamespace(user_data={})
    with patch.object(language_module, "_set_language_sync") as set_mock:
        asyncio.run(language_module.language_callback(update, context))
    set_mock.assert_not_called()
    query.answer.assert_awaited_once()


def test_the_profile_button_opens_the_picker_as_its_own_message():
    update, query = _callback_update("lang:menu")
    with patch.object(language_module, "_current_language_sync", return_value="en"):
        asyncio.run(language_module.language_callback(update, SimpleNamespace(user_data={})))
    markup = query.message.reply_text.call_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[1][0].text == "✅ English"
    query.edit_message_text.assert_not_called()


def test_profile_has_a_language_button_readable_in_hebrew_and_english():
    user = SimpleNamespace(is_active=True, notifications_enabled=True)
    keyboard = profile_module._keyboard(user, "en")
    last = keyboard.inline_keyboard[-1][0]
    assert last.callback_data == "lang:menu"
    assert "Language" in last.text and "שפה" in last.text


def test_language_is_in_the_bot_menu():
    # loaded under its own name, like test_bot_heartbeat.py: a bare `import main` would clash with scraper/main.py
    spec = importlib.util.spec_from_file_location("bot_main_language", Path(__file__).resolve().parent.parent / "bot" / "main.py")
    bot_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot_main)
    assert "language" in [command.command for command in bot_main.BOT_COMMANDS]
