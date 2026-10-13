"""Free, offline reading of a free-text apartment search ("מחפש שכירות בתל אביב, 3 חדרים, עד 8,500 ש"ח עם מרפסת").

2026-10-13 (owner report): bot onboarding depended entirely on Gemini, and when its prepaid balance ran out (HTTP 402 on
every model) every new user got only "technical hiccup". The owner asked for something that works without paying per
message and cannot be drained by a user who sends a lot of messages. This reads the common shapes of a search message
with plain rules, so most onboarding messages never reach the AI at all. Gemini (todira_common.gemini_client) stays an
optional helper for messages these rules can't complete.

parse() returns the same fields gemini_client.parse_onboarding_message fills: deal_type ("rent" / "sale" / "sublet" or
None), cities (names from todira_common.cities.CITIES only), rooms_min/rooms_max, price_min/price_max and keywords
(features matched against a listing's description, see todira_common.matching). Anything it isn't sure about is left
empty rather than guessed: an empty field just means the bot asks for it.
"""
from __future__ import annotations

import difflib
import re

from todira_common.bot_strings import bot_text
from todira_common.cities import _ALIASES, CITIES, normalize_spelling
from todira_common.matching import safe_range_update

# --- deal type ---------------------------------------------------------------------------------------------------------

_SUBLET = re.compile(r"סאבלט|סבלט|סב-לט|\bsublet\b|\bsub-let\b", re.IGNORECASE)
_SALE = re.compile(
    r"לקנות|קנייה|קניה|לקניה|לקנייה|למכירה|מכירה|לרכוש|רכישה|רוכש|רוכשת|\bbuy\b|\bbuying\b|\bpurchase\b|\bfor sale\b",
    re.IGNORECASE,
)
_RENT = re.compile(
    r"שכירות|להשכרה|לשכור|שוכר|שוכרת|שכ\"ד|שכ״ד|שכד\b|\brent\b|\brental\b|\brenting\b",
    re.IGNORECASE,
)


def _deal_type(text: str) -> str | None:
    if _SUBLET.search(text):
        return "sublet"
    sale, rent = bool(_SALE.search(text)), bool(_RENT.search(text))
    if sale and not rent:
        return "sale"
    if rent and not sale:
        return "rent"
    return None  # none, or both (ambiguous) - the bot asks


# --- cities ------------------------------------------------------------------------------------------------------------

# Bundled city names that are also everyday Hebrew words or first names ("באזור המרכז" = "in the central area", "במגדל" =
# "in a tower"). Never picked out of a sentence; still accepted when the whole reply is the city (match_city_reply).
_AMBIGUOUS_CITY_WORDS = {"אזור", "מגדל", "עומר", "שלומי", "אפרת", "נשר", "אורנית", "אלקנה", "ברקן"}

# Short forms people write in a sentence that aren't the bundled name itself.
_EXTRA_NAMES: dict[str, str] = {
    "תל אביב": "תל אביב יפו",
    "תל-אביב": "תל אביב יפו",
    "יפו": "תל אביב יפו",
    "מודיעין": "מודיעין מכבים רעות",
    "פרדס חנה": "פרדס חנה כרכור",
    "כרכור": "פרדס חנה כרכור",
    "קדימה": "קדימה צורן",
    "בנימינה": "בנימינה גבעת עדה",
    "יהוד": "יהוד מונוסון",
    "מעלות": "מעלות תרשיחא",
    "יקנעם": "יקנעם עילית",
    "נצרת עילית": "נוף הגליל",
    "tel aviv": "תל אביב יפו",
    "jerusalem": "ירושלים",
    "haifa": "חיפה",
    "beer sheva": "באר שבע",
    "netanya": "נתניה",
    "herzliya": "הרצליה",
    "ramat gan": "רמת גן",
    "givatayim": "גבעתיים",
    "rishon lezion": "ראשון לציון",
    "petah tikva": "פתח תקווה",
    "holon": "חולון",
    "bat yam": "בת ים",
    "ashdod": "אשדוד",
    "raanana": "רעננה",
    "kfar saba": "כפר סבא",
    "modiin": "מודיעין מכבים רעות",
    "eilat": "אילת",
}

_QUOTES = "\"'׳״"
# Hebrew one-letter prefixes glued to a name: ב(in) ל(to) מ(from) ו(and) ה(the) ש(that) כ(like), up to two of them.
_PREFIX = r"(?:[בלמוהשכ]{1,2}-?)?"
_BOUNDARY_BEFORE = r"(?:^|(?<=[\s,.;:!?()\[\]/\-–]))"
_BOUNDARY_AFTER = r"(?=$|[\s,.;:!?()\[\]/\-–])"


def _name_pattern(name: str) -> re.Pattern:
    words = [re.escape(normalize_spelling(w)) for w in name.split()]
    return re.compile(_BOUNDARY_BEFORE + _PREFIX + r"[\s\-]+".join(words) + _BOUNDARY_AFTER, re.IGNORECASE)


def _build_city_patterns() -> list[tuple[re.Pattern, str]]:
    names: dict[str, str] = {c: c for c in CITIES if c not in _AMBIGUOUS_CITY_WORDS}
    names.update(_EXTRA_NAMES)
    # Longest first, so "תל אביב יפו" is taken before "תל אביב" and "קריית אתא" before anything shorter inside it.
    return [(_name_pattern(n), city) for n, city in sorted(names.items(), key=lambda kv: -len(kv[0]))]


_CITY_PATTERNS = _build_city_patterns()
# Abbreviations (ת"א, ב"ש, פ"ת, ראשל"צ...) only count when written with a quote mark, so a plain word never matches.
_ABBREVIATION = re.compile(_BOUNDARY_BEFORE + r"[בלמו]?([א-ת]{1,4}[\"'׳״][א-ת])" + _BOUNDARY_AFTER)


def _cities(text: str) -> list[str]:
    normalized = normalize_spelling(text)
    hits: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for pattern, city in _CITY_PATTERNS:
        for m in pattern.finditer(normalized):
            if any(m.start() < end and start < m.end() for start, end in taken):
                continue
            taken.append((m.start(), m.end()))
            hits.append((m.start(), city))
    for m in _ABBREVIATION.finditer(text):
        city = _ALIASES.get("".join(ch for ch in m.group(1) if ch not in _QUOTES))
        if city:
            hits.append((m.start(), city))
    found: list[str] = []
    for _, city in sorted(hits):  # in the order the message names them
        if city not in found:
            found.append(city)
    return found


def match_city_reply(reply: str) -> list[str]:
    """For a reply to "which city?": the cities named in it, or, when the whole reply is one city name (possibly with a
    common misspelling), that city. Used only when the bot has just asked for a city, so a short answer like "מגדל" or a
    typo like "רמת גם" is taken as a city here even though parse() would never pick it out of a sentence."""
    found = _cities(reply)
    if found:
        return found
    stripped = normalize_spelling("".join(ch for ch in reply.strip() if ch not in _QUOTES)).strip(" .!?,")
    stripped = re.sub(r"^[בלמו]-?(?=\S{3,})", "", stripped) if stripped not in _NORMALIZED_CITIES else stripped
    if stripped in _NORMALIZED_CITIES:
        return [_NORMALIZED_CITIES[stripped]]
    if stripped in _ALIASES:
        return [_ALIASES[stripped]]
    return []


def suggest_cities(reply: str, limit: int = 3) -> list[str]:
    """Closest bundled city names to a reply that matched none (a typo), for the bot to offer as buttons."""
    stripped = normalize_spelling(reply.strip())
    close = difflib.get_close_matches(stripped, list(_NORMALIZED_CITIES), n=limit, cutoff=0.6)
    return [_NORMALIZED_CITIES[c] for c in close]


_NORMALIZED_CITIES = {normalize_spelling(c): c for c in CITIES}

# --- numbers -----------------------------------------------------------------------------------------------------------

_NUMBER_WORDS = {
    "אחד": 1, "אחת": 1, "שניים": 2, "שתיים": 2, "שני": 2, "שתי": 2, "שלושה": 3, "שלוש": 3, "ארבעה": 4, "ארבע": 4,
    "חמישה": 5, "חמש": 5, "שישה": 6, "שש": 6,
}
_NUM = r"\d+(?:[.,]\d+)?"
_ROOM_WORD = r"(?:חדרים|חדר|חד'|חד׳|rooms?|bedrooms?|br)\b"


def _to_float(raw: str) -> float:
    return float(raw.replace(",", "."))


def _rooms(text: str) -> tuple[float | None, float | None]:
    t = text
    for word, value in _NUMBER_WORDS.items():
        t = re.sub(rf"(?<![א-ת]){word}(?![א-ת])(?=\s*(?:וחצי\s*)?חדר)", str(value), t)
    t = re.sub(r"(\d+)\s*וחצי(?=\s*חדר)", lambda m: f"{m.group(1)}.5", t)
    t = re.sub(r"(?<![\d.])חדר\s+וחצי", "1.5 חדרים", t)
    if re.search(r"סטודיו|דירת\s+חדר(?!\S)|studio", t, re.IGNORECASE):
        return 1.0, 1.5
    m = re.search(rf"({_NUM})\s*(?:-|–|עד|או|to)\s*({_NUM})\s*{_ROOM_WORD}", t, re.IGNORECASE)
    if m:
        low, high = sorted((_to_float(m.group(1)), _to_float(m.group(2))))
        return (low, high) if 0 < low <= 12 and high <= 12 else (None, None)
    m = re.search(
        rf"(?:לפחות|מינימום|מעל|at least)\s*({_NUM})\s*{_ROOM_WORD}|({_NUM})\s*\+\s*{_ROOM_WORD}|({_NUM})\s*{_ROOM_WORD}\s*(?:ומעלה|ויותר|\+|or more)",
        t,
        re.IGNORECASE,
    )
    if m:
        value = _to_float(next(g for g in m.groups() if g))
        return (value, None) if 0 < value <= 12 else (None, None)
    m = re.search(rf"({_NUM})\s*{_ROOM_WORD}", t, re.IGNORECASE)
    if m:
        value = _to_float(m.group(1))
        if 0 < value <= 12:
            return value, (value + 0.5 if value == int(value) else value)
    return None, None


_CURRENCY = r"(?:₪|ש\"ח|ש״ח|שח\b|שקל(?:ים)?\b|nis\b|ils\b)"
_NOT_PRICE_UNIT = re.compile(r"^\s*(?:מ\"ר|מ״ר|מטר|מ'|sqm|m2|קומה|קומות|חדר|חד'|ימים|יום|דקות|ק\"מ|%|\+)", re.IGNORECASE)


def _amount(raw: str, suffix: str) -> float | None:
    digits = raw.replace(",", "") if re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw) else raw.replace(",", ".")
    try:
        value = float(digits)
    except ValueError:
        return None
    suffix = suffix.strip().lower()
    if suffix.startswith(("מיליון", "מליון", "m")) and value < 100:
        value *= 1_000_000
    elif suffix.startswith(("אלף", "k", "א'")) and value < 100_000:
        value *= 1_000
    return value


_AMOUNT = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(מיליון|מליון|אלף|k\b|m\b)?"


def _prices(text: str) -> tuple[float | None, float | None]:
    t = text.replace("–", "-")
    m = re.search(rf"(?:בין|מ-?|from)\s*{_AMOUNT}\s*(?:ל-?|עד|and|to|-)\s*{_AMOUNT}", t, re.IGNORECASE)
    if not m:
        m = re.search(rf"{_AMOUNT}\s*-\s*{_AMOUNT}\s*{_CURRENCY}", t, re.IGNORECASE)
    if m:
        low = _amount(m.group(1), m.group(2) or (m.group(4) or ""))
        high = _amount(m.group(3), m.group(4) or "")
        if low and high and 500 <= low <= high:
            return low, high
    m = re.search(rf"(?:עד|מקסימום|תקציב(?:\s+של)?(?:\s+עד)?|לא יותר מ-?|up to|max(?:imum)?|budget)\s*{_AMOUNT}", t, re.IGNORECASE)
    if m:
        value = _amount(m.group(1), m.group(2) or "")
        rest = t[m.end():]
        if value and value >= 500 and not _NOT_PRICE_UNIT.match(rest):
            return None, value
    m = re.search(rf"(?:מ-?|החל מ-?|לפחות|from|at least)\s*{_AMOUNT}\s*{_CURRENCY}", t, re.IGNORECASE)
    if m:
        value = _amount(m.group(1), m.group(2) or "")
        if value and value >= 500:
            return value, None
    for m in re.finditer(rf"{_AMOUNT}\s*({_CURRENCY})?", t, re.IGNORECASE):
        value = _amount(m.group(1), m.group(2) or "")
        rest = t[m.end():]
        if value is None or _NOT_PRICE_UNIT.match(rest) or _NOT_PRICE_UNIT.match(t[m.start(1) + len(m.group(1)):]):
            continue
        bare = not m.group(3) and "," not in m.group(1)
        if bare and (2000 <= value <= 2100 or value >= 100_000_000):
            continue  # a year ("כניסה ב-2026") or a phone number, not a price
        if m.group(3) or value >= 1000:
            return None, value
    return None, None


# --- features ----------------------------------------------------------------------------------------------------------

# word in the message -> the keyword stored on the filter (matched against a listing's description, any of them).
_FEATURES = [
    (r"מרפסת|מרפסות", "מרפסת"),
    (r"חניה|חנייה|חניות", "חניה"),
    (r"מעלית", "מעלית"),
    (r"ממ\"ד|ממ״ד|ממד\b|מרחב מוגן", "ממ\"ד"),
    (r"מחסן", "מחסן"),
    (r"גינה|חצר", "גינה"),
    (r"משופצת|משופץ|שיפוץ", "משופצת"),
    (r"מרוהטת|מרוהט|ריהוט", "מרוהטת"),
    (r"בעלי חיים|חיות מחמד|כלב|חתול", "בעלי חיים"),
    (r"מיזוג|מזגן", "מיזוג"),
    (r"נגישה|נגישות", "נגישה"),
]


# Features the filter stores as a structured requirement (the same switches /filter's buttons set), matched against the
# listing's own fields rather than its description text. The rest stay plain keywords.
FEATURE_FIELDS: dict[str, tuple[str, object]] = {
    "מרפסת": ("require_balcony", True),
    "חניה": ("require_parking", True),
    "מעלית": ("require_elevator", True),
    "בעלי חיים": ("require_pets_allowed", True),
    "משופצת": ("require_renovated", True),
    'ממ"ד': ("safe_room_pref", "safe_room_only"),
    "מרוהטת": ("furniture_pref", "furnished"),
}


def split_features(keywords: list[str]) -> tuple[dict, list[str]]:
    """(filter fields to set, keywords left over) for the keywords parse() returned."""
    fields: dict = {}
    rest: list[str] = []
    for keyword in keywords:
        if keyword in FEATURE_FIELDS:
            field, value = FEATURE_FIELDS[keyword]
            fields[field] = value
        else:
            rest.append(keyword)
    return fields, rest

def _keywords(text: str) -> list[str]:
    return [kw for pattern, kw in _FEATURES if re.search(pattern, text)]


def parse(text: str) -> dict:
    """See the module docstring. Never raises; an unreadable message just comes back with every field empty."""
    text = (text or "").strip()
    rooms_min, rooms_max = _rooms(text)
    price_min, price_max = _prices(text)
    return {
        "deal_type": _deal_type(text),
        "cities": _cities(text),
        "rooms_min": rooms_min,
        "rooms_max": rooms_max,
        "price_min": price_min,
        "price_max": price_max,
        "keywords": _keywords(text),
    }


# --- onboarding state (shared by the Telegram bot and the WhatsApp webhook) ----------------------------------------------


def merge_into(state: dict, found: dict) -> None:
    """Adds what parse() found to an onboarding state from earlier messages (cities and keywords accumulate;
    rooms/price ranges go through safe_range_update so they can never end up inverted)."""
    if found.get("deal_type"):
        state["deal_type"] = found["deal_type"]
    for key in ("cities", "keywords"):
        for value in found.get(key) or []:
            if value not in state[key]:
                state[key] = [*state[key], value]
    if found.get("rooms_min") is not None or found.get("rooms_max") is not None:
        state["rooms_min"], state["rooms_max"] = safe_range_update(
            state["rooms_min"], state["rooms_max"], found.get("rooms_min"), found.get("rooms_max")
        )
    if found.get("price_min") is not None or found.get("price_max") is not None:
        state["price_min"], state["price_max"] = safe_range_update(
            state["price_min"], state["price_max"], found.get("price_min"), found.get("price_max")
        )


def infer_deal_type(state: dict) -> None:
    """Onboarding only (2026-10-13): a budget with no deal word ("עד 8,500 ₪", the promo reel's own message) settles it -
    under NIS 50,000 can only be a monthly rent, NIS 300,000 and up only a purchase. Shown in the summary, so a wrong
    guess is visible and fixable in /filter. Not used in /filter itself, where an explicit choice must never be
    overwritten."""
    if state["deal_type"]:
        return
    price = state["price_max"] if state["price_max"] is not None else state["price_min"]
    if price is None:
        return
    if price < 50_000:
        state["deal_type"] = "rent"
    elif price >= 300_000:
        state["deal_type"] = "sale"


def is_complete(state: dict) -> bool:
    return state["deal_type"] in ("rent", "sale", "sublet") and bool(state["cities"])


def _number(value: float) -> str:
    return f"{value:,.0f}" if value >= 1000 or value == int(value) else f"{value:g}"


def summary(state: dict, lang: str) -> str:
    """"שכירות · ירושלים · 5–5.5 חדרים · עד 8,500 ₪ · מרפסת" - what the bot understood so far."""
    parts = []
    if state["deal_type"]:
        parts.append(bot_text(f"onboarding.deal_{state['deal_type']}", lang))
    if state["cities"]:
        parts.append(", ".join(state["cities"]))
    low, high = state["rooms_min"], state["rooms_max"]
    if low is not None and high is not None:
        rooms = _number(low) if low == high else f"{_number(low)}–{_number(high)}"
        parts.append(bot_text("onboarding.rooms", lang, rooms=rooms))
    elif low is not None:
        parts.append(bot_text("onboarding.rooms", lang, rooms=f"{_number(low)}+"))
    elif high is not None:
        parts.append(bot_text("onboarding.rooms_up_to", lang, rooms=_number(high)))
    low, high = state["price_min"], state["price_max"]
    if low is not None and high is not None:
        parts.append(f"₪{_number(low)}–{_number(high)}")
    elif high is not None:
        parts.append(bot_text("onboarding.price_up_to", lang, price=_number(high)))
    elif low is not None:
        parts.append(bot_text("onboarding.price_from", lang, price=_number(low)))
    parts.extend(state["keywords"])
    return " · ".join(parts)
