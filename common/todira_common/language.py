"""Shared language handling for the bot — kept in sync BY HAND with
website/i18n.py's own SUPPORTED_LANGS/DEFAULT_LANG (duplicated, not imported: i18n.py lives under
website/ with ~250 web-page-specific translation keys the bots have no use for, and importing it
here would pull the whole website module graph into bot/scraper processes).

2026-09-26 real owner request: the bot was Hebrew-only — not just its own canned strings, but
Gemini's own generated replies too (the prompt in gemini_client.py explicitly said "write in
Hebrew"). Telegram already tells us the user's own device language for free on every update
(telegram.User.language_code), so the bot auto-detects it silently.

2026-11-02 (owner): six more languages for everyone living in Israel. CORE_LANGS are written inline in
bot_strings.py; each FILE_LANGS language's bot texts live in todira_common/bot_langs/<code>.json, and a key a file
doesn't have shows the English text, then the Hebrew one."""
from __future__ import annotations

CORE_LANGS = ["he", "en", "ru", "fr", "ar"]
FILE_LANGS = ["es", "pt", "hi", "fil", "th", "zh"]
SUPPORTED_LANGS = CORE_LANGS + FILE_LANGS
DEFAULT_LANG = "he"

# Mirrors website/i18n.py's own RTL_LANGS (same reasoning: Hebrew and Arabic are RTL, all the others
# are LTR) — kept in sync by hand for the same reason SUPPORTED_LANGS/DEFAULT_LANG are: not
# imported across the website/bot process boundary.
RTL_LANGS = {"he", "ar"}

# Each language's English name plus its own name, for the Gemini prompt instruction (so the model sees "Russian",
# not just the ambiguous two-letter code).
LANGUAGE_NAMES = {
    "he": "Hebrew (עברית)",
    "en": "English",
    "ru": "Russian (Русский)",
    "fr": "French (Français)",
    "ar": "Arabic (العربية)",
    "es": "Spanish (Español)",
    "pt": "Brazilian Portuguese (Português)",
    "hi": "Hindi (हिन्दी)",
    "fil": "Filipino (Tagalog)",
    "th": "Thai (ไทย)",
    "zh": "Simplified Chinese (中文)",
}

# Telegram/browser tags whose primary subtag isn't our code: Tagalog is the base of Filipino, and "iw" is the old
# code for Hebrew that some Android phones still send.
_ALIASES = {"tl": "fil", "iw": "he"}


def fallback_langs(lang: str | None) -> tuple[str, ...]:
    """The languages tried, in order, for one text: the asked one, then English for a file language, then Hebrew."""
    if lang in FILE_LANGS:
        return (lang, "en", DEFAULT_LANG)
    return (lang or DEFAULT_LANG, DEFAULT_LANG)


def normalize_language_code(raw: str | None) -> str | None:
    """Maps a raw IETF/BCP-47 tag (e.g. "en-US", "pt-BR", "zh-Hans", "tl", "RU") to one of SUPPORTED_LANGS, or None
    if it doesn't match any of them. Only the primary subtag is compared (before any '-' or '_'), so a regional or
    script variant like "en-GB", "pt-BR" or "zh-CN" resolves to "en"/"pt"/"zh", not to the default."""
    if not raw:
        return None
    primary = raw.strip().replace("_", "-").split("-")[0].lower()
    primary = _ALIASES.get(primary, primary)
    return primary if primary in SUPPORTED_LANGS else None
