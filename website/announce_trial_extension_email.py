"""One-time email to Google-only users (no Telegram, so the bot can't tell them): everyone registered before the change
has full, free access until 26.10 (migration 0031) - 2026-10-19, owner request. Same recipients rule as the Telegram
message (bot/announce_trial_extension.py): created before the change, inside the trial now, no paid pass, no free access.
Each email that Resend accepts is marked on users.trial_gift_emailed_at, so a second run never repeats it.

Run by .github/workflows/announce-trial-extension-email.yaml in the website pod ("dry-run" counts, "send" sends).
Prints counts only - never an address; the repository and its logs are public."""
from __future__ import annotations

import datetime as dt
import html
import sys
import time
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select

from todira_common import email_client
from todira_common.db import get_session
from todira_common.models import User

CHANGE_AT = dt.datetime(2026, 10, 19, 0, 0, tzinfo=dt.timezone.utc)
SITE = "https://todira.app"


def recipients(session, now: dt.datetime) -> list[User]:
    return list(session.scalars(select(User).where(
        User.telegram_user_id.is_(None),
        User.google_email.is_not(None),
        User.trial_gift_emailed_at.is_(None),
        User.free_access_granted.is_(False),
        User.created_at < CHANGE_AT,
        User.trial_ends_at > now,
        or_(User.paid_until.is_(None), User.paid_until <= now),
    )))


def message_for(first_name: str | None, trial_ends_at: dt.datetime) -> tuple[str, str, str]:
    """(subject, html, text) - the wording the owner saw before sending."""
    date = trial_ends_at.astimezone(ZoneInfo("Asia/Jerusalem")).strftime("%d.%m")
    hello = f"היי {first_name}," if first_name else "היי,"
    subject = "🎁 פתחנו לך עוד 7 ימי גישה מלאה בטודירה"
    lines = [
        hello,
        f"חדשות טובות: פתחנו לך עוד 7 ימים של גישה מלאה וחינמית לטודירה, עד {date}.",
        "בזמן הזה תקבל/י כל דירה חדשה שמתאימה לחיפוש שלך, עם הפרטים המלאים והקישור למודעה המקורית.",
    ]
    text = "\n".join(lines) + f"\n\nלכל הדירות שמתאימות לך: {SITE}/apartments\n\nבהצלחה בחיפוש,\nצוות טודירה"
    body = "".join(f"<p style=\"margin:0 0 12px\">{html.escape(line)}</p>" for line in lines)
    page = (
        "<div dir=\"rtl\" style=\"font-family:Arial,sans-serif;font-size:16px;line-height:1.6;color:#173c40;"
        "max-width:520px;margin:0 auto;padding:24px\">"
        f"{body}"
        f"<p style=\"margin:20px 0\"><a href=\"{SITE}/apartments\" style=\"background:#d9a441;color:#2b2111;"
        "padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:bold\">לדירות שלי</a></p>"
        "<p style=\"margin:0\">בהצלחה בחיפוש,<br>צוות טודירה</p></div>"
    )
    return subject, page, text


def main(send: bool) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    with get_session() as session:
        users = recipients(session, now)
        print(f"Google-only users the email is for: {len(users)} | email sending configured: {email_client.enabled()}")
        if not send:
            print("dry run - nothing sent")
            return
        if not email_client.enabled():
            print("RESEND_API_KEY is not set - nothing sent")
            return
        sent = failed = 0
        for user in users:
            subject, page, text = message_for(user.first_name, user.trial_ends_at)
            if email_client.send(user.google_email, subject, page, text):
                user.trial_gift_emailed_at = dt.datetime.now(dt.timezone.utc)
                session.commit()
                sent += 1
            else:
                failed += 1
            time.sleep(0.6)  # Resend's free plan allows 2 requests a second
        print(f"sent: {sent} | failed: {failed}")


if __name__ == "__main__":
    main(send="--send" in sys.argv[1:])
