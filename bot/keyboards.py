"""Inline-keyboard builders for the /filter conversation. Every submenu ends in a "Back" button
that returns to the root menu (`f:root`) — see plan Section 5 for the menu-driven design this
implements, and handlers/filter_conversation.py for the state machine that drives these.

2026-09-26: every label here now goes through bot_strings.bot_text(..., lang) instead of a fixed
Hebrew constant — part of the owner's "full coverage, not just filter_conversation.py's own
prompts" follow-up (see bot_strings.py's own header). The old module-level dicts (CATEGORY_TITLES,
DEAL_TYPE_LABELS, etc.) are now lang-parameterized functions instead; NUMERIC_PRESETS stays a
plain constant since it holds numbers, not text.
"""
from __future__ import annotations

import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from todira_common import cities
from todira_common.bot_strings import bot_text
from todira_common.enums import DealType, FurniturePref, PropertyType, SafeRoomPref


def deal_type_labels(lang: str) -> dict:
    return {
        DealType.RENT: bot_text("kb.deal_type.rent", lang),
        DealType.SALE: bot_text("kb.deal_type.sale", lang),
        DealType.SUBLET: bot_text("kb.deal_type.sublet", lang),
    }


def property_type_labels(lang: str) -> dict:
    return {
        PropertyType.APARTMENT: bot_text("kb.property_type.apartment", lang),
        PropertyType.GARDEN_APARTMENT: bot_text("kb.property_type.garden_apartment", lang),
        PropertyType.PENTHOUSE: bot_text("kb.property_type.penthouse", lang),
        PropertyType.STUDIO: bot_text("kb.property_type.studio", lang),
        PropertyType.HOUSING_UNIT: bot_text("kb.property_type.housing_unit", lang),
        PropertyType.PRIVATE_HOUSE: bot_text("kb.property_type.private_house", lang),
        PropertyType.SHARED_ROOM: bot_text("kb.property_type.shared_room", lang),
    }


def safe_room_labels(lang: str) -> dict:
    return {
        SafeRoomPref.SAFE_ROOM_ONLY: bot_text("kb.safe_room.only", lang),
        SafeRoomPref.SAFE_ROOM_OR_SHELTER: bot_text("kb.safe_room.or_shelter", lang),
        SafeRoomPref.ANY: bot_text("kb.all", lang),
    }


def furniture_labels(lang: str) -> dict:
    return {
        FurniturePref.FURNISHED: bot_text("kb.furniture.furnished", lang),
        FurniturePref.UNFURNISHED: bot_text("kb.furniture.unfurnished", lang),
        FurniturePref.ANY: bot_text("kb.all", lang),
    }


def requirement_labels(lang: str) -> tuple[tuple[str, str], ...]:
    return (
        ("require_parking", bot_text("kb.requirement.parking", lang)),
        ("require_elevator", bot_text("kb.requirement.elevator", lang)),
        ("require_balcony", bot_text("kb.requirement.balcony", lang)),
        ("require_pets_allowed", bot_text("kb.requirement.pets_allowed", lang)),
        ("require_renovated", bot_text("kb.requirement.renovated", lang)),
        ("require_has_photos", bot_text("kb.requirement.has_photos", lang)),
        ("require_roommate_friendly", bot_text("kb.requirement.roommate_friendly", lang)),
    )


def category_titles(lang: str) -> dict:
    return {
        "root": bot_text("kb.title.root", lang),
        "dt": bot_text("kb.title.dt", lang),
        "pt": bot_text("kb.title.pt", lang),
        "loc": bot_text("kb.title.loc", lang),
        "locpick": bot_text("kb.title.locpick", lang),
        "price": bot_text("kb.title.price", lang),
        "rooms": bot_text("kb.title.rooms", lang),
        "floor": bot_text("kb.title.floor", lang),
        "req": bot_text("kb.title.req", lang),
        "safe": bot_text("kb.title.safe", lang),
        "furn": bot_text("kb.title.furn", lang),
        "area": bot_text("kb.title.area", lang),
        "kw": bot_text("kb.title.kw", lang),
        "move": bot_text("kb.title.move", lang),
        "adv": bot_text("kb.title.adv", lang),
    }


def _back_button(lang: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(bot_text("kb.back", lang), callback_data="f:root")


def _fmt_range(lo, hi, lang: str, unit: str = "") -> str:
    if lo is None and hi is None:
        return bot_text("kb.no_limit", lang)
    if lo is not None and hi is not None:
        return f"{lo}–{hi}{unit}"
    if lo is not None:
        return bot_text("kb.range_from", lang, lo=lo, unit=unit)
    return bot_text("kb.range_until", lang, hi=hi, unit=unit)


def render_root_summary(draft: dict, lang: str) -> str:
    titles = category_titles(lang)
    all_label = bot_text("kb.all", lang)
    dash = "—"
    active_reqs = [label for attr, label in requirement_labels(lang) if draft.get(attr)]
    property_labels = property_type_labels(lang)
    min_area = (
        bot_text("kb.sqm_value", lang, value=draft["min_area_sqm"])
        if draft["min_area_sqm"]
        else dash
    )
    lines = [
        titles["root"],
        f"🏷️ {bot_text('kb.label.deal_type', lang)}: "
        + deal_type_labels(lang).get(draft["deal_type"], draft["deal_type"]),
        f"🏠 {bot_text('kb.label.property_type', lang)}: "
        + (", ".join(property_labels[p] for p in draft["property_types"]) or all_label),
        f"📍 {bot_text('kb.label.cities', lang)}: " + (", ".join(draft["cities"]) or all_label),
        f"💰 {bot_text('kb.label.price', lang)}: "
        + _fmt_range(draft["price_min"], draft["price_max"], lang, " ₪"),
        f"🛏️ {bot_text('kb.label.rooms', lang)}: "
        + _fmt_range(draft["rooms_min"], draft["rooms_max"], lang),
        f"🏢 {bot_text('kb.label.floor', lang)}: "
        + (
            bot_text("kb.ground_floor_only_label", lang)
            if draft["ground_floor_only"]
            else _fmt_range(draft["floor_min"], draft["floor_max"], lang)
        ),
        f"✅ {bot_text('kb.label.requirements', lang)}: " + (", ".join(active_reqs) or dash),
        f"🛡️ {bot_text('kb.label.safe_room', lang)}: "
        + safe_room_labels(lang).get(draft["safe_room_pref"], all_label),
        f"🛋️ {bot_text('kb.label.furniture', lang)}: "
        + furniture_labels(lang).get(draft["furniture_pref"], all_label),
        f"📏 {bot_text('kb.label.min_area', lang)}: " + min_area,
        # html.escape — unlike every other field rendered here, keywords is genuine free user
        # text (typed directly or extracted by Gemini from free text, see onboarding.py/
        # filter_conversation.py), and this whole summary is always sent with parse_mode=HTML.
        # An unescaped "<"/"&" here (e.g. a keyword like "AC & heating") makes Telegram's HTML
        # parser reject the message outright — and since this same render is what /filter always
        # shows first, that would make /filter permanently unusable for that user until the DB
        # row is fixed manually. Same fix already applied everywhere else user text meets
        # parse_mode=HTML in this project (see todira_common/cards.py, handlers/support.py).
        f"🔍 {bot_text('kb.label.keywords', lang)}: "
        + (", ".join(html.escape(kw) for kw in draft["keywords"]) or dash),
        f"📅 {bot_text('kb.label.move_in', lang)}: "
        + _fmt_range(draft["move_in_earliest"], draft["move_in_latest"], lang),
        f"⚙️ {bot_text('kb.label.no_brokers', lang)}: "
        + ("✔" if draft["no_brokers"] else "✘")
        + f" · {bot_text('kb.label.flexible_match', lang)}: "
        + ("✔" if draft["flexible_match"] else "✘"),
    ]
    return "\n".join(lines)


def root_keyboard(lang: str) -> InlineKeyboardMarkup:
    titles = category_titles(lang)
    rows = [
        [
            InlineKeyboardButton(titles["dt"], callback_data="f:cat:dt"),
            InlineKeyboardButton(titles["pt"], callback_data="f:cat:pt"),
        ],
        [
            InlineKeyboardButton(titles["loc"], callback_data="f:cat:loc"),
            InlineKeyboardButton(titles["price"], callback_data="f:cat:price"),
        ],
        [
            InlineKeyboardButton(titles["rooms"], callback_data="f:cat:rooms"),
            InlineKeyboardButton(titles["floor"], callback_data="f:cat:floor"),
        ],
        [
            InlineKeyboardButton(titles["req"], callback_data="f:cat:req"),
            InlineKeyboardButton(titles["safe"], callback_data="f:cat:safe"),
        ],
        [
            InlineKeyboardButton(titles["furn"], callback_data="f:cat:furn"),
            InlineKeyboardButton(titles["area"], callback_data="f:cat:area"),
        ],
        [
            InlineKeyboardButton(titles["kw"], callback_data="f:cat:kw"),
            InlineKeyboardButton(titles["move"], callback_data="f:cat:move"),
        ],
        [InlineKeyboardButton(titles["adv"], callback_data="f:cat:adv")],
        [
            InlineKeyboardButton(bot_text("kb.save_and_search", lang), callback_data="f:save"),
            InlineKeyboardButton(bot_text("kb.cancel_button", lang), callback_data="f:cancel"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def single_select_keyboard(
    options: dict[str, str], current: str, ns: str, lang: str
) -> InlineKeyboardMarkup:
    rows = []
    for value, label in options.items():
        mark = "🔘" if value == current else "⚪"
        rows.append([InlineKeyboardButton(f"{mark} {label}", callback_data=f"f:set:{ns}:{value}")])
    rows.append([_back_button(lang)])
    return InlineKeyboardMarkup(rows)


def multi_select_keyboard(
    options: dict[str, str], selected: list[str], ns: str, lang: str
) -> InlineKeyboardMarkup:
    rows = []
    for value, label in options.items():
        mark = "☑️" if value in selected else "⬜"
        rows.append([InlineKeyboardButton(f"{mark} {label}", callback_data=f"f:tog:{ns}:{value}")])
    rows.append([_back_button(lang)])
    return InlineKeyboardMarkup(rows)


def requirements_keyboard(draft: dict, lang: str) -> InlineKeyboardMarkup:
    rows = []
    for attr, label in requirement_labels(lang):
        mark = "☑️" if draft.get(attr) else "⬜"
        rows.append([InlineKeyboardButton(f"{mark} {label}", callback_data=f"f:tog:req:{attr}")])
    rows.append([_back_button(lang)])
    return InlineKeyboardMarkup(rows)


def location_keyboard(draft: dict, lang: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                bot_text("kb.add_city_from_list", lang), callback_data="f:loc:full"
            )
        ],
        [
            InlineKeyboardButton(
                bot_text("kb.search_city_by_typing", lang), callback_data="f:loc:addcity"
            )
        ],
    ]
    if draft["cities"]:
        # 2026-09-15: real owner report — an empty cities list already means "all cities" (see
        # render_root_summary's own "kb.all" fallback just below, and matching.py's
        # _check_hard_filters: `if filter_row.cities:` is skipped entirely when this is empty, so
        # NO city check applies at all, including cities outside cities.CITIES) — but the only way
        # to reach that state was manually adding, then manually removing, every single city one at
        # a time. The owner instead selected all 42 bundled cities individually to mean "all
        # cities," which is NOT the same thing: it silently excludes every real listing whose city
        # isn't one of those 42 curated names (confirmed live: 1,153 of 3,794 active rent listings,
        # in real towns like אריאל/חריש/נשר/קרית שמונה that just aren't in the bundled list). This
        # button reaches the SAME true-"all" state the summary already promises, in one tap.
        rows.append(
            [
                InlineKeyboardButton(
                    bot_text("kb.clear_all_cities", lang), callback_data="f:loc:clearall"
                )
            ]
        )
    for city in draft["cities"]:
        # 2026-09-25 real bug fix: this used to encode the city's LIST INDEX, which goes stale the
        # instant one is removed — a real double-tap (or any tap racing a slow re-render) on the
        # same rendered button sent the SAME stale index twice, so the second tap silently removed
        # whatever city had shifted into that position instead of doing nothing. Encoding the
        # city's own name instead makes removal idempotent/robust to exactly that, and every real
        # Israeli city/town name is far short of callback_data's 64-byte limit (the bundled list's
        # own longest, "מודיעין מכבים רעות", is 34 bytes; this prefix adds 10).
        rows.append([InlineKeyboardButton(f"🗑️ {city}", callback_data=f"f:loc:rmc:{city}")])
    rows.append([_back_button(lang)])
    return InlineKeyboardMarkup(rows)


def city_picker_keyboard(draft: dict, lang: str) -> InlineKeyboardMarkup:
    """Full list of every bundled city as a toggleable button (mirrors multi_select_keyboard's
    ☑️/⬜ pattern, same as "property type") — the primary way to add a city now; typed search
    (below) is a convenience for anyone who'd rather not scroll ~40 buttons, not the only path
    anymore."""
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
    rows.append(
        [InlineKeyboardButton(bot_text("kb.search_by_typing", lang), callback_data="f:loc:addcity")]
    )
    rows.append([InlineKeyboardButton(bot_text("kb.back", lang), callback_data="f:cat:loc")])
    return InlineKeyboardMarkup(rows)


def city_search_results_keyboard(matches: list[str], lang: str) -> InlineKeyboardMarkup:
    """Renders typed-search candidates (from cities.find_matches) as tappable buttons instead of
    silently picking the first match — a user chooses explicitly which city they meant, same as
    tapping a box in city_picker_keyboard. `matches` are always members of cities.CITIES, so
    `.index()` never raises."""
    rows = [
        [InlineKeyboardButton(f"➕ {city}", callback_data=f"f:loc:togc:{cities.CITIES.index(city)}")]
        for city in matches
    ]
    rows.append([InlineKeyboardButton(bot_text("kb.back", lang), callback_data="f:cat:loc")])
    return InlineKeyboardMarkup(rows)


NUMERIC_PRESETS: dict[str, list] = {
    "price_min": [0, 1500, 2000, 2500, 3000, 4000, 5000, 7000],
    "price_max": [2500, 3500, 4500, 5500, 7000, 9000, 12000, 18000],
    "rooms_min": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0],
    "rooms_max": [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0],
    "floor_min": [0, 1, 2, 3, 4, 5, 8, 12],
    "floor_max": [1, 2, 3, 4, 5, 8, 12, 20],
}


def numeric_preset_keyboard(
    field: str, current, parent_category: str, lang: str
) -> InlineKeyboardMarkup:
    """Quick-pick grid of common values for a price/rooms/floor min or max field, tap-only — no
    typing needed for the common case. The "other value..." button is the fallback for anything
    not in the grid (routed by filter_conversation._prompt_for_text to a freshly SENT message with
    a ForceReply, which is the only way to get Telegram to auto-open the device keyboard — the old
    behavior here edited the existing message with a plain text prompt, which python-telegram-bot/
    the Bot API can only attach an InlineKeyboardMarkup to, never a ForceReply, so the keyboard
    never opened on its own. Real owner complaint, 2026-09-15."""
    presets = NUMERIC_PRESETS[field]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for idx, val in enumerate(presets):
        label = f"{val:g}" if isinstance(val, float) else str(val)
        mark = "✅ " if current == val else ""
        row.append(InlineKeyboardButton(f"{mark}{label}", callback_data=f"f:pick:{field}:{idx}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(
                bot_text("kb.other_value", lang), callback_data=f"f:pick:{field}:custom"
            )
        ]
    )
    if current is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    bot_text("kb.clear_no_limit", lang), callback_data=f"f:pick:{field}:clear"
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(bot_text("kb.back", lang), callback_data=f"f:cat:{parent_category}")]
    )
    return InlineKeyboardMarkup(rows)


def price_keyboard(draft: dict, lang: str) -> InlineKeyboardMarkup:
    req_mark = "☑️" if draft["require_price"] else "⬜"
    rows = [
        [
            InlineKeyboardButton(
                bot_text("kb.minimum_value", lang, value=draft["price_min"] or "—"),
                callback_data="f:price:min",
            ),
            InlineKeyboardButton(
                bot_text("kb.maximum_value", lang, value=draft["price_max"] or "—"),
                callback_data="f:price:max",
            ),
        ],
        [
            InlineKeyboardButton(
                f"{req_mark} {bot_text('kb.only_with_price', lang)}",
                callback_data="f:price:reqtoggle",
            )
        ],
        [_back_button(lang)],
    ]
    return InlineKeyboardMarkup(rows)


def rooms_keyboard(draft: dict, lang: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                bot_text("kb.minimum_value", lang, value=draft["rooms_min"] or "—"),
                callback_data="f:rooms:min",
            ),
            InlineKeyboardButton(
                bot_text("kb.maximum_value", lang, value=draft["rooms_max"] or "—"),
                callback_data="f:rooms:max",
            ),
        ],
        [_back_button(lang)],
    ]
    return InlineKeyboardMarkup(rows)


def floor_keyboard(draft: dict, lang: str) -> InlineKeyboardMarkup:
    ground_mark = "☑️" if draft["ground_floor_only"] else "⬜"
    rows = [
        [
            InlineKeyboardButton(
                bot_text("kb.minimum_value", lang, value=draft["floor_min"] or "—"),
                callback_data="f:floor:min",
            ),
            InlineKeyboardButton(
                bot_text("kb.maximum_value", lang, value=draft["floor_max"] or "—"),
                callback_data="f:floor:max",
            ),
        ],
        [
            InlineKeyboardButton(
                f"{ground_mark} {bot_text('kb.ground_floor_only_toggle', lang)}",
                callback_data="f:floor:ground",
            )
        ],
        [_back_button(lang)],
    ]
    return InlineKeyboardMarkup(rows)


def area_keyboard(draft: dict, lang: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                bot_text("kb.min_area_value", lang, value=draft["min_area_sqm"] or "—"),
                callback_data="f:area:set",
            )
        ],
        [_back_button(lang)],
    ]
    return InlineKeyboardMarkup(rows)


def keywords_keyboard(draft: dict, lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(bot_text("kb.edit_keywords", lang), callback_data="f:kw:set")],
        [InlineKeyboardButton(bot_text("kb.clear_button", lang), callback_data="f:kw:clear")],
        [_back_button(lang)],
    ]
    return InlineKeyboardMarkup(rows)


def move_in_keyboard(draft: dict, lang: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                bot_text("kb.earliest_value", lang, value=draft["move_in_earliest"] or "—"),
                callback_data="f:move:earliest",
            ),
            InlineKeyboardButton(
                bot_text("kb.latest_value", lang, value=draft["move_in_latest"] or "—"),
                callback_data="f:move:latest",
            ),
        ],
        [InlineKeyboardButton(bot_text("kb.clear_button", lang), callback_data="f:move:clear")],
        [_back_button(lang)],
    ]
    return InlineKeyboardMarkup(rows)


def advanced_keyboard(draft: dict, lang: str) -> InlineKeyboardMarkup:
    nb_mark = "☑️" if draft["no_brokers"] else "⬜"
    fx_mark = "☑️" if draft["flexible_match"] else "⬜"
    rows = [
        [
            InlineKeyboardButton(
                f"{nb_mark} {bot_text('kb.no_brokers_toggle', lang)}",
                callback_data="f:tog:adv:no_brokers",
            )
        ],
        [
            InlineKeyboardButton(
                f"{fx_mark} {bot_text('kb.flexible_match_toggle', lang)}",
                callback_data="f:tog:adv:flexible_match",
            )
        ],
        [_back_button(lang)],
    ]
    return InlineKeyboardMarkup(rows)
