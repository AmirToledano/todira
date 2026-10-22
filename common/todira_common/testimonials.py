"""Real testimonials (2026-10-22, owner: "nobody presses 'I found a flat' at the end, ask them instead").

The bot asks "did you find a flat?" when a user pauses their alerts, and (in the morning, from the main scraper run -
scraper/renewal_reminder.py) a few days after their pass or trial ended. A "yes" asks for one sentence about how it
went and permission to show it on the site with their first name; that reply is saved as a ContactMessage with
source="testimonial" and sent to the owner. Nothing shows on the site until the owner approves it on /admin/messages
(app flag "testimonial_show:<id>")."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session
from todira_common.app_flags import get_flag, set_flag
from todira_common.bot_strings import bot_text
from todira_common.models import AppFlag, ContactMessage

SOURCE = "testimonial"
ASK_AGAIN_AFTER = dt.timedelta(days=60)


def found_keyboard(lang: str):
    # Imported here, not at the top: the website imports this module too, and its image has no Telegram library.
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(bot_text("found_ask.yes_btn", lang), callback_data="tq:yes"),
            InlineKeyboardButton(bot_text("found_ask.no_btn", lang), callback_data="tq:no"),
        ]]
    )


def _asked_key(user_id: int) -> str:
    return f"found_asked:{user_id}"


def asked_recently(session: Session, user_id: int, now: dt.datetime) -> bool:
    value = get_flag(session, _asked_key(user_id))
    if not value:
        return False
    try:
        return now - dt.datetime.fromisoformat(value) < ASK_AGAIN_AFTER
    except ValueError:
        return True


def mark_asked(session: Session, user_id: int, now: dt.datetime) -> None:
    set_flag(session, _asked_key(user_id), now.isoformat())


def _show_key(message_id: int) -> str:
    return f"testimonial_show:{message_id}"


def is_shown(session: Session, message_id: int) -> bool:
    return get_flag(session, _show_key(message_id)) == "1"


def set_shown(session: Session, message_id: int, shown: bool) -> None:
    set_flag(session, _show_key(message_id), "1" if shown else "0")


def shown_testimonials(session: Session, limit: int = 6) -> list[ContactMessage]:
    """Testimonials the owner approved for the site, newest first."""
    shown_ids = [
        int(key.rsplit(":", 1)[1])
        for key, value in session.execute(
            select(AppFlag.key, AppFlag.value).where(AppFlag.key.like("testimonial_show:%"))
        )
        if value == "1" and key.rsplit(":", 1)[1].isdigit()
    ]
    if not shown_ids:
        return []
    return list(
        session.scalars(
            select(ContactMessage)
            .where(ContactMessage.id.in_(shown_ids), ContactMessage.source == SOURCE)
            .order_by(ContactMessage.created_at.desc())
            .limit(limit)
        )
    )
