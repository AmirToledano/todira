"""Shared language handling for the bots (Telegram + WhatsApp) — kept in sync BY HAND with
website/i18n.py's own SUPPORTED_LANGS/DEFAULT_LANG (duplicated, not imported: i18n.py lives under
website/ with ~250 web-page-specific translation keys the bots have no use for, and importing it
here would pull the whole website module graph into bot/scraper processes).

2026-09-26 real owner request: both bots were Hebrew-only — not just their own canned strings, but
Gemini's own generated replies too (the prompt in gemini_client.py explicitly said "write in
Hebrew"). Telegram already tells us the user's own device language for free on every update
(telegram.User.language_code) — Google/every real bot platform surfaces this the same way — so
that channel auto-detects silently. WhatsApp's Cloud API gives no such signal at all, so that
channel asks explicitly once (see website/whatsapp_webhook.py's own language-picker flow)."""
from __future__ import annotations

SUPPORTED_LANGS = ["he", "en", "ru", "fr", "ar"]
DEFAULT_LANG = "he"

# Mirrors website/i18n.py's own RTL_LANGS (same reasoning: Hebrew and Arabic are RTL, the other
# three are LTR) — kept in sync by hand for the same reason SUPPORTED_LANGS/DEFAULT_LANG are: not
# imported across the website/bot process boundary. Used by todira_common/cards.py to decide
# whether a listing-card line needs its own RTL bidi embedding at all (see cards._force_rtl) —
# forcing RTL on an English/Russian/French line would misalign text that's already correctly LTR.
RTL_LANGS = {"he", "ar"}

# Each language's own name, in itself — used for the WhatsApp language-picker rows and for the
# Gemini prompt instruction (so the model sees "Russian", not just the ambiguous two-letter code).
LANGUAGE_NAMES = {
    "he": "Hebrew (עברית)",
    "en": "English",
    "ru": "Russian (Русский)",
    "fr": "French (Français)",
    "ar": "Arabic (العربية)",
}


def normalize_language_code(raw: str | None) -> str | None:
    """Maps a raw IETF/BCP-47 tag (e.g. "en-US", "he", "RU") to one of SUPPORTED_LANGS, or None if
    it doesn't match any of them. Only the primary subtag is compared (before any '-'), matching
    website/i18n.py's own Accept-Language handling — same reasoning, a regional variant like
    "en-GB" should still resolve to "en", not fall through to the default."""
    if not raw:
        return None
    primary = raw.strip().split("-")[0].lower()
    return primary if primary in SUPPORTED_LANGS else None
