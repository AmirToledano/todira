"""Extracts structured fields (price/rooms/floor/square_meters + a few amenity booleans) out of a
Facebook Group post's free-text Hebrew description — the ONLY thing every other source
(Yad2/Komo/Homeless/Marketplace) gets for free from a structured field, a Group post has to be
guessed at from prose a human typed by hand, same as a WhatsApp message.

2026-09-21: built by regex/keyword rules, matching this whole project's existing style (see
yad2_client.normalize's own _FEED_TAG_TO_FIELD/_HEBREW_PROPERTY_TYPE_MAP — plain pattern matching,
never a model call) — explicit owner decision: no LLM call per post (this project has never made
one anywhere; a per-message API cost for something regex can approximate for free wasn't worth it
to him). Deliberately best-effort and ONLY EVER SETS a field when a pattern actually matches — same
"benefit of the doubt" contract as everywhere else a boolean amenity is inferred in this project
(matching.py already treats an unset field as "unknown," never "no"). A post this can't parse
anything out of just normalizes with every structured field None, same as it already does today —
this only adds upside, never a new failure mode.

NOT attempted: city/neighborhood/street extraction — real Hebrew addresses are far too free-form
(informal landmarks like "15 דקות הליכה מהאוניברסיטה" show up as often as a real street name, per
the actual live-confirmed sample this was built against) to guess reliably; left None, same as
facebook_groups_client.py's own module docstring already documents as a real, open limitation.
"""
from __future__ import annotations

import re
from typing import Any

# ₪1,350 / 1,350₪ / 1350 ש"ח / 1350ש״ח / ₪ 1350 — comma thousands-separator optional, ₪/ש"ח either
# side, no space required (confirmed live: "1,350ש\"ח" had zero space between digits and the sign).
_PRICE_RE = re.compile(
    r'(?:₪\s*(\d[\d,]{1,7})|(\d[\d,]{1,7})\s*(?:₪|ש["״]?ח))'
)

# "3 חדרים" / "3.5 חד'" / "2 חד" / "חדר אחד" (word form not handled — rare, and a false negative
# here just leaves rooms=None, never a wrong guess).
_ROOMS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*חד(?:רים|׳|'|ר)?\b")

# "קומה 9" / "קומה ג'" (Hebrew-letter floors not handled, same reasoning as rooms above) /
# "קומת קרקע" treated as floor 0 — a real, common Israeli listing convention.
_FLOOR_RE = re.compile(r"קומ[הת]\s*(\d+)")
_GROUND_FLOOR_RE = re.compile(r"קומת\s*קרקע")

# "80 מ\"ר" / "80 מ״ר" / "80 מטר" / "80 מטרים"
_SQM_RE = re.compile(r'(\d+)\s*(?:מ["״]?ר|מטר(?:ים)?)')

# Each: (compiled pattern, raw_item key, value to set). Checked in order; a later match never
# overwrites an earlier one for the same key (see parse_listing_fields). Negation-aware only for
# pets (the one amenity where "אסור/לא" flipping the meaning is common and easy to check for) —
# every other flag here only ever fires on unambiguous presence of the word itself, same
# "only ever sets True, never guesses False" policy yad2_client.normalize already uses.
_AMENITY_PATTERNS: list[tuple[re.Pattern[str], str, Any]] = [
    (re.compile(r"חניי?ה"), "parking", True),
    (re.compile(r"מעלית"), "elevator", True),
    (re.compile(r"מרפס(?:ת|ות)"), "balcony", True),
    # Hebrew sofit-letter trap, real and live-confirmed: "משופץ" (masculine, ends in ץ) is NOT a
    # substring match for "משופצ" (the same root before a suffixed ת/ים use regular צ) — both forms
    # enumerated explicitly rather than trying to be clever with a single regex.
    (re.compile(r"משופץ|משופצת|משופצים"), "renovated", True),
    (re.compile(r"שותפ(?:ים|ות)|דירת\s*שותפים"), "roommates", True),
]

_PETS_ALLOWED_RE = re.compile(r"חיות\s*מחמד")
_PETS_NEGATION_RE = re.compile(r"(?:לא|אסור|ללא)\D{0,10}חיות\s*מחמד")


def parse_listing_fields(text: str) -> dict[str, Any]:
    """Returns a dict of ONLY the raw_item keys (normalize()-ready names) actually detected in
    `text` — price/rooms/floor/square_meters/parking/elevator/balcony/renovated/roommates/
    petsAllowed. An empty dict means nothing matched; callers merge this into whatever other raw
    fields they already have (see facebook_groups_client.fetch_post_detail), never overwriting a
    field that's already set from a more reliable source."""
    if not text:
        return {}

    fields: dict[str, Any] = {}

    price_match = _PRICE_RE.search(text)
    if price_match:
        digits = (price_match.group(1) or price_match.group(2)).replace(",", "")
        fields["price"] = int(digits)

    rooms_match = _ROOMS_RE.search(text)
    if rooms_match:
        fields["rooms"] = float(rooms_match.group(1))

    if _GROUND_FLOOR_RE.search(text):
        fields["floor"] = 0
    else:
        floor_match = _FLOOR_RE.search(text)
        if floor_match:
            fields["floor"] = int(floor_match.group(1))

    sqm_match = _SQM_RE.search(text)
    if sqm_match:
        fields["square_meters"] = int(sqm_match.group(1))

    for pattern, key, value in _AMENITY_PATTERNS:
        if key not in fields and pattern.search(text):
            fields[key] = value

    if _PETS_ALLOWED_RE.search(text) and not _PETS_NEGATION_RE.search(text):
        fields["petsAllowed"] = True

    return fields
