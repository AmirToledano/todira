"""Entrypoint: builds the Application, registers all handlers, and starts polling. No
webhook/public URL is needed in Phase 1 — see plan Section 5.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from handlers.activity import build_activity_handler
from handlers.voice import build_voice_handler
from handlers.support import build_support_handler
from handlers.apartments import build_apartments_handler
from handlers.contact_fallback import build_contact_fallback_handler
from handlers.filter_conversation import build_filter_conversation_handler
from handlers.language import build_language_handlers
from handlers.liked import build_hidden_handler, build_liked_handler, build_reaction_handler
from handlers.onboarding import build_onboarding_handler
from handlers.owner_inbox import build_owner_inbox_handlers
from handlers.profile import build_profile_handlers
from handlers.testimonial import build_found_answer_handler
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

# Liveness-probe heartbeat (added 2026-09-08, pre-launch reliability pass — see
# charts/todira/templates/bot-deployment.yaml's own new livenessProbe comment). Unlike a plain
# background thread, a JobQueue job runs ON THE SAME asyncio event loop that processes every
# incoming Telegram update — if that loop ever deadlocks (a real handler bug, a library hang),
# this job stops firing right along with real message handling, so the file genuinely goes stale
# instead of a naive "the process technically still exists" thread happily ticking forever
# regardless of whether the bot can do anything. No user activity ever makes this file stale on
# its own — the job runs on a fixed interval independent of whether anyone messages the bot, so an
# idle-but-healthy bot never gets mistaken for a hung one.
HEARTBEAT_PATH = os.environ.get("BOT_HEARTBEAT_PATH", "/tmp/bot_heartbeat")
HEARTBEAT_INTERVAL_S = 15

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
    BotCommand("filter", "⚙️ החיפוש שלי"),
    BotCommand("apartments", "👀 כל הדירות"),
    BotCommand("liked", "❤️ דירות ששמרתי"),
    BotCommand("hidden", "🙈 דירות שהסתרתי"),
    BotCommand("profile", "👤 אזור אישי"),
    BotCommand("support", "🆘 פנייה לתמיכה"),
    BotCommand("language", "🌐 שפה · Language"),
]


BOT_SHORT_DESCRIPTION = "כל דירה חדשה להשכרה או למכירה, ישר לטלגרם, דקות אחרי שעלתה 🏠"


async def _heartbeat_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    Path(HEARTBEAT_PATH).touch()


async def _post_init(application: Application) -> None:
    await application.bot.set_my_commands(BOT_COMMANDS)
    # 2026-10-24 (owner approved): the "about" line on the bot's profile page was empty.
    try:
        await application.bot.set_my_short_description(BOT_SHORT_DESCRIPTION)
    except Exception:
        logger.warning("Could not set the bot's short description", exc_info=True)
    if application.job_queue is not None:
        # first=0 so the file exists immediately, not only after the first interval elapses —
        # otherwise a liveness probe that starts checking right at container boot could see a
        # missing file and wrongly treat a perfectly healthy, just-started bot as failed.
        application.job_queue.run_repeating(_heartbeat_job, interval=HEARTBEAT_INTERVAL_S, first=0)
    else:
        # Defensive only — requirements.txt pins python-telegram-bot[job-queue], so this should
        # never actually be None in a real deploy; logged loudly rather than silently skipped in
        # case that pin is ever accidentally dropped, since it would silently disable the
        # liveness probe's actual signal (see bot-deployment.yaml's own livenessProbe comment).
        logger.error(
            "JobQueue unavailable — the liveness-probe heartbeat will never update, so the bot "
            "Pod will eventually be killed as unhealthy even while running fine. Check that "
            "python-telegram-bot is installed with the [job-queue] extra."
        )


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

    # 2026-10-21: counts messages and button presses per person per day (handlers/activity.py), before anything else
    application.add_handler(*build_activity_handler())
    # 2026-10-20: the owner's inbox group (handlers/owner_inbox.py) - its guard runs before every handler below
    for handler, group in build_owner_inbox_handlers():
        application.add_handler(handler, group=group)
    # 2026-10-24: voice messages become text first (handlers/voice.py), then go through every handler below
    application.add_handler(*build_voice_handler())
    application.add_handler(build_support_handler())
    application.add_handler(build_onboarding_handler())
    application.add_handler(build_filter_conversation_handler())
    application.add_handler(build_apartments_handler())
    application.add_handler(build_liked_handler())
    application.add_handler(build_hidden_handler())
    application.add_handler(build_reaction_handler())
    application.add_handler(build_found_answer_handler())
    for handler in build_profile_handlers():
        application.add_handler(handler)
    for handler in build_language_handlers():
        application.add_handler(handler)
    # Registered LAST (same default group) so it only fires once every ConversationHandler and
    # CommandHandler above has already declined the update — see contact_fallback.py's docstring.
    application.add_handler(build_contact_fallback_handler())
    application.add_error_handler(_error_handler)

    logger.info("Starting bot polling...")
    application.run_polling(allowed_updates=["message", "callback_query", "my_chat_member"])


if __name__ == "__main__":
    main()
