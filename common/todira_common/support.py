"""Channel-agnostic "this message is a support/help request, not apartment criteria" detector.
Shared by bot/handlers/support.py (Telegram) and website/whatsapp_webhook.py (WhatsApp) so both
channels recognize the same intent instead of maintaining two copies of the same regex — each
channel still does its own escalation (owner notification mechanics differ: python-telegram-bot's
context.bot vs a raw Telegram HTTP call from the website process)."""
from __future__ import annotations

import re

_HELP_PATTERN = re.compile(
    r"support|customer service|(?:talk|speak) to (?:a )?(?:human|person|someone|representative)|"
    r"נציג|תמיכה|עזרה מ|לדבר עם (?:מישהו|בנאדם|בן אדם|נציג|צוות)|שירות לקוחות|יש לי תלונה|בעיה טכנית",
    re.IGNORECASE,
)


def looks_like_help_request(text: str) -> bool:
    return bool(_HELP_PATTERN.search(text or ""))
