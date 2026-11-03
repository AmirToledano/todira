"""The language files (2026-11-02, owner: more languages for everyone living in Israel).

Spanish, Portuguese, Hindi, Filipino, Thai and Chinese come as JSON files, one {key: text} object per language:
website/i18n_langs/<code>.json for the site and common/todira_common/bot_langs/<code>.json for the bot. These tests
check every file that is there (a broken line is skipped at runtime with a warning, here it fails CI instead), and that
a key no file has yet shows the English text.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_ROOT = Path(__file__).resolve().parent.parent
_WEBSITE_DIR = _ROOT / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("i18n_lang_files_test", _WEBSITE_DIR / "i18n.py")
i18n = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(i18n)

from todira_common import bot_strings, language, lang_files  # noqa: E402

SITE_DIR = _WEBSITE_DIR / "i18n_langs"
BOT_DIR = _ROOT / "common" / "todira_common" / "bot_langs"
DASHES = ("—", "–")  # em dash, en dash: the owner's rule, never in user-facing text


def _site_sources() -> dict[str, str]:
    """Every key a site file may hold, with the text its placeholders and tags must match."""
    sources = {key: lang_files.source_text(entry) for key, entry in i18n.TRANSLATIONS.items()}
    for group, labels in i18n._LABEL_GROUPS.items():
        for value, text in labels["en"].items():
            sources[f"label.{group}.{value}"] = text
    return sources


def _bot_sources() -> dict[str, str]:
    return {key: lang_files.source_text(entry) for key, entry in bot_strings.BOT_STRINGS.items()}


def problems(directory: Path, sources: dict[str, str], codes: list[str]) -> list[str]:
    """Everything wrong with the *.json files in `directory`, as readable lines (empty when all is well)."""
    found = []
    for path in sorted(directory.glob("*.json")):
        if path.stem not in codes:
            found.append(f"{path.name}: {path.stem!r} is not one of the file languages {codes}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            found.append(f"{path.name}: not valid JSON ({exc})")
            continue
        if not isinstance(data, dict):
            found.append(f"{path.name}: must be one {{key: text}} object")
            continue
        for key, text in data.items():
            where = f"{path.name} [{key}]"
            if not isinstance(text, str):
                found.append(f"{where}: the text must be a string")
                continue
            if key not in sources:
                found.append(f"{where}: no such key in the source")
                continue
            source = sources[key]
            got_ph, want_ph = sorted(lang_files.PLACEHOLDER_RE.findall(text)), sorted(lang_files.PLACEHOLDER_RE.findall(source))
            if got_ph != want_ph:
                found.append(f"{where}: placeholders {got_ph} but the source has {want_ph}")
            got_tags, want_tags = lang_files.HTML_TAG_RE.findall(text), lang_files.HTML_TAG_RE.findall(source)
            if got_tags != want_tags:
                found.append(f"{where}: HTML tags {got_tags} but the source has {want_tags}")
            if any(dash in text for dash in DASHES):
                found.append(f"{where}: has an em or en dash")
    return found


def test_both_language_directories_exist():
    assert SITE_DIR.is_dir() and BOT_DIR.is_dir()


def test_every_site_language_file_is_valid():
    found = problems(SITE_DIR, _site_sources(), i18n.FILE_LANGS)
    assert not found, "\n".join(found)


def test_every_bot_language_file_is_valid():
    found = problems(BOT_DIR, _bot_sources(), language.FILE_LANGS)
    assert not found, "\n".join(found)


def test_the_site_and_the_bot_have_the_same_languages():
    assert i18n.SUPPORTED_LANGS == language.SUPPORTED_LANGS
    assert i18n.FILE_LANGS == language.FILE_LANGS
    assert set(i18n.LANG_LABELS) == set(i18n.SUPPORTED_LANGS)


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("Hola {name}, mira <b>esto</b>", True),
        ("<b>esto</b> {name}", True),  # placeholders may move, the words around them do
        ("Hola, mira <b>esto</b>", False),  # a placeholder lost
        ("Hola {nombre}, mira <b>esto</b>", False),  # a placeholder renamed
        ("Hola {name}, mira esto", False),  # a tag lost
        ("Hola {name}, mira <i>esto</i>", False),  # a different tag
        ("Hola {name}, mira <b>esto</b> — ya", False),  # an em dash
    ],
)
def test_the_validator_catches_a_bad_line(tmp_path, text, ok):
    (tmp_path / "es.json").write_text(json.dumps({"k": text}), encoding="utf-8")
    found = problems(tmp_path, {"k": "Hi {name}, look at <b>this</b>"}, ["es"])
    assert (not found) == ok, found


def test_the_validator_catches_an_unknown_key_and_a_wrong_file_name(tmp_path):
    (tmp_path / "es.json").write_text(json.dumps({"nope": "x"}), encoding="utf-8")
    (tmp_path / "de.json").write_text(json.dumps({}), encoding="utf-8")
    found = problems(tmp_path, {"k": "x"}, ["es"])
    assert len(found) == 2


def test_a_file_text_is_merged_and_a_missing_one_shows_english(tmp_path):
    (tmp_path / "es.json").write_text(json.dumps({
        "a": "Hola {name}",
        "b": "sin marcador",  # placeholder lost: skipped, so English shows
        "unknown": "x",  # not in the table: skipped
    }), encoding="utf-8")
    table = {
        "a": {"he": "שלום {name}", "en": "Hello {name}"},
        "b": {"he": "שלום {name}", "en": "Hello {name}"},
        "c": {"he": "שלום", "en": "Hello"},
    }
    lang_files.merge_lang_files(table, tmp_path, ["es", "pt"])  # pt.json isn't there: nothing happens
    assert table["a"]["es"] == "Hola {name}"
    assert "es" not in table["b"] and "es" not in table["c"]
    assert i18n.pick_text(table["b"], "es") == "Hello {name}"
    assert i18n.pick_text(table["c"], "pt") == "Hello"
    assert i18n.pick_text({"he": "שלום"}, "zh") == "שלום"  # no English either: Hebrew
    assert i18n.pick_text({"he": "שלום", "en": "Hello"}, "ru") == "שלום"  # a core language keeps its Hebrew fallback


def test_a_new_language_shows_english_until_its_file_has_the_text():
    t = i18n.make_translator("th")
    entry = i18n.TRANSLATIONS["meta.title_home"]
    assert t("meta.title_home") == (entry.get("th") or entry["en"])
    assert bot_strings.bot_text("language.changed", "hi") == (
        bot_strings.BOT_STRINGS["language.changed"].get("hi") or bot_strings.BOT_STRINGS["language.changed"]["en"]
    )
    assert bot_strings.bot_text("language.changed", "ru") == bot_strings.BOT_STRINGS["language.changed"]["ru"]
    assert bot_strings.bot_text("language.changed", None) == bot_strings.BOT_STRINGS["language.changed"]["he"]


def test_the_filter_labels_exist_for_every_language():
    for labels in i18n._LABEL_GROUPS.values():
        for code in i18n.SUPPORTED_LANGS:
            assert set(labels[code]) == set(labels["en"]), code


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("es-419", "es"), ("pt-BR", "pt"), ("pt_PT", "pt"), ("hi", "hi"), ("fil", "fil"), ("tl", "fil"),
        ("th-TH", "th"), ("zh-CN", "zh"), ("zh-Hans", "zh"), ("zh-hans-cn", "zh"), ("iw", "he"), ("de", None),
    ],
)
def test_telegram_language_codes_map_to_ours(raw, code):
    assert language.normalize_language_code(raw) == code
