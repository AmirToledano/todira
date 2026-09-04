"""/start — register a new user, reactivate + refresh a returning one (nudging them to renew if
their trial/paid access has expired), or — when reached via a `t.me/<bot>?start=ref_xxxxxx` deep
link generated on the website's /account page — link this Telegram account to that SAME existing
user instead of creating a separate one. See dorin_common/channel_link.py for the code itself and
website/whatsapp_webhook.py for the WhatsApp side of the same feature.
"""
from __future__ import annotations

import asyncio
import logging
import os

from config import WEBSITE_URL
from dorin_common.access import has_full_access
from dorin_common.channel_link import resolve_link_code
from dorin_common.db import get_session
from dorin_common.models import User
from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Mirrors website/main.py's _is_owner_id — same secret, same "owner always has full access"
# override, kept in its own module-level var here rather than in config.py since (like
# handlers/support.py's own copy) only this one handler needs it.
OWNER_TELEGRAM_USER_ID = os.environ.get("OWNER_TELEGRAM_USER_ID")

WELCOME = (
    "✨ 🏠 היי {name}! אני בוט חיפוש דירות אישי — סורק את שוק הדירות ומודיע לך כשמופיעה דירה "
    "שמתאימה לסינון שלך.\n\n"
    "פקודות:\n"
    "/filter — הגדרת/עדכון הסינון שלך\n"
    "/apartments — הדירות התואמות האחרונות\n"
    "/liked — הדירות ששמרת\n"
    "/profile — הפרופיל וההגדרות שלך\n\n"
    "רוצה גם להתחבר באתר (Google/ווטסאפ)? {account_url} 🔗"
)

LINKED = "🎉 חיברתי! אתה כבר רשום ומעודכן אצלי במערכת — מעכשיו תקבל עדכונים גם כאן בטלגרם."

LINK_CONFLICT = (
    "לחשבון הטלגרם הזה כבר יש חשבון נפרד אצלי, אז אי אפשר לחבר אותו לחשבון אחר. "
    "אם זו טעות, כתוב/י לנו דרך /contact."
)

# 2026-09-04 — matches the reference product's own confirmed /start behavior for a returning user
# whose trial/paid access has expired (screenshotted live): a personalized nudge naming their own
# search cities, instead of the plain welcome, pointing straight at /upgrade.
RENEWAL_NEEDED = (
    "היי {name}! 👋 שוב אנחנו?\n\n"
    "שמתי לב שתקופת הגישה שלך הסתיימה, אז ההתראות מושהות כרגע. "
    "{cities_line}רוצה שנחדש את המנוי ונחזור לחפש לך דירה? אפשר ישר כאן: {upgrade_url} 🔥🏠"
)


def _format_cities_he(cities: list[str]) -> str:
    """"ירושלים, הר גילה ומבשרת ציון" — a natural-Hebrew join, not just a comma list."""
    if not cities:
        return ""
    if len(cities) == 1:
        return cities[0]
    return ", ".join(cities[:-1]) + " ו" + cities[-1]


def _upsert_or_link_user_sync(tg_user, link_code: str | None) -> tuple[str, str]:
    """Returns (outcome, reply_text). outcome is "linked" / "conflict" / "normal" / "expired" —
    tests key off outcome; start() just sends reply_text as-is."""
    is_owner = bool(OWNER_TELEGRAM_USER_ID) and str(tg_user.id) == str(OWNER_TELEGRAM_USER_ID)

    with get_session() as session:
        if link_code:
            code_user = resolve_link_code(session, link_code)
            if code_user is not None:
                existing = session.scalar(
                    select(User).where(User.telegram_user_id == tg_user.id)
                )
                if existing is not None and existing.id != code_user.id:
                    # This Telegram account already has its OWN separate account — linking it to
                    # a second one would mean merging two rows' filters/history, which we don't
                    # do automatically. Leave both accounts exactly as they were.
                    return "conflict", LINK_CONFLICT
                code_user.telegram_user_id = tg_user.id
                code_user.telegram_username = tg_user.username
                code_user.first_name = code_user.first_name or tg_user.first_name
                code_user.is_active = True
                session.commit()
                return "linked", LINKED
            # Unknown/expired code — fall through to the normal /start handling below rather
            # than erroring, since a plain "/start" with no payload hits this same path with
            # link_code=None every time.

        user = session.scalar(select(User).where(User.telegram_user_id == tg_user.id))
        if user is None:
            user = User(
                telegram_user_id=tg_user.id,
                telegram_username=tg_user.username,
                first_name=tg_user.first_name,
            )
            session.add(user)
            session.commit()
            return "normal", WELCOME.format(
                name=tg_user.first_name or "",
                account_url=f"{WEBSITE_URL}/account?uid={tg_user.id}",
            )

        # reactivate — mirrors the reference bot re-engaging a paused/"found apartment" user
        user.is_active = True
        user.telegram_username = tg_user.username
        user.first_name = tg_user.first_name
        session.commit()

        # Only a returning user who already onboarded (has a filter) can have "expired" access in
        # any meaningful sense — a brand-new row never reaches here (handled above), and someone
        # mid-onboarding with no filter yet is always still within their fresh trial window.
        if user.filter is not None and not has_full_access(user, is_owner=is_owner):
            cities = _format_cities_he(user.filter.cities)
            reply = RENEWAL_NEEDED.format(
                name=tg_user.first_name or "",
                cities_line=f"מתגעגע/ת לעדכונים על {cities}? " if cities else "",
                upgrade_url=f"{WEBSITE_URL}/upgrade?uid={tg_user.id}",
            )
            return "expired", reply

        return "normal", WELCOME.format(
            name=tg_user.first_name or "",
            account_url=f"{WEBSITE_URL}/account?uid={tg_user.id}",
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    link_code = context.args[0] if context.args else None
    logger.info(
        "/start invoked by telegram_user_id=%s (link_code=%s)", tg_user.id, bool(link_code)
    )
    # asyncio.to_thread so a slow/blocking DB round-trip doesn't freeze the whole bot - PTB
    # processes updates one at a time by default (max_concurrent_updates=1, see main.py), so a
    # synchronous DB call made directly on the event loop blocks every OTHER user's button press
    # and command for its entire duration, not just this one. See PROJECT_STATE.md's 2026-08-31
    # "bot-wide blocking DB calls" entry for the investigation that found this.
    _outcome, reply_text = await asyncio.to_thread(_upsert_or_link_user_sync, tg_user, link_code)
    await update.message.reply_text(reply_text)
