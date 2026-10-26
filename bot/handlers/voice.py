"""Voice messages (2026-10-24, owner-approved): the recording is turned into text and handled exactly like a typed
message - onboarding, /filter edits and free chat all read it the same way. A recording that can't be understood gets
one short reply asking to try again or type."""
from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes, MessageHandler, filters

from todira_common import gemini_client
from todira_common.bot_strings import bot_text
from handlers.testimonial import _user_lang_sync

logger = logging.getLogger(__name__)

MAX_SECONDS = 120


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from todira_common import switches

    if not await asyncio.to_thread(switches.is_on, "voice", True):
        return  # switched off from the owner's dashboard: the recording goes on to the other handlers as before
    message = update.message
    media = message.voice or message.audio
    lang = await asyncio.to_thread(_user_lang_sync, update.effective_user.id)
    text = None
    if media is not None and (media.duration or 0) <= MAX_SECONDS:
        try:
            file = await media.get_file()
            audio = bytes(await file.download_as_bytearray())
            text = await asyncio.to_thread(
                gemini_client.transcribe_voice, audio, getattr(media, "mime_type", None) or "audio/ogg"
            )
        except Exception:
            logger.warning("voice message could not be read", exc_info=True)
    if not text:
        await message.reply_text(bot_text("voice.not_understood", lang))
        raise ApplicationHandlerStop
    data = update.to_dict()
    data["message"].pop("voice", None)
    data["message"].pop("audio", None)
    data["message"]["text"] = text
    await context.application.process_update(Update.de_json(data, context.bot))
    raise ApplicationHandlerStop


def build_voice_handler() -> tuple[MessageHandler, int]:
    """(handler, group): after the activity counter and the group guard, before every handler that reads text."""
    return MessageHandler(filters.ChatType.PRIVATE & (filters.VOICE | filters.AUDIO), handle_voice), 0
