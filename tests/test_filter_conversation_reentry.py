"""Regression test for a real production bug found 2026-08-31 (see PROJECT_STATE.md): a user who
ever abandoned a /filter session mid-way (closed the chat with the inline menu still open, never
tapped Save/Cancel) got stuck in that ConversationHandler state FOREVER — every future /filter
they sent matched nothing at all and got total silence, not even an error, because
python-telegram-bot's ConversationHandler only tries its entry_points when
`state is None or allow_reentry` (allow_reentry defaults to False), and MENU's own state handler
only accepts inline-button callback queries, not a text command.

This constructs real telegram.Update/Message objects and drives ConversationHandler.check_update
directly (no network, no DB — check_update only decides routing, it doesn't invoke the callback)
to prove: (a) a stuck MENU/AWAIT_TEXT state is unresponsive to /filter without allow_reentry
(reproducing the original bug, so this test would have caught it), and (b) it IS responsive with
allow_reentry=True (the fix)."""
import datetime
import sys
import types

if "patchright" not in sys.modules:
    patchright_stub = types.ModuleType("patchright")
    sync_api_stub = types.ModuleType("patchright.sync_api")
    sync_api_stub.TimeoutError = TimeoutError
    sync_api_stub.sync_playwright = None
    patchright_stub.sync_api = sync_api_stub
    sys.modules["patchright"] = patchright_stub
    sys.modules["patchright.sync_api"] = sync_api_stub

from telegram import Chat, Message, MessageEntity, Update, User

from handlers.filter_conversation import AWAIT_TEXT, MENU, build_filter_conversation_handler
from handlers.onboarding import build_onboarding_handler

CHAT_ID = 111
USER_ID = 222


class _FakeBot:
    username = "AmirDirotBot"


def _command_update(text: str, entity_length: int) -> Update:
    chat = Chat(id=CHAT_ID, type="private")
    user = User(id=USER_ID, first_name="Test", is_bot=False)
    message = Message(
        message_id=1,
        date=datetime.datetime.now(datetime.timezone.utc),
        chat=chat,
        from_user=user,
        text=text,
        entities=[MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=entity_length)],
    )
    message.set_bot(_FakeBot())
    return Update(update_id=1, message=message)


def _filter_update() -> Update:
    return _command_update("/filter", entity_length=len("/filter"))


def test_stuck_in_menu_state_is_unresponsive_without_allow_reentry():
    """Reproduces the original bug: with allow_reentry off, a /filter sent while the user is
    stuck in MENU matches nothing at all — this is what "no response, not even an error" looked
    like in production."""
    handler = build_filter_conversation_handler()
    handler._allow_reentry = False  # simulate the pre-fix default
    handler._conversations[(CHAT_ID, USER_ID)] = MENU

    assert handler.check_update(_filter_update()) is None


def test_stuck_in_menu_state_re_enters_with_allow_reentry():
    handler = build_filter_conversation_handler()
    assert handler.allow_reentry is True  # the actual fix must be in place

    handler._conversations[(CHAT_ID, USER_ID)] = MENU
    result = handler.check_update(_filter_update())

    assert result is not None
    _state, key, matched_handler, _check = result
    assert key == (CHAT_ID, USER_ID)
    assert matched_handler in handler.entry_points


def test_stuck_in_await_text_state_also_re_enters():
    # Same scenario but for the other conversation state (e.g. abandoned mid-typing a price) —
    # AWAIT_TEXT's own handler only accepts plain text, not a command, so this needs allow_reentry
    # just as much as MENU does.
    handler = build_filter_conversation_handler()
    handler._conversations[(CHAT_ID, USER_ID)] = AWAIT_TEXT

    assert handler.check_update(_filter_update()) is not None


def test_onboarding_handler_also_has_allow_reentry():
    # /start already doubled as both an entry point and a fallback here, so it wasn't actually
    # exposed to this exact bug — allow_reentry is set anyway for defense-in-depth, this just
    # locks that choice in.
    assert build_onboarding_handler().allow_reentry is True
