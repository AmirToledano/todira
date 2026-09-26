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


# 2026-09-25: the about.*/accessibility.*/privacy.*/terms.* keys are deliberately he/en only —
# see i18n.py's own "about page"/"accessibility page"/"privacy page"/"terms page" section
# comments. That content was never translated into ru/fr/ar even before it moved into
# TRANSLATIONS (the pre-React templates hardcoded raw he/en text directly, outside the
# TRANSLATIONS/i18n system entirely), so this isn't a forgotten translation, it's the same
# real-content-only scope those pages already documented. Scoped to these prefixes (not a
# blanket exemption) so a future unrelated key missing a language still fails this test.
_PARTIAL_COVERAGE_PREFIXES = ("about.", "accessibility.", "privacy.", "terms.")


def test_every_translation_key_covers_all_supported_languages():
    missing = {
        key: [lang for lang in i18n.SUPPORTED_LANGS if lang not in entry]
        for key, entry in i18n.TRANSLATIONS.items()
        if not key.startswith(_PARTIAL_COVERAGE_PREFIXES)
        if any(lang not in entry for lang in i18n.SUPPORTED_LANGS)
    }
    assert not missing, f"Translation keys missing one or more supported languages: {missing}"


# 2026-09-26 real owner request: a first-time visitor's phone/browser already tells us its
# language on every request via Accept-Language — get_lang() used to ignore it entirely and
# always default to Hebrew. These test the new fallback tier (?lang= > cookie > Accept-Language >
# Hebrew) via real Starlette Request objects, not just the header-parsing helper in isolation, so
# a regression in how get_lang wires the header in would actually fail a test.
from starlette.requests import Request as _StarletteRequest  # noqa: E402


def _request(*, query_string=b"", cookies=None, accept_language=None):
    headers = []
    if accept_language is not None:
        headers.append((b"accept-language", accept_language.encode()))
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers.append((b"cookie", cookie_header.encode()))
    scope = {
        "type": "http", "method": "GET", "path": "/", "query_string": query_string,
        "headers": headers,
    }
    return _StarletteRequest(scope)


def test_get_lang_picks_the_best_matching_language_from_accept_language_header():
    request = _request(accept_language="fr-FR,fr;q=0.9,en;q=0.5")
    assert i18n.get_lang(request) == "fr"


def test_get_lang_ignores_accept_language_entries_not_in_supported_langs():
    # de/es aren't supported — only "he" in this header is, even though it's listed last/lowest.
    request = _request(accept_language="de-DE,es;q=0.9,he;q=0.3")
    assert i18n.get_lang(request) == "he"


def test_get_lang_falls_back_to_hebrew_when_accept_language_matches_nothing_supported():
    request = _request(accept_language="de-DE,es-ES;q=0.9")
    assert i18n.get_lang(request) == "he"


def test_get_lang_prefers_explicit_lang_param_over_accept_language():
    request = _request(query_string=b"lang=ru", accept_language="fr-FR,fr;q=0.9")
    assert i18n.get_lang(request) == "ru"


def test_get_lang_prefers_existing_cookie_over_accept_language():
    request = _request(cookies={"lang": "ar"}, accept_language="fr-FR,fr;q=0.9")
    assert i18n.get_lang(request) == "ar"


def test_get_lang_with_no_accept_language_header_at_all_defaults_to_hebrew():
    request = _request()
    assert i18n.get_lang(request) == "he"
