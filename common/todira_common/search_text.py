"""Free, offline reading of a free-text apartment search ("מחפש שכירות בתל אביב, 3 חדרים, עד 8,500 ש"ח עם מרפסת").

2026-10-13 (owner report): bot onboarding depended entirely on Gemini, and when its prepaid balance ran out (HTTP 402 on
every model) every new user got only "technical hiccup". The owner asked for something that works without paying per
message and cannot be drained by a user who sends a lot of messages. This reads the common shapes of a search message
with plain rules, so most onboarding messages never reach the AI at all. Gemini (todira_common.gemini_client) stays an
optional helper for messages these rules can't complete.

parse() returns the same fields gemini_client.parse_onboarding_message fills: deal_type ("rent" / "sale" / "sublet" or
None), cities (stored names from todira_common.cities.LOCALITIES: every locality, and every locality of a named area), rooms_min/rooms_max, price_min/price_max and keywords
(features matched against a listing's description, see todira_common.matching). Anything it isn't sure about is left
empty rather than guessed: an empty field just means the bot asks for it.
"""
from __future__ import annotations

import difflib
import re

from todira_common.bot_strings import bot_text
from todira_common.cities import (
    _ALIASES,
    CITIES,
    EXTRA_LOCALITIES,
    LOCALITIES,
    REGIONS,
    locality_key,
    normalize_spelling,
    resolve_locality,
)
from todira_common.matching import safe_range_update

# --- deal type ---------------------------------------------------------------------------------------------------------

# 2026-10-21 (owner: "אני רוצה השכרה" was not understood - only "להשכרה" was): every way people write the kind of deal,
# in Hebrew (with and without the usual spelling variants; ב/ו/ל/ש prefixes match on their own, these are plain
# substrings) and in the other languages the bot speaks. Anything still not understood gets the bot's question.
_SUBLET = re.compile(
    r"סאבלט|סבלט|סב-לט|סב לט|סאב לט|סאב-לט|סאבלאט|סבלאט|לטווח קצר|לתקופה קצרה|"
    r"\bsublet\b|\bsub-let\b|\bsub let\b|субаренд|sous-location|sous location",
    re.IGNORECASE,
)
_SALE = re.compile(
    r"לקנות|קנייה|קניה|לקניה|לקנייה|קנית דירה|קניית|קונה דירה|קונים דירה|אני קונה|"
    r"למכירה|מכירה|מכירת|לרכוש|רכישה|רכישת|רוכש|רוכשת|רוכשים|"
    r"להשקעה|השקעה|משכנתא|משכנתה|דירה בבעלות|"
    r"\bbuy\b|\bbuying\b|\bpurchase\b|\bfor sale\b|\bto own\b|"
    r"купить|покупк|продаж|acheter|achat|à vendre|a vendre|شراء|للبيع|اشتري|أشتري",
    re.IGNORECASE,
)
_RENT = re.compile(
    r"שכירות|השכרה|השכרת|השכרות|להשכיר דירה|לשכור|שוכר|שוכרת|שוכרים|שכירה|שכ\"ד|שכ״ד|שכד\b|שכר דירה|"
    r"\brent\b|\brental\b|\brenting\b|\bto let\b|\blease\b|"
    r"аренд|снять|сниму|снимать|louer|loyer|إيجار|ايجار|استئجار|للإيجار|للايجار",
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


def _name_pattern(name: str, prefix_required: bool = False) -> re.Pattern:
    words = [re.escape(normalize_spelling(w)) for w in name.split()]
    prefix = r"[בלמ]-?" if prefix_required else _PREFIX
    return re.compile(_BOUNDARY_BEFORE + prefix + r"[\s\-]+".join(words) + _BOUNDARY_AFTER, re.IGNORECASE)


# Areas (todira_common.cities.REGIONS: regional councils, sub-districts, "גוש דן", "הקריות") picked out of a sentence.
# Multi-word names always ("גוש עציון", "מטה בנימין", "הגליל העליון" / "גליל עליון"); one-word names only these, since
# the others are also everyday words or first names ("גזר", "תמר", "יואב").
_ONE_WORD_REGIONS = {"השרון", "הקריות", "שומרון", "הגלבוע", "משגב", "זבולון", "מנשה", "מגידו", "גולן"}


def _region_spellings(region: str) -> set[str]:
    """"הגליל העליון" is also written "גליל העליון" (after ב: "בגליל העליון") and "גליל עליון"."""
    words = region.split()
    drop = [w[1:] if w.startswith("ה") and len(w) > 3 else w for w in words]
    return {region, " ".join([drop[0], *words[1:]]), " ".join(drop)}


def _build_city_patterns() -> list[tuple[re.Pattern, tuple[str, ...]]]:
    names: dict[str, tuple[str, ...]] = {c: (c,) for c in CITIES if c not in _AMBIGUOUS_CITY_WORDS}
    names.update({spelling: (city,) for spelling, city in _EXTRA_NAMES.items()})
    # 2026-10-13: every other locality whose name has two words or more ("גבעת זאב", "כפר ורדים", "בית אריה"). One-word
    # names are left to the "which city?" reply (match_city_reply): far too many are everyday words ("רחוב", "נווה",
    # "גפן", "דן") to be picked out of a sentence.
    for name in EXTRA_LOCALITIES:
        if len(name.split()) >= 2 and "/" not in name and name not in names:
            names[name] = (name,)
    prefix_only: set[str] = set()
    for region, members in REGIONS.items():
        if len(region.split()) >= 2 or region in _ONE_WORD_REGIONS:
            for spelling in _region_spellings(region):
                names.setdefault(spelling, tuple(members))
                if " " not in spelling and not spelling.startswith("ה"):
                    prefix_only.add(spelling)  # "שרון", "גולן" are also first names: only "בשרון", "בגולן"
    # Longest first, so "תל אביב יפו" is taken before "תל אביב" and "קריית אתא" before anything shorter inside it.
    return [
        (_name_pattern(n, prefix_required=n in prefix_only), found)
        for n, found in sorted(names.items(), key=lambda kv: -len(kv[0]))
    ]


_CITY_PATTERNS = _build_city_patterns()
# Abbreviations (ת"א, ב"ש, פ"ת, ראשל"צ...) only count when written with a quote mark, so a plain word never matches.
_ABBREVIATION = re.compile(_BOUNDARY_BEFORE + r"[בלמו]?([א-ת]{1,4}[\"'׳״][א-ת])" + _BOUNDARY_AFTER)


_PLACE_WORD = re.compile(
    _BOUNDARY_BEFORE + r"[בלמו]?(?:ה?יישוב|ה?ישוב|ה?מושב|ה?קיבוץ|ה?התנחלות|ה?כפר)\s+([א-ת][א-ת\"'׳״\-]{1,20})" + _BOUNDARY_AFTER
)


def _cities(text: str) -> list[str]:
    normalized = normalize_spelling(text)
    hits: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for pattern, cities_found in _CITY_PATTERNS:
        for m in pattern.finditer(normalized):
            if any(m.start() < end and start < m.end() for start, end in taken):
                continue
            taken.append((m.start(), m.end()))
            hits.extend((m.start(), city) for city in cities_found)
    # 2026-10-19: a one-word place is only picked out of a sentence when the sentence says it is a place
    # ("ביישוב קדר", "במושב נורדיה", "בקיבוץ גבעון") - on its own, "קדר" is also a word.
    for m in _PLACE_WORD.finditer(text):
        city = resolve_locality(m.group(1))
        if city:
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
    # 2026-10-13: the whole reply as any locality (official list, listings spellings) or area, with or without a "ב".
    stripped = reply.strip().strip(" .!?,")
    for candidate in (stripped, re.sub(r"^[בלמו]-?(?=\S{3,})", "", stripped)):
        locality = resolve_locality(candidate)
        if locality:
            return [locality]
        region = _REGIONS_BY_KEY.get(locality_key(candidate))
        if region:
            return list(REGIONS[region])
    return []


def suggest_cities(reply: str, limit: int = 3) -> list[str]:
    """Closest locality names to a reply that matched none (a typo), for the bot to offer as buttons - the major cities
    first when they are as close."""
    key = locality_key(reply)
    close = difflib.get_close_matches(key, list(_LOCALITIES_BY_KEY), n=limit, cutoff=0.6)
    return [_LOCALITIES_BY_KEY[c] for c in close]


_LOCALITIES_BY_KEY = {locality_key(c): c for c in reversed(LOCALITIES)}  # reversed: a major city wins a shared key
_REGIONS_BY_KEY = {locality_key(spelling): region for region in REGIONS for spelling in _region_spellings(region)}

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

# (pattern, label shown back to the user, filter field, value). A field of None means a plain keyword, matched against a
# listing's description (todira_common.matching: any of them). The others are the same structured switches /filter's
# buttons set, matched against the listing's own fields. Negative forms come before positive ones ("לא מרוהטת").
_FEATURES: list[tuple[str, str, str | None, object]] = [
    (r"מרפסת|מרפסות", "מרפסת", "require_balcony", True),
    (r"חניה|חנייה|חניות", "חניה", "require_parking", True),
    (r"מעלית", "מעלית", "require_elevator", True),
    (r"ממ\"ד|ממ״ד|ממד\b|מרחב מוגן", 'ממ"ד', "safe_room_pref", "safe_room_only"),
    (r"משופצת|משופץ|אחרי שיפוץ", "משופצת", "require_renovated", True),
    (r"(?:לא|ללא|בלי)\s+ריהוט|לא\s+מרוהטת|לא\s+מרוהט", "בלי ריהוט", "furniture_pref", "unfurnished"),
    (r"מרוהטת|מרוהט|עם\s+ריהוט|ריהוט\s+מלא", "מרוהטת", "furniture_pref", "furnished"),
    (r"בעלי חיים|חיות מחמד|חיית מחמד|כלב|חתול", "בעלי חיים", "require_pets_allowed", True),
    (r"(?:ללא|בלי|לא\s+דרך|לא\s+דרך\s+ה?|בלי\s+דמי|ללא\s+דמי)\s*(?:תיווך|מתווכ\w*)|מבעלים|ישירות\s+מבעל|מבעל\s+הבית",
     "ללא תיווך", "no_brokers", True),
    (r"קומת\s+קרקע|קומה\s+0\b|קומת\s+כניסה", "קומת קרקע", "ground_floor_only", True),
    (r"שותפים|שותפות|לשותפ", "מתאים לשותפים", "require_roommate_friendly", True),
    (r"דירת\s+גן|דירות\s+גן", "דירת גן", "property_types", "garden_apartment"),
    (r"פנטהאוז|פנטהאוס|פנטהאוס|דירת\s+גג|penthouse", "פנטהאוז", "property_types", "penthouse"),
    (r"יחידת\s+דיור|יח[\"״]ד", "יחידת דיור", "property_types", "housing_unit"),
    (r"בית\s+פרטי|קוטג|וילה|דו[\s-]?משפחתי|חד[\s-]?משפחתי", "בית פרטי", "property_types", "private_house"),
    (r"מחסן", "מחסן", None, None),
    (r"גינה|חצר", "גינה", None, None),
    (r"מיזוג|מזגן|מזגנים", "מיזוג", None, None),
    (r"נגישה|נגישות", "נגישה", None, None),
]
# "בלי מעלית", "לא צריך חניה": the feature is not a requirement.
_NEGATION_BEFORE = re.compile(r"(?:בלי|ללא|לא\s+צריך|לא\s+חייב(?:ת)?|אין\s+צורך\s+ב|לא\s+משנה)\s*-?\s*$")


def _features(text: str) -> tuple[dict, list[str], list[str]]:
    """(filter fields, labels to show back, plain keywords) for the features a message asks for."""
    fields: dict = {}
    labels: list[str] = []
    keywords: list[str] = []
    for pattern, label, field, value in _FEATURES:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        negated_feature = field not in ("no_brokers", "furniture_pref")  # these patterns carry their own "without"
        if negated_feature and _NEGATION_BEFORE.search(text[max(0, m.start() - 14):m.start()]):
            continue
        if field is None:
            keywords.append(label)
        elif field == "property_types":
            fields["property_types"] = [*fields.get("property_types", []), value]
        elif field in fields:
            continue  # the negative form above already decided it
        else:
            fields[field] = value
        if label not in labels and field is not None:
            labels.append(label)
    area = re.search(r"(?:לפחות|מעל|מינימום|at least)\s*(\d{2,3})\s*(?:מ\"ר|מ״ר|מטר|מ'|sqm|m2)|(\d{2,3})\s*\+\s*(?:מ\"ר|מ״ר|מטר)|(\d{2,3})\s*(?:מ\"ר|מ״ר|מטר)\s*(?:ומעלה|לפחות|ויותר)", text)
    if area:
        sqm = int(next(g for g in area.groups() if g))
        fields["min_area_sqm"] = sqm
        labels.append(f'{sqm}+ מ"ר')
    floor_min = re.search(r"(?:מקומה|לפחות\s+קומה|מעל\s+קומה)\s*(\d{1,2})|קומה\s*(\d{1,2})\s*(?:ומעלה|\+)", text)
    if floor_min:
        floor = int(next(g for g in floor_min.groups() if g))
        fields["floor_min"] = floor
        labels.append(f"קומה {floor}+")
    floor_max = re.search(r"עד\s+קומה\s*(\d{1,2})", text)
    if floor_max:
        fields["floor_max"] = int(floor_max.group(1))
        labels.append(f"עד קומה {floor_max.group(1)}")
    return fields, labels, keywords


def parse(text: str) -> dict:
    """See the module docstring. Never raises; an unreadable message just comes back with every field empty."""
    text = (text or "").strip()
    rooms_min, rooms_max = _rooms(text)
    price_min, price_max = _prices(text)
    fields, labels, keywords = _features(text)
    return {
        "deal_type": _deal_type(text),
        "cities": _cities(text),
        "rooms_min": rooms_min,
        "rooms_max": rooms_max,
        "price_min": price_min,
        "price_max": price_max,
        "keywords": keywords,
        # structured filter fields (balcony, parking, no brokers, property type, min size, floor...) and their labels
        "fields": fields,
        "labels": labels,
    }


# --- onboarding state (the Telegram bot) --------------------------------------------------------------------------------


def merge_into(state: dict, found: dict) -> None:
    """Adds what parse() found to an onboarding state from earlier messages (cities and keywords accumulate;
    rooms/price ranges go through safe_range_update so they can never end up inverted)."""
    if found.get("deal_type"):
        state["deal_type"] = found["deal_type"]
    if found.get("fields"):
        merged = {**(state.get("fields") or {})}
        for field, value in found["fields"].items():
            if field == "property_types":
                merged[field] = [*merged.get(field, []), *[v for v in value if v not in merged.get(field, [])]]
            else:
                merged[field] = value
        state["fields"] = merged
    for key in ("cities", "keywords", "labels"):
        state.setdefault(key, [])
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
        shown = state["cities"]
        parts.append(", ".join(shown) if len(shown) <= 4 else f"{', '.join(shown[:3])} +{len(shown) - 3}")
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
    parts.extend(state.get("labels") or [])
    parts.extend(state["keywords"])
    return " · ".join(parts)
