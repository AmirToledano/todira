"""Static sanity checks over website/i18n.py's TRANSLATIONS table.

Found live 2026-09-07: 17 Arabic ("ar") entries had the Hebrew brand name "טודירה" pasted
straight into otherwise-Arabic text (and one had a similarly mixed-script "טודי", the dog's own
name) instead of a proper Arabic transliteration ("توديرا"/"تودي") — presumably from copying the
Hebrew string as a starting point for a new translation and not fully replacing it. This is a
static content check, not a rendering test, so it stays cheap and catches the next instance of the
same slip immediately in CI rather than needing a native speaker to notice it on the live site.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("i18n_translations_test", _WEBSITE_DIR / "i18n.py")
i18n = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(i18n)

_HEBREW_RE = re.compile(r"[֐-׿]")


def test_no_hebrew_characters_leak_into_arabic_translations():
    offenders = []
    for key, entry in i18n.TRANSLATIONS.items():
        value = entry.get("ar")
        if value and _HEBREW_RE.search(value):
            offenders.append((key, value))
    assert not offenders, f"Hebrew characters found inside Arabic translation values: {offenders}"


def test_every_translation_key_covers_all_supported_languages():
    missing = {
        key: [lang for lang in i18n.SUPPORTED_LANGS if lang not in entry]
        for key, entry in i18n.TRANSLATIONS.items()
        if any(lang not in entry for lang in i18n.SUPPORTED_LANGS)
    }
    assert not missing, f"Translation keys missing one or more supported languages: {missing}"
