"""Language files (2026-11-02, owner: more languages for everyone living in Israel).

The five core languages are written inline in website/i18n.py's TRANSLATIONS and bot_strings.py's BOT_STRINGS. Each
newer language lives in its own JSON file instead, one {key: text} object per language:
website/i18n_langs/<code>.json for the site, todira_common/bot_langs/<code>.json for the bot. Both are read once at
import and merged into the inline tables by merge_lang_files below. tests/test_lang_files.py checks every file."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")
HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^<>]*>")


def source_text(entry: dict[str, str]) -> str:
    """The text a translation must match (placeholders, tags): English when there is one, else Hebrew."""
    return entry.get("en") or entry.get("he") or ""


def same_markup(text: str, source: str) -> bool:
    """Same {placeholders} (any order) and the same HTML tags in the same order as the source."""
    return (sorted(PLACEHOLDER_RE.findall(text)) == sorted(PLACEHOLDER_RE.findall(source))
            and HTML_TAG_RE.findall(text) == HTML_TAG_RE.findall(source))


def read_lang_file(directory: Path, code: str) -> dict[str, str]:
    """The non-empty texts of <directory>/<code>.json, or {} when the file isn't there (yet) or can't be read."""
    path = directory / f"{code}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("unreadable language file %s", path)
        return {}
    if not isinstance(data, dict):
        logger.warning("language file %s is not a {key: text} object", path)
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and v.strip()}


def merge_lang_files(table: dict[str, dict[str, str]], directory: Path, codes: list[str],
                     extra_keys: set[str] | frozenset[str] = frozenset()) -> None:
    """Adds each language file's texts to `table` ({key: {lang: text}}). A key the table doesn't know, or a text whose
    {placeholders} or HTML tags differ from the source, is skipped with a warning, so one bad line can never break a
    page or a message: that key just shows the fallback language. `extra_keys` are known keys the caller reads from
    the file itself (not table entries), so they aren't warned about."""
    for code in codes:
        for key, text in read_lang_file(directory, code).items():
            entry = table.get(key)
            if entry is None:
                if key not in extra_keys:
                    logger.warning("%s.json: unknown key %r", code, key)
                continue
            if not same_markup(text, source_text(entry)):
                logger.warning("%s.json: %r has different placeholders or tags than the source", code, key)
                continue
            entry[code] = text
