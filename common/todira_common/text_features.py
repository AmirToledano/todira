"""Card fields read out of an ad's own free text (2026-10-09, owner request).

Komo and Facebook ads, and many Yad2 and Homeless ones, state the floor ("קומה 3 מתוך 5"), the building height, whether there is
parking / an elevator / a balcony / a safe room, whether pets are allowed, whether it is a garden apartment, a penthouse or a private
house, and the entry date in the description text rather than in a structured field. This reads them out of the text with plain
pattern rules (no model call, no cost — the same choice scraper/facebook_groups_text_parser.py made for Group posts).

Contract — conservative on purpose, because a wrong value is worse than a missing one (a wrong `False` hides an ad from users whose
filter requires the feature):
- a field is returned ONLY when the text states it; nothing is guessed;
- a feature is `True` when mentioned plainly, `False` only on an explicit negation right next to the word ("ללא חניה", "אין מעלית");
- when the text both affirms and denies the same thing, or says something that is not a statement about THIS flat ("חניה ברחוב",
  "אפשרות לחניה", "מטבח מרוהט"), the field is left out;
- `missing_updates(listing)` returns only columns the listing has no value for, so a structured source (Yad2's item JSON, Komo's
  amenity list) always wins over the text.

Returned keys are Listing columns: floor, floor_total, has_parking, has_elevator, has_balcony, pets_allowed, is_renovated,
is_roommate_friendly, safe_room_type, furniture, property_type, move_in_date, move_in_note."""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

_NIQQUD_RE = re.compile(r"[֑-ׇ‎‏]")
_SPACES_RE = re.compile(r"[ \t\r\f\v ]+")
_CLAUSE_SPLIT_RE = re.compile(r"[.,;!?\n•|]|(?:^|\s)(?:ו?עם|ו?כולל|ו?יש|אבל|אך|וגם|למרות)(?=\s|$)")
_NEGATION_RE = re.compile(r"(?:^|[^א-ת])(?:ללא|בלי|אין|לא|בלא|חסר(?:ה)?)(?:[^א-ת]|$)")

_MAX_FLOOR = 60

_ORDINAL_FLOORS = {
    "ראשונה": 1, "שנייה": 2, "שניה": 2, "שלישית": 3, "רביעית": 4, "חמישית": 5,
    "שישית": 6, "שביעית": 7, "שמינית": 8, "תשיעית": 9, "עשירית": 10,
}
_LETTER_FLOORS = {"א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9, "י": 10}

_MONTHS = {
    "ינואר": 1, "פברואר": 2, "מרץ": 3, "מרס": 3, "אפריל": 4, "מאי": 5, "יוני": 6,
    "יולי": 7, "אוגוסט": 8, "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12,
}


def _normalize(text: str) -> str:
    cleaned = _NIQQUD_RE.sub("", text)
    for src, dst in (("״", '"'), ("”", '"'), ("“", '"'), ("׳", "'"), ("’", "'"), ("‘", "'"), ("–", "-"), ("—", "-")):
        cleaned = cleaned.replace(src, dst)
    return _SPACES_RE.sub(" ", cleaned)


def _clause_before(text: str, pos: int, window: int = 18) -> str:
    """The words right before `pos`, cut at the last clause break, so a negation in an earlier sentence never reaches this word."""
    return _CLAUSE_SPLIT_RE.split(text[max(0, pos - window):pos])[-1]


def _negated(text: str, pos: int) -> bool:
    return _NEGATION_RE.search(" " + _clause_before(text, pos) + " ") is not None


def _affirm_or_deny(text: str, pattern: re.Pattern[str], *, skip_after: re.Pattern[str] | None = None,
                    skip_before: re.Pattern[str] | None = None) -> bool | None:
    """True if the word is mentioned plainly, False if only mentioned with a negation right before it, None if absent,
    contradictory or not a statement about this flat."""
    positive = negative = False
    for match in pattern.finditer(text):
        if skip_after is not None and skip_after.match(text[match.end():match.end() + 24]):
            continue
        before = _clause_before(text, match.start())
        if skip_before is not None and skip_before.search(before):
            continue
        if _negated(text, match.start()):
            negative = True
        else:
            positive = True
    if positive and negative:
        return None
    if positive:
        return True
    if negative:
        return False
    return None


# --- feature words ------------------------------------------------------------------------------------------------

_PARKING_RE = re.compile(r"חני(?:ה|יה|ות|יות)")
# "street parking", "paid parking", "possible parking": not a statement that THIS flat has a parking spot.
_PARKING_SKIP_AFTER_RE = re.compile(r"\s*(?:ב?רחוב|אזורית|ציבורית|בתשלום|קלה|קל\b|כחולה|בקרבת|באזור|בסביבה|קרובה|אפשרית|לא\b)")
_PARKING_SKIP_BEFORE_RE = re.compile(r"(?:אפשרות|אפשר|קל|קלה|בעיית|בעיה)\s*(?:ל|ב|של)?\s*$")
_ELEVATOR_RE = re.compile(r"מעלית|מעליות")
_BALCONY_RE = re.compile(r"מרפס(?:ת|ות)|גזוזטרה")
_SAFE_ROOM_RE = re.compile(r'ממ"?ד|ממד\b|מרחב מוגן')
_SHELTER_RE = re.compile(r"מקלט")
_PETS_RE = re.compile(r'בעלי חיים|בעלי-חיים|בע"ח|חיות מחמד|חיות|כלבים|כלב\b|חתולים|חתול\b')
_PETS_ALLOW_RE = re.compile(r"מותר|ניתן|אפשר|מתאים|מקבלים|ידידותי|מאפשר|בסדר|פט פרנדלי|פט-פרנדלי")
_PETS_DENY_RE = re.compile(r"אסור|ללא|בלי|לא\b|אין\b")
_ROOMMATES_RE = re.compile(r"שותפ(?:ים|ות|ה|ין)|שותף\b")
_RENOVATED_YES_RE = re.compile(r"משופצ(?:ת|ים|ות)|משופץ|שופצה|שופץ|שיפוץ (?:יסודי|כללי|מלא|אחרון|מקיף)")
_RENOVATED_NO_RE = re.compile(r"דורש(?:ת)? שיפוץ|טעונ(?:ה|ת) שיפוץ|זקוק(?:ה)? לשיפוץ|לשיפוץ\b|דורשת התחדשות")
_FURNISHED_PARTIAL_RE = re.compile(r"מרוהט(?:ת)? חלקית|ריהוט חלקי|חלקית מרוהט")
_UNFURNISHED_RE = re.compile(r"לא מרוהט(?:ת)?|ללא ריהוט|בלי ריהוט|לא כולל ריהוט|ריקה מריהוט|ריק(?:ה)? מריהוט")
_FURNISHED_RE = re.compile(r"מרוהט(?:ת|ים)?|כולל ריהוט|עם ריהוט")
_KITCHEN_BEFORE_RE = re.compile(r"מטבח\s*$")

_PROPERTY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("garden_apartment", re.compile(r"דירת גן")),
    ("penthouse", re.compile(r"פנטהאוז|פנטהאוס|דירת גג")),
    ("private_house", re.compile(r"(?<![א-ת])(?:בית פרטי|וילה|קוטג'?|בית דו[- ]?משפחתי|דו[- ]?משפחתי)(?![א-ת])")),
    ("studio", re.compile(r"סטודיו")),
    ("housing_unit", re.compile(r"יחידת דיור")),
)
_PROPERTY_SKIP_BEFORE_RE = re.compile(r"(?:ליד|קרוב|בקרבת|מול|רחוב|רח'|שכונת|שכונה)\s*$")

# --- floors -------------------------------------------------------------------------------------------------------

_FLOOR_NUMBER_RE = re.compile(r"קומ[הת]\s*(\d{1,2})(?!\d)(?:\s*(?:מתוך|מ-|מ|/|מבין)\s*(\d{1,2})(?!\d))?")
_FLOOR_GROUND_RE = re.compile(r"קומת\s*קרקע|קומה\s*קרקע|קומה\s*0\b")
_FLOOR_ORDINAL_RE = re.compile(r"קומ[הת]\s*ה?(" + "|".join(_ORDINAL_FLOORS) + r")")
_FLOOR_LETTER_RE = re.compile(r"קומה\s+([א-י])'")
_BUILDING_HEIGHT_RE = re.compile(r"(?:בניין|בנין|בית|מבנה)\s*(?:בן|של|עם|מורכב מ)?\s*(\d{1,2})\s*קומות")
_TOTAL_AFTER_FLOOR_WORDS_RE = re.compile(r"מתוך\s*(\d{1,2})\s*קומות")


def _floors(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    ground = _FLOOR_GROUND_RE.search(text)
    number = _FLOOR_NUMBER_RE.search(text)
    ordinal = _FLOOR_ORDINAL_RE.search(text)
    letter = _FLOOR_LETTER_RE.search(text)
    floor: int | None = None
    total: int | None = None
    if ground:
        floor = 0
    elif number:
        floor = int(number.group(1))
        if number.group(2):
            total = int(number.group(2))
    elif ordinal:
        floor = _ORDINAL_FLOORS[ordinal.group(1)]
    elif letter:
        floor = _LETTER_FLOORS[letter.group(1)]
    if total is None:
        height = _BUILDING_HEIGHT_RE.search(text) or _TOTAL_AFTER_FLOOR_WORDS_RE.search(text)
        if height:
            total = int(height.group(1))
    if floor is not None and floor > _MAX_FLOOR:
        floor = None
    if total is not None and not 1 <= total <= _MAX_FLOOR:
        total = None
    if floor is not None and total is not None and floor > total:
        total = None  # "קומה 5 מתוך 4" is a typo — neither is trusted beyond the floor itself
    if floor is not None:
        out["floor"] = floor
    if total is not None:
        out["floor_total"] = total
    return out


# --- entry date ---------------------------------------------------------------------------------------------------

_ENTRY_IMMEDIATE_RE = re.compile(r"כניסה מיידית|כניסה מידית|פינוי מיידי|פנוי(?:ה)? מיידית|פנוי(?:ה)? מיד\b|כניסה מיד\b|כניסה מיידי")
_ENTRY_FLEXIBLE_RE = re.compile(r"כניסה גמישה|תאריך כניסה גמיש|כניסה בגמישות|גמישים בכניסה")
# "כניסה מיידית 3.5 חדרים" must not read 3.5 as a date: the gap between the word and the digits may not hold "מיידית", and the
# numbers may not be followed by a rooms / area / price word.
_ENTRY_NOT_A_DATE_AFTER = r"(?!\d)(?!\s*(?:חד|ח'|חדרים|מ\"ר|מטר|₪|ש\"ח|קומ))"
_ENTRY_NUMERIC_RE = re.compile(
    r"כניסה(?P<gap>[^\d\n]{0,14})(?P<d>\d{1,2})[./](?P<m>\d{1,2})(?:[./](?P<y>\d{2,4}))?" + _ENTRY_NOT_A_DATE_AFTER
)
_ENTRY_MONTH_RE = re.compile(
    r"כניסה(?P<gap>[^\d\n]{0,14})(?P<d>\d{1,2})\s*(?:ל|ב)?-?(?P<mon>" + "|".join(_MONTHS) + r")(?:\s*(?P<y>\d{4}))?"
)


def _entry(text: str, today: dt.date) -> dict[str, Any]:
    day = month = year = None
    match = _ENTRY_NUMERIC_RE.search(text)
    if match and "מיידי" not in match.group("gap") and "מידית" not in match.group("gap"):
        day, month = int(match.group("d")), int(match.group("m"))
        year = int(match.group("y")) if match.group("y") else None
    else:
        match = _ENTRY_MONTH_RE.search(text)
        if match and "מיידי" not in match.group("gap"):
            day, month = int(match.group("d")), _MONTHS[match.group("mon")]
            year = int(match.group("y")) if match.group("y") else None
    if day is not None:
        if year is not None and year < 100:
            year += 2000
        try:
            if year is None:
                candidate = dt.date(today.year, month, day)
                if candidate < today:
                    candidate = dt.date(today.year + 1, month, day)
            else:
                candidate = dt.date(year, month, day)
        except ValueError:
            return {}
        if candidate.year > today.year + 3:
            return {}
        if candidate > today:
            return {"move_in_date": candidate}
        return {"move_in_note": "מיידית"}
    if _ENTRY_IMMEDIATE_RE.search(text):
        return {"move_in_note": "מיידית"}
    if _ENTRY_FLEXIBLE_RE.search(text):
        return {"move_in_note": "גמיש"}
    return {}


# --- the public API -----------------------------------------------------------------------------------------------


def _pets(text: str) -> bool | None:
    allowed = denied = False
    for match in _PETS_RE.finditer(text):
        around = text[max(0, match.start() - 24):match.end() + 24]
        before = _clause_before(text, match.start(), window=24)
        after = _CLAUSE_SPLIT_RE.split(text[match.end():match.end() + 24])[0]
        if _PETS_DENY_RE.search(before) or _PETS_DENY_RE.search(after):
            denied = True
        elif _PETS_ALLOW_RE.search(around):
            allowed = True
    if allowed and denied:
        return None
    return True if allowed else (False if denied else None)


def _furniture(text: str) -> str | None:
    if _FURNISHED_PARTIAL_RE.search(text):
        return None
    if _UNFURNISHED_RE.search(text):
        return "unfurnished"
    for match in _FURNISHED_RE.finditer(text):
        if _KITCHEN_BEFORE_RE.search(_clause_before(text, match.start(), window=10)):
            continue
        if _negated(text, match.start()):
            return None
        return "furnished"
    return None


def _property_type(text: str) -> str | None:
    found: set[str] = set()
    for name, pattern in _PROPERTY_RULES:
        for match in pattern.finditer(text):
            if _PROPERTY_SKIP_BEFORE_RE.search(_clause_before(text, match.start(), window=12)):
                continue
            if _negated(text, match.start()):
                continue
            found.add(name)
    return found.pop() if len(found) == 1 else None


def features_from_text(text: str | None, *, today: dt.date | None = None) -> dict[str, Any]:
    """Listing-column values the text states. {} when `text` is empty or states nothing usable. Never raises."""
    if not text or not text.strip():
        return {}
    try:
        return _features(_normalize(text), today or dt.date.today())
    except Exception:  # a parsing surprise must never break a scrape or a notification
        return {}


def _features(text: str, today: dt.date) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out.update(_floors(text))
    out.update(_entry(text, today))

    flags = (
        ("has_parking", _affirm_or_deny(text, _PARKING_RE, skip_after=_PARKING_SKIP_AFTER_RE, skip_before=_PARKING_SKIP_BEFORE_RE)),
        ("has_elevator", _affirm_or_deny(text, _ELEVATOR_RE)),
        ("has_balcony", _affirm_or_deny(text, _BALCONY_RE)),
        ("pets_allowed", _pets(text)),
        ("is_roommate_friendly", _affirm_or_deny(text, _ROOMMATES_RE)),
    )
    for column, value in flags:
        if value is not None:
            out[column] = value

    safe_room = _affirm_or_deny(text, _SAFE_ROOM_RE)
    shelter = _affirm_or_deny(text, _SHELTER_RE)
    if safe_room is True:
        out["safe_room_type"] = "safe_room"
    elif shelter is True:
        out["safe_room_type"] = "building_shelter"  # also "ללא ממ"ד, מקלט בבניין"
    elif safe_room is False:
        out["safe_room_type"] = "none"

    renovated_no = _RENOVATED_NO_RE.search(text) is not None
    renovated_yes = _RENOVATED_YES_RE.search(text) is not None
    if renovated_yes and not renovated_no:
        out["is_renovated"] = True
    elif renovated_no and not renovated_yes:
        out["is_renovated"] = False

    furniture = _furniture(text)
    if furniture is not None:
        out["furniture"] = furniture
    property_type = _property_type(text)
    if property_type is not None:
        out["property_type"] = property_type
    return out


_COLUMNS = (
    "floor", "floor_total", "has_parking", "has_elevator", "has_balcony", "pets_allowed", "is_renovated",
    "is_roommate_friendly", "safe_room_type", "furniture", "property_type", "move_in_date", "move_in_note",
)


def missing_updates(listing: Any, *, today: dt.date | None = None) -> dict[str, Any]:
    """The text-derived values for the columns `listing` has NO value for (structured sources always win). A move-in note is
    only offered when the listing has neither a move-in date nor a note."""
    found = features_from_text(getattr(listing, "description", None), today=today)
    updates = {column: value for column, value in found.items() if getattr(listing, column, None) is None}
    if getattr(listing, "move_in_date", None) is not None or getattr(listing, "move_in_note", None):
        updates.pop("move_in_date", None)
        updates.pop("move_in_note", None)
    # A floor taken from the text must not contradict a total the listing already has (and vice versa).
    floor = updates.get("floor", getattr(listing, "floor", None))
    total = updates.get("floor_total", getattr(listing, "floor_total", None))
    if floor is not None and total is not None and floor > total:
        updates.pop("floor_total", None) if "floor_total" in updates else updates.pop("floor", None)
    return updates


def apply_missing(listing: Any, *, today: dt.date | None = None) -> dict[str, Any]:
    """Sets the missing columns on `listing` (an ORM row) and returns what was set."""
    updates = missing_updates(listing, today=today)
    for column, value in updates.items():
        setattr(listing, column, value)
    return updates
