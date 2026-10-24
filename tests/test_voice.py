"""handlers/voice.py: a recording becomes a typed message; one that can't be read gets one short reply."""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bot"))

from telegram.ext import ApplicationHandlerStop  # noqa: E402

from handlers import voice  # noqa: E402


def _update():
    media = SimpleNamespace(duration=5, mime_type="audio/ogg",
                            get_file=AsyncMock(return_value=SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(b"x")))))
    message = SimpleNamespace(voice=media, audio=None, reply_text=AsyncMock())
    update = MagicMock()
    update.message = message
    update.effective_user.id = 1
    update.to_dict.return_value = {"update_id": 1, "message": {"message_id": 1, "date": 0, "chat": {"id": 1, "type": "private"}, "voice": {}}}
    return update, message


def test_a_recording_is_handled_as_text():
    update, _message = _update()
    context = MagicMock()
    context.application.process_update = AsyncMock()
    with patch.object(voice, "_user_lang_sync", lambda uid: "he"), \
         patch.object(voice.gemini_client, "transcribe_voice", lambda audio, mime: "3 חדרים בחיפה"), \
         patch.object(voice.Update, "de_json", lambda data, bot: data):
        with pytest.raises(ApplicationHandlerStop):
            asyncio.run(voice.handle_voice(update, context))
    sent = context.application.process_update.await_args.args[0]
    assert sent["message"]["text"] == "3 חדרים בחיפה" and "voice" not in sent["message"]


def test_an_unreadable_recording_gets_one_reply():
    update, message = _update()
    context = MagicMock()
    with patch.object(voice, "_user_lang_sync", lambda uid: "he"), \
         patch.object(voice.gemini_client, "transcribe_voice", lambda audio, mime: None):
        with pytest.raises(ApplicationHandlerStop):
            asyncio.run(voice.handle_voice(update, context))
    assert "לא הצלחתי להבין את ההקלטה" in message.reply_text.await_args.args[0]
