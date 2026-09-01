"""Inline-keyboard builders for the /filter conversation. Every submenu ends in a "Back" button
that returns to the root menu (`f:root`) — see plan Section 5 for the menu-driven design this
implements, and handlers/filter_conversation.py for the state machine that drives these.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from dorin_common import cities
from dorin_common.enums import DealType, FurniturePref, PropertyType, SafeRoomPref

DEAL_TYPE_LABELS = {DealType.RENT: "להשכרה", DealType.SALE: "למכירה", DealType.SUBLET: "סאבלט"}
PROPERTY_TYPE_LABELS = {
    PropertyType.APARTMENT: "דירה",
    PropertyType.GARDEN_APARTMENT: "דירת גן",
    PropertyType.PENTHOUSE: "פנטהאוז/גג",
    PropertyType.STUDIO: "סטודיו",
    PropertyType.HOUSING_UNIT: "יחידת דיור",
    PropertyType.PRIVATE_HOUSE: "בית פרטי",
    PropertyType.SHARED_ROOM: "חדר בשותפים",
}
SAFE_ROOM_LABELS = {
    SafeRoomPref.SAFE_ROOM_ONLY: 'ממ"ד בלבד',
    SafeRoomPref.SAFE_ROOM_OR_SHELTER: 'ממ"ד/מקלט',
    SafeRoomPref.ANY: "הכל",
}
FURNITURE_LABELS = {
    FurniturePref.FURNISHED: "מרוהטת",
    FurniturePref.UNFURNISHED: "לא מרוהטת",
    FurniturePref.ANY: "הכל",
}
REQUIREMENT_LABELS = (
    ("require_parking", "🅿️ חניה"),
    ("require_elevator", "🛗 מעלית"),
    ("require_balcony", "🌳 מרפסת"),
    ("require_pets_allowed", "🐾 חיות מחמד"),
    ("require_renovated", "🔨 משופצת"),
    ("require_has_photos", "📷 עם תמונות"),
    ("require_roommate_friendly", "🤝 לשותפים"),
)

CATEGORY_TITLES = {
    "root": "🔧 <b>הסינון שלך</b>",
    "dt": "🏷️ סוג עסקה",
    "pt": "🏠 סוג נכס",
    "loc": "📍 מיקום",
    "locpick": "📍 בחר/י ערים מהרשימה",
    "price": "💰 מחיר",
    "rooms": "🛏️ חדרים",
    "floor": "🏢 קומה",
    "req": "✅ דרישות",
    "safe": "🛡️ מיגון",
    "furn": "🛋️ ריהוט",
    "area": "📏 שטח מינימלי",
    "kw": "🔍 מילות מפתח",
    "move": "📅 תאריך כניסה",
    "adv": "⚙️ מתקדם",
}

BACK_BUTTON = InlineKeyboardButton("⬅️ חזרה", callback_data="f:root")


def _fmt_range(lo, hi, unit: str = "") -> str:
    if lo is None and hi is None:
        return "ללא הגבלה"
    if lo is not None and hi is not None:
        return f"{lo}–{hi}{unit}"
    if lo is not None:
        return f"מ-{lo}{unit}"
    return f"עד {hi}{unit}"


def render_root_summary(draft: dict) -> str:
    active_reqs = [label for attr, label in REQUIREMENT_LABELS if draft.get(attr)]
    lines = [
        CATEGORY_TITLES["root"],
        f"🏷️ סוג עסקה: {DEAL_TYPE_LABELS.get(draft['deal_type'], draft['deal_type'])}",
        "🏠 סוג נכס: "
        + (", ".join(PROPERTY_TYPE_LABELS[p] for p in draft["property_types"]) or "הכל"),
        "📍 ערים: " + (", ".join(draft["cities"]) or "הכל"),
        "💰 מחיר: " + _fmt_range(draft["price_min"], draft["price_max"], " ₪"),
        "🛏️ חדרים: " + _fmt_range(draft["rooms_min"], draft["rooms_max"]),
        "🏢 קומה: "
        + (
            "קרקע בלבד"
            if draft["ground_floor_only"]
            else _fmt_range(draft["floor_min"], draft["floor_max"])
        ),
        "✅ דרישות: " + (", ".join(active_reqs) or "—"),
        "🛡️ מיגון: " + SAFE_ROOM_LABELS.get(draft["safe_room_pref"], "הכל"),
        "🛋️ ריהוט: " + FURNITURE_LABELS.get(draft["furniture_pref"], "הכל"),
        "📏 שטח מינימלי: " + (f"{draft['min_area_sqm']} מ\"ר" if draft["min_area_sqm"] else "—"),
        "🔍 מילות מפתח: " + (", ".join(draft["keywords"]) or "—"),
        "📅 כניסה: " + _fmt_range(draft["move_in_earliest"], draft["move_in_latest"]),
        "⚙️ ללא תיווך: "
        + ("✔" if draft["no_brokers"] else "✘")
        + " · סינון גמיש: "
        + ("✔" if draft["flexible_match"] else "✘"),
    ]
    return "\n".join(lines)


def root_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🏷️ סוג עסקה", callback_data="f:cat:dt"),
            InlineKeyboardButton("🏠 סוג נכס", callback_data="f:cat:pt"),
        ],
        [
            InlineKeyboardButton("📍 מיקום", callback_data="f:cat:loc"),
            InlineKeyboardButton("💰 מחיר", callback_data="f:cat:price"),
        ],
        [
            InlineKeyboardButton("🛏️ חדרים", callback_data="f:cat:rooms"),
            InlineKeyboardButton("🏢 קומה", callback_data="f:cat:floor"),
        ],
        [
            InlineKeyboardButton("✅ דרישות", callback_data="f:cat:req"),
            InlineKeyboardButton("🛡️ מיגון", callback_data="f:cat:safe"),
        ],
        [
            InlineKeyboardButton("🛋️ ריהוט", callback_data="f:cat:furn"),
            InlineKeyboardButton("📏 שטח מינימלי", callback_data="f:cat:area"),
        ],
        [
            InlineKeyboardButton("🔍 מילות מפתח", callback_data="f:cat:kw"),
            InlineKeyboardButton("📅 תאריך כניסה", callback_data="f:cat:move"),
        ],
        [InlineKeyboardButton("⚙️ מתקדם", callback_data="f:cat:adv")],
        [
            InlineKeyboardButton("💾 שמור וחפש", callback_data="f:save"),
            InlineKeyboardButton("❌ ביטול", callback_data="f:cancel"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def single_select_keyboard(options: dict[str, str], current: str, ns: str) -> InlineKeyboardMarkup:
    rows = []
    for value, label in options.items():
        mark = "🔘" if value == current else "⚪"
        rows.append([InlineKeyboardButton(f"{mark} {label}", callback_data=f"f:set:{ns}:{value}")])
    rows.append([BACK_BUTTON])
    return InlineKeyboardMarkup(rows)


def multi_select_keyboard(
    options: dict[str, str], selected: list[str], ns: str
) -> InlineKeyboardMarkup:
    rows = []
    for value, label in options.items():
        mark = "☑️" if value in selected else "⬜"
        rows.append([InlineKeyboardButton(f"{mark} {label}", callback_data=f"f:tog:{ns}:{value}")])
    rows.append([BACK_BUTTON])
    return InlineKeyboardMarkup(rows)


def requirements_keyboard(draft: dict) -> InlineKeyboardMarkup:
    rows = []
    for attr, label in REQUIREMENT_LABELS:
        mark = "☑️" if draft.get(attr) else "⬜"
        rows.append([InlineKeyboardButton(f"{mark} {label}", callback_data=f"f:tog:req:{attr}")])
    rows.append([BACK_BUTTON])
    return InlineKeyboardMarkup(rows)


def location_keyboard(draft: dict) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📋 הוסף עיר מרשימה", callback_data="f:loc:full")],
        [InlineKeyboardButton("🔍 חיפוש עיר לפי הקלדה", callback_data="f:loc:addcity")],
    ]
    for idx, city in enumerate(draft["cities"]):
        rows.append([InlineKeyboardButton(f"🗑️ {city}", callback_data=f"f:loc:rmc:{idx}")])
    rows.append([BACK_BUTTON])
    return InlineKeyboardMarkup(rows)


def city_picker_keyboard(draft: dict) -> InlineKeyboardMarkup:
    """Full list of every bundled city as a toggleable button (mirrors multi_select_keyboard's
    ☑️/⬜ pattern, same as "סוג נכס") — the primary way to add a city now; typed search (below)
    is a convenience for anyone who'd rather not scroll ~40 buttons, not the only path anymore."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for idx, city in enumerate(cities.CITIES):
        mark = "☑️" if city in draft["cities"] else "⬜"
        row.append(InlineKeyboardButton(f"{mark} {city}", callback_data=f"f:loc:togc:{idx}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔍 חיפוש לפי הקלדה", callback_data="f:loc:addcity")])
    rows.append([InlineKeyboardButton("⬅️ חזרה", callback_data="f:cat:loc")])
    return InlineKeyboardMarkup(rows)


def city_search_results_keyboard(matches: list[str]) -> InlineKeyboardMarkup:
    """Renders typed-search candidates (from cities.find_matches) as tappable buttons instead of
    silently picking the first match — a user chooses explicitly which city they meant, same as
    tapping a box in city_picker_keyboard. `matches` are always members of cities.CITIES, so
    `.index()` never raises."""
    rows = [
        [InlineKeyboardButton(f"➕ {city}", callback_data=f"f:loc:togc:{cities.CITIES.index(city)}")]
        for city in matches
    ]
    rows.append([InlineKeyboardButton("⬅️ חזרה", callback_data="f:cat:loc")])
    return InlineKeyboardMarkup(rows)


def price_keyboard(draft: dict) -> InlineKeyboardMarkup:
    req_mark = "☑️" if draft["require_price"] else "⬜"
    rows = [
        [
            InlineKeyboardButton(f"מינימום: {draft['price_min'] or '—'}", callback_data="f:price:min"),
            InlineKeyboardButton(f"מקסימום: {draft['price_max'] or '—'}", callback_data="f:price:max"),
        ],
        [InlineKeyboardButton(f"{req_mark} רק דירות עם מחיר", callback_data="f:price:reqtoggle")],
        [BACK_BUTTON],
    ]
    return InlineKeyboardMarkup(rows)


def rooms_keyboard(draft: dict) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(f"מינימום: {draft['rooms_min'] or '—'}", callback_data="f:rooms:min"),
            InlineKeyboardButton(f"מקסימום: {draft['rooms_max'] or '—'}", callback_data="f:rooms:max"),
        ],
        [BACK_BUTTON],
    ]
    return InlineKeyboardMarkup(rows)


def floor_keyboard(draft: dict) -> InlineKeyboardMarkup:
    ground_mark = "☑️" if draft["ground_floor_only"] else "⬜"
    rows = [
        [
            InlineKeyboardButton(f"מינימום: {draft['floor_min'] or '—'}", callback_data="f:floor:min"),
            InlineKeyboardButton(f"מקסימום: {draft['floor_max'] or '—'}", callback_data="f:floor:max"),
        ],
        [InlineKeyboardButton(f"{ground_mark} קומת קרקע בלבד", callback_data="f:floor:ground")],
        [BACK_BUTTON],
    ]
    return InlineKeyboardMarkup(rows)


def area_keyboard(draft: dict) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"שטח מינימלי: {draft['min_area_sqm'] or '—'} מ\"ר", callback_data="f:area:set"
            )
        ],
        [BACK_BUTTON],
    ]
    return InlineKeyboardMarkup(rows)


def keywords_keyboard(draft: dict) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("✏️ ערוך מילות מפתח", callback_data="f:kw:set")],
        [InlineKeyboardButton("🗑️ נקה", callback_data="f:kw:clear")],
        [BACK_BUTTON],
    ]
    return InlineKeyboardMarkup(rows)


def move_in_keyboard(draft: dict) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"מוקדם ביותר: {draft['move_in_earliest'] or '—'}", callback_data="f:move:earliest"
            ),
            InlineKeyboardButton(
                f"מאוחר ביותר: {draft['move_in_latest'] or '—'}", callback_data="f:move:latest"
            ),
        ],
        [InlineKeyboardButton("🗑️ נקה", callback_data="f:move:clear")],
        [BACK_BUTTON],
    ]
    return InlineKeyboardMarkup(rows)


def advanced_keyboard(draft: dict) -> InlineKeyboardMarkup:
    nb_mark = "☑️" if draft["no_brokers"] else "⬜"
    fx_mark = "☑️" if draft["flexible_match"] else "⬜"
    rows = [
        [InlineKeyboardButton(f"{nb_mark} ללא תיווך", callback_data="f:tog:adv:no_brokers")],
        [
            InlineKeyboardButton(
                f"{fx_mark} סינון גמיש (מותר לפספס דרישה אחת)",
                callback_data="f:tog:adv:flexible_match",
            )
        ],
        [BACK_BUTTON],
    ]
    return InlineKeyboardMarkup(rows)
