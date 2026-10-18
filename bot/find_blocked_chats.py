"""Finds the people who blocked the bot and tells the owner who they are - privately, in the owner's own Telegram chat
(2026-10-19 owner request). The repository and its Actions logs are public, so this prints counts only; names go
nowhere but that one message. Each blocked person's search is paused, as the notifier now does by itself
(scraper/notifier.py's _pause_blocked_user); /start turns it back on.

Checks a chat with sendChatAction ("typing"): it shows nothing in a chat that is not open and sends no message, but
Telegram refuses it for a chat that blocked the bot. Run by .github/workflows/find-blocked-chats.yaml in the bot pod."""
from __future__ import annotations

import asyncio
import html
import os

from sqlalchemy import select
from telegram import Bot
from telegram.constants import ChatAction, ParseMode
from telegram.error import Forbidden, RetryAfter, TelegramError

from todira_common.db import get_session
from todira_common.models import Filter, User


def _describe(user: User, has_filter: bool) -> str:
    name = html.escape(user.first_name or "ללא שם")
    username = f" (@{html.escape(user.telegram_username)})" if user.telegram_username else ""
    joined = user.created_at.strftime("%d.%m.%Y") if user.created_at else "?"
    search = "עם חיפוש" if has_filter else "בלי חיפוש"
    return f"• {name}{username}, נרשם {joined}, {search}"


async def main() -> None:
    owner = os.environ.get("OWNER_TELEGRAM_USER_ID", "").strip()
    with get_session() as session:
        users = list(session.scalars(select(User).where(User.telegram_user_id.is_not(None), User.is_active.is_(True))))
        filtered = set(session.scalars(select(Filter.user_id)))
        blocked: list[User] = []
        failed = 0
        async with Bot(token=os.environ["TELEGRAM_BOT_TOKEN"]) as bot:
            for user in users:
                if str(user.telegram_user_id) == owner:
                    continue
                for attempt in (1, 2):
                    try:
                        await bot.send_chat_action(chat_id=user.telegram_user_id, action=ChatAction.TYPING)
                        break
                    except Forbidden:
                        blocked.append(user)
                        break
                    except RetryAfter as exc:
                        await asyncio.sleep(float(getattr(exc, "retry_after", 1)) + 1)
                    except TelegramError:
                        failed += 1
                        break
                await asyncio.sleep(0.1)
            for user in blocked:
                user.is_active = False
            session.commit()
            print(f"active Telegram users checked: {len(users)} | blocked the bot: {len(blocked)} | other errors: {failed}")
            if owner and blocked:
                lines = [f"🚫 <b>{len(blocked)} משתמשים חסמו את הבוט</b> (החיפוש שלהם הושהה, /start מחזיר אותם):"]
                lines += [_describe(user, user.id in filtered) for user in blocked]
                await bot.send_message(chat_id=owner, text="\n".join(lines), parse_mode=ParseMode.HTML)
                print("the list was sent to the owner's Telegram")


if __name__ == "__main__":
    asyncio.run(main())
