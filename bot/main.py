"""Entrypoint: builds the Application, registers all handlers, and starts polling. No
webhook/public URL is needed in Phase 1 — see plan Section 5.
"""
from __future__ import annotations

import logging
import os

from handlers.apartments import build_apartments_handler
from handlers.filter_conversation import build_filter_conversation_handler
from handlers.liked import build_liked_handler, build_reaction_handler
from handlers.onboarding import build_onboarding_handler
from handlers.profile import build_profile_handlers
from telegram import BotCommand
from telegram.ext import Application

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("bot.main")

# Shown in Telegram's "Menu" button — only appears once a user has started a session with the
# bot (Telegram's own behavior, not something we control), matching what the reference bot's
# menu looked like in the screenshots.
BOT_COMMANDS = [
    BotCommand("start", "👋 היי DirAmir"),
    BotCommand("filter", "🎯 החיפוש שלי"),
    BotCommand("apartments", "👀 כל הדירות"),
    BotCommand("liked", "❤️ דירות ששמרתי"),
    BotCommand("profile", "👤 אזור אישי"),
]


async def _post_init(application: Application) -> None:
    await application.bot.set_my_commands(BOT_COMMANDS)


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    application = Application.builder().token(token).post_init(_post_init).build()

    application.add_handler(build_onboarding_handler())
    application.add_handler(build_filter_conversation_handler())
    application.add_handler(build_apartments_handler())
    application.add_handler(build_liked_handler())
    application.add_handler(build_reaction_handler())
    for handler in build_profile_handlers():
        application.add_handler(handler)

    logger.info("Starting bot polling...")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
