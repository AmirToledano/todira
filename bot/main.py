"""Entrypoint: builds the Application, registers all handlers, and starts polling. No
webhook/public URL is needed in Phase 1 — see plan Section 5.
"""
from __future__ import annotations

import logging
import os

from handlers.apartments import build_apartments_handler
from handlers.contact_fallback import build_contact_fallback_handler
from handlers.filter_conversation import build_filter_conversation_handler
from handlers.liked import build_liked_handler, build_reaction_handler
from handlers.onboarding import build_onboarding_handler
from handlers.profile import build_profile_handlers
from telegram import BotCommand, Update
from telegram.ext import Application, ContextTypes, PicklePersistence

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# python-telegram-bot uses httpx internally for every Telegram Bot API call, and Telegram's API
# URLs embed the bot token directly in the path (api.telegram.org/bot<TOKEN>/<method>) — httpx's
# own "httpx" logger emits an INFO line per request with the FULL URL, so at the root INFO level
# above this was leaking the live Telegram bot token into every pod log line, on every single API
# call the bot makes. Same issue found and fixed in scraper/main.py (there: a ZenRows API key)
# 2026-09-03 — silencing httpx specifically (not the whole app) keeps our own "bot.main" etc.
# logging at INFO as intended.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("bot.main")

# Persists user_data/chat_data and ConversationHandler state (see build_onboarding_handler and
# build_filter_conversation_handler, both persistent=True) across pod restarts - mounted on a PVC
# (see charts/todira/templates/bot-pvc.yaml), not the container's ephemeral filesystem, since a
# redeploy replaces the container entirely. Without this, every restart silently forgets which
# step of /start or /filter a user was on, and they get no response until they /start over.
PERSISTENCE_PATH = os.environ.get("BOT_PERSISTENCE_PATH", "/data/bot_persistence.pickle")

# Shown in Telegram's "Menu" button — only appears once a user has started a session with the
# bot (Telegram's own behavior, not something we control), matching what the reference bot's
# menu looked like in the screenshots.
BOT_COMMANDS = [
    BotCommand("start", "👋 היי טודירה"),
    BotCommand("filter", "🎯 החיפוש שלי"),
    BotCommand("apartments", "👀 כל הדירות"),
    BotCommand("liked", "❤️ דירות ששמרתי"),
    BotCommand("profile", "👤 אזור אישי"),
]


async def _post_init(application: Application) -> None:
    await application.bot.set_my_commands(BOT_COMMANDS)


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Without this, python-telegram-bot's default behavior on an uncaught handler exception is
    to log it and otherwise do nothing — the user just sees silence with no indication anything
    went wrong, and nothing points at *which* command/user hit it unless every single handler
    remembers to log for itself (none currently do, e.g. filter_conversation.py has zero logger
    calls). Registered as a catch-all so any future bug fails loud, in logs and to the user,
    instead of failing silently like this one apparently did."""
    logger.error(
        "Unhandled exception while processing update %s", update, exc_info=context.error
    )
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "😅 קרתה תקלה טכנית אצלנו. נסה/י שוב בעוד רגע — ואם זה נמשך, אפשר גם /start מחדש."
            )
        except Exception:
            logger.exception("Failed to notify the user about the error above")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    persistence = PicklePersistence(filepath=PERSISTENCE_PATH)
    application = (
        Application.builder().token(token).persistence(persistence).post_init(_post_init).build()
    )

    application.add_handler(build_onboarding_handler())
    application.add_handler(build_filter_conversation_handler())
    application.add_handler(build_apartments_handler())
    application.add_handler(build_liked_handler())
    application.add_handler(build_reaction_handler())
    for handler in build_profile_handlers():
        application.add_handler(handler)
    # Registered LAST (same default group) so it only fires once every ConversationHandler and
    # CommandHandler above has already declined the update — see contact_fallback.py's docstring.
    application.add_handler(build_contact_fallback_handler())
    application.add_error_handler(_error_handler)

    logger.info("Starting bot polling...")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
