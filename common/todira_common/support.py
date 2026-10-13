"""Channel-agnostic "this message is a support/help request, not apartment criteria" detector.
Used by bot/handlers/support.py and the bot's conversation handlers so they all recognize the same
intent from one regex."""
from __future__ import annotations

import re

_HELP_PATTERN = re.compile(
    r"support|customer service|(?:talk|speak) to (?:a )?(?:human|person|someone|representative)|"
    r"נציג|תמיכה|עזרה מ|לדבר עם (?:מישהו|בנאדם|בן אדם|נציג|צוות)|שירות לקוחות|יש לי תלונה|בעיה טכנית",
    re.IGNORECASE,
)


def looks_like_help_request(text: str) -> bool:
    return bool(_HELP_PATTERN.search(text or ""))
