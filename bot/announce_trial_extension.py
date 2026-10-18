"""One-time Telegram message: the free trial went from 3 to 10 days and everyone already registered got 7 more days
(2026-10-18, owner request; migration 0030 did the extension itself).

Run by .github/workflows/announce-trial-extension.yaml inside the bot pod, once, at a civil hour. Reaches only people
the extension actually helps: a Telegram account created before the change, still searching, alerts on, inside its
trial now, without a paid pass or free access. Every chat a message reached is written to SENT_LOG (on the bot's
persistent volume), so a second run never sends anyone the same message twice. Prints counts only - never an id,
name or chat."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from telegram import Bot
from telegram.error import Forbidden, RetryAfter, TelegramError

from todira_common.bot_strings import bot_text
from todira_common.db import get_session
from todira_common.language import DEFAULT_LANG
from todira_common.models import User

CHANGE_AT = dt.datetime(2026, 10, 19, 0, 0, tzinfo=dt.timezone.utc)  # accounts created before this got the 7 days
SENT_LOG = Path(os.environ.get("TRIAL_GIFT_SENT_LOG", "/data/trial_gift_sent.txt"))
SEND_DELAY_SECONDS = 0.05  # well under Telegram's ~30 messages a second


def recipients(session, now: dt.datetime) -> list[tuple[int, str, dt.datetime]]:
    """(telegram chat id, language, new trial end) for everyone the message is for."""
    rows = session.execute(
        select(User.telegram_user_id, User.language, User.trial_ends_at).where(
            User.telegram_user_id.is_not(None),
            User.is_active.is_(True),
            User.notifications_enabled.is_(True),
            User.free_access_granted.is_(False),
            User.created_at < CHANGE_AT,
            User.trial_ends_at > now,
            or_(User.paid_until.is_(None), User.paid_until <= now),
        )
    ).all()
    return [(row.telegram_user_id, row.language or DEFAULT_LANG, row.trial_ends_at) for row in rows]


def message_for(lang: str, trial_ends_at: dt.datetime) -> str:
    date = trial_ends_at.astimezone(ZoneInfo("Asia/Jerusalem")).strftime("%d.%m")
    return bot_text("trial_gift.telegram", lang, date=date)


def _already_sent() -> set[int]:
    if not SENT_LOG.exists():
        return set()
    return {int(line) for line in SENT_LOG.read_text().split() if line.strip().isdigit()}


async def send_all(bot, targets, already_sent: set[int], log_file) -> dict[str, int]:
    counts = {"sent": 0, "skipped_already_sent": 0, "blocked": 0, "failed": 0}
    for chat_id, lang, trial_ends_at in targets:
        if chat_id in already_sent:
            counts["skipped_already_sent"] += 1
            continue
        text = message_for(lang, trial_ends_at)
        for attempt in (1, 2):
            try:
                await bot.send_message(chat_id=chat_id, text=text)
                counts["sent"] += 1
                log_file.write(f"{chat_id}\n")
                log_file.flush()
                break
            except RetryAfter as exc:
                if attempt == 2:
                    counts["failed"] += 1
                    break
                await asyncio.sleep(float(getattr(exc, "retry_after", 1)) + 1)
            except Forbidden:
                counts["blocked"] += 1  # the person blocked the bot
                break
            except TelegramError:
                counts["failed"] += 1
                break
        await asyncio.sleep(SEND_DELAY_SECONDS)
    return counts


async def main(send: bool) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    with get_session() as session:
        targets = recipients(session, now)
    already_sent = _already_sent()
    print(f"people the message is for: {len(targets)} (already sent earlier: {len(already_sent & {t[0] for t in targets})})")
    if not send:
        print("dry run - nothing sent")
        return
    SENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SENT_LOG.open("a") as log_file:
        async with Bot(token=os.environ["TELEGRAM_BOT_TOKEN"]) as bot:
            counts = await send_all(bot, targets, already_sent, log_file)
    print(" | ".join(f"{name}: {value}" for name, value in counts.items()))


if __name__ == "__main__":
    asyncio.run(main(send="--send" in sys.argv[1:]))
