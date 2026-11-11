"""Neighbourhood and street names: one comparison form for every spelling, and "did you mean" suggestions.

2026-11-11 (owner: "people can write a thousand variations, someone types קרית יובל and it is really קריית היובל").
Both the filter's names and the listings' names go through name_key() before they are compared (matching.py), and the
bot offers names from a list (suggest()) instead of keeping what was typed.
"""
from __future__ import annotations

import difflib
import gzip
import itertools
import json
import pathlib
import re
import threading
import time
from collections import Counter
from functools import lru_cache

from todira_common.cities import locality_key

_STREET_PREFIX_RE = re.compile(r"^(?:רחוב|רח)\s+")
_NEIGHBOURHOOD_PREFIX_RE = re.compile(r"^(?:שכונת|שכ)\s+")
# The official list and many ads abbreviate the first word ("שד' רוטשילד", "סמ' הפקאן", "מד' הרצל").
_ABBREVIATIONS = {"שד": "שדרות", "סמ": "סמטת", "מד": "מדרגות"}
_ABBREVIATION_RE = re.compile(r"^(שד|סמ|מד)\s+")
_HOUSE_NUMBER_RE = re.compile(r"(?:\s+\d+[א-ת]?)+$")


def _words_key(text: str) -> str:
    # The definite article: "קריית היובל" and "קריית יובל", "רחוב הרצל" and "רחוב רצל" are the same name. Dropped only
    # from words of 3+ letters, so a short word is never emptied.
    words = [w[1:] if len(w) >= 3 and w.startswith("ה") else w for w in text.split()]
    return " ".join(words)


def name_key(text: str | None) -> str:
    """A neighbourhood's comparison form: punctuation, quote marks and case dropped, full and defective spelling alike
    ("קריית"/"קרית", "נווה"/"נוה"), "שכונת" in front dropped, the definite article dropped."""
    key = locality_key(text).lower()
    key = _NEIGHBOURHOOD_PREFIX_RE.sub("", key)
    return _words_key(key)


_PARTS_RE = re.compile(r"\s*[,/]\s*|\s+[-–]\s+")


def neighbourhood_parts(text: str | None) -> list[str]:
    """The names inside a combined neighbourhood ("חומת שמואל, הר חומה", "מחנה יהודה - לב העיר"): sources often write two
    neighbourhoods in one, and someone who picks either one wants that listing."""
    return [part.strip() for part in _PARTS_RE.split(text or "") if part.strip()]


def neighbourhood_keys(text: str | None) -> frozenset[str]:
    """name_key of the whole neighbourhood and of each name inside it ({""} when the listing states none)."""
    return frozenset({name_key(text), *(name_key(part) for part in neighbourhood_parts(text))})


def street_key(text: str | None) -> str:
    """A street's comparison form: "רחוב הרצל 12", "רח' הרצל 12/3", "הרצל 12א" and "הרצל" are one street, "שד' רוטשילד" and
    "שדרות רוטשילד" too. The house number goes only when a name is left in front of it ("רחוב 12" stays)."""
    key = locality_key(text).lower()
    key = _STREET_PREFIX_RE.sub("", key)
    key = _ABBREVIATION_RE.sub(lambda m: _ABBREVIATIONS[m.group(1)] + " ", key)
    without_number = _HOUSE_NUMBER_RE.sub("", key)
    key = without_number if without_number and not without_number.isdigit() else key
    return _words_key(key)


def suggest(typed: str, names, key=name_key, limit: int = 6) -> list[str]:
    """Names from `names` (most common first) that the typed text most likely means: the same name in any spelling,
    then names that start with or contain it, then close spellings. Order of `names` breaks ties."""
    wanted = key(typed)
    if not wanted:
        return []
    exact, starts, contains, keyed = [], [], [], {}
    for name in names:
        k = key(name)
        if not k:
            continue
        keyed.setdefault(k, name)
        if k == wanted:
            exact.append(name)
        elif k.startswith(wanted) or any(w.startswith(wanted) for w in k.split()):
            starts.append(name)
        elif wanted in k:
            contains.append(name)
    picked = list(dict.fromkeys(exact + starts + contains))
    if len(picked) < limit:
        close = difflib.get_close_matches(wanted, list(keyed), n=limit, cutoff=0.72)
        picked += [keyed[k] for k in close if keyed[k] not in picked]
    # one spelling per name: a listing spelling and the official one of the same street are offered once
    seen, out = set(), []
    for name in picked:
        k = key(name)
        if k in seen:
            continue
        seen.add(k)
        out.append(name)
    return out[:limit]


_STREETS_FILE = pathlib.Path(__file__).resolve().parent / "assets" / "streets.json.gz"


@lru_cache(maxsize=1)
def _official_streets() -> dict[str, list[str]]:
    """{locality spelling: [street names]} from the official list (scripts/build_streets.py). Empty if not built."""
    try:
        with gzip.open(_STREETS_FILE, "rt", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def official_streets(city: str) -> list[str]:
    return _official_streets().get(city, [])


_NAMES_TTL = 3600.0
_names_cache: dict[str, tuple[float, list[str]]] = {}
_names_lock = threading.Lock()


def city_neighbourhoods(session, city: str) -> list[str]:
    """The neighbourhoods our live listings name in `city`, commonest first (kept for an hour). A combined name ("חומת
    שמואל, הר חומה") counts for each name in it; spellings of one name are counted together under its commonest
    spelling. A name needs 2+ listings. Read from our own listings table only."""
    return _city_names(session, city, "neighborhood")


def city_streets(session, city: str) -> list[str]:
    """The official streets of `city` (the ones our listings use most first). For a locality the official list does
    not have, the street names our live listings use there."""
    return official_streets(city) or _city_names(session, city, "street")


def _city_names(session, city: str, column: str) -> list[str]:
    cache_key = f"{column}|{city}"
    with _names_lock:
        hit = _names_cache.get(cache_key)
    if hit is not None and time.monotonic() - hit[0] < _NAMES_TTL:
        return hit[1]
    from sqlalchemy import func, select

    from todira_common.models import Listing

    raw = func.btrim(getattr(Listing, column))
    rows = session.execute(
        select(raw, func.count())
        .where(Listing.city == city, Listing.is_delisted.is_(False), Listing.duplicate_of_id.is_(None),
               getattr(Listing, column).is_not(None), raw != "")
        .group_by(raw)
    ).all()
    key_of = name_key if column == "neighborhood" else street_key
    counts: Counter = Counter()
    spellings: dict[str, Counter] = {}
    for text, count in rows:
        for part in neighbourhood_parts(text) if column == "neighborhood" else [text]:
            key = key_of(part)
            if not key or ":" in part or part.isdigit():
                continue
            counts[key] += count
            spellings.setdefault(key, Counter())[part] += count
    names = [spellings[key].most_common(1)[0][0] for key, count in counts.most_common() if count >= 2]
    with _names_lock:
        _names_cache[cache_key] = (time.monotonic(), names)
    return names


def suggest_places(session, kind: str, typed_names, cities, limit: int = 8) -> list[tuple[str, str]]:
    """(city, name) pairs the typed names most likely mean, a few from each city in turn. `kind` is "neighborhood" or
    "street". Shared by the bot's "did you mean" buttons and the site's street search."""
    is_street = kind == "street"
    key = street_key if is_street else name_key
    lists = {city: (city_streets if is_street else city_neighbourhoods)(session, city) for city in cities}
    found: list[tuple[str, str]] = []
    for typed in typed_names:
        per_city = [[(city, name) for name in suggest(typed, names, key=key, limit=limit)] for city, names in lists.items()]
        for group in itertools.zip_longest(*per_city):
            found.extend(item for item in group if item and item not in found)
    return found[:limit]
