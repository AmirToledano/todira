"""Extracts structured fields (price/rooms/floor/square_meters + a few amenity booleans) out of a
Facebook Group post's free-text Hebrew description — the ONLY thing every other source
(Yad2/Komo/Homeless/Marketplace) gets for free from a structured field, a Group post has to be
guessed at from prose a human typed by hand, same as a chat message.

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

# "80 מ\"ר" / "80 מ״ר" / "80 מטר" / "80 מטרים". 2026-10-15: not a distance - "200 מטר מהים", "50 מטרים לתחנה" - and only a
# believable flat size, so a stray number never becomes one.
_SQM_RE = re.compile(r'(?<!\d)(\d{2,3})\s*(?:מ["״\']?ר(?![א-ת])|מטר(?:ים)?(?![א-ת])(?!\s*(?:מ|ל|עד|הליכה|נסיעה)))')
_SQM_RANGE = (15, 500)
_ROOMS_RANGE = (1.0, 12.0)

# 2026-10-15: a room in a shared flat states the FLAT's rooms ("חדר להשכרה בדירת 4 חדרים"), not what is for rent - no room
# count then, so the ad never reaches someone looking for a whole 4-room flat.
_SINGLE_ROOM_RE = re.compile(
    r"חדר\s+(?:להשכרה|פנוי|בדירת|בדירה)|(?:מפנה|מפנים|משכיר|משכירה)\s+(?:את\s+)?ה?חדר(?![א-ת])|שות(?:ף|פה|פים|פות)\s+ל?דירת"
)

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

    fields.update(rooms_and_size(text))

    if _GROUND_FLOOR_RE.search(text):
        fields["floor"] = 0
    else:
        floor_match = _FLOOR_RE.search(text)
        if floor_match:
            fields["floor"] = int(floor_match.group(1))

    for pattern, key, value in _AMENITY_PATTERNS:
        if key not in fields and pattern.search(text):
            fields[key] = value

    if _PETS_ALLOWED_RE.search(text) and not _PETS_NEGATION_RE.search(text):
        fields["petsAllowed"] = True

    return fields


def rooms_and_size(text: str | None) -> dict[str, Any]:
    """2026-10-15: the room count and size an ad's own text states, as raw_item keys ("rooms", "square_meters") - also used
    for Marketplace ads, whose feed has neither (facebook_client.py). Only what the text clearly says; nothing on doubt."""
    if not text:
        return {}
    fields: dict[str, Any] = {}
    rooms_match = _ROOMS_RE.search(text)
    if rooms_match and not _SINGLE_ROOM_RE.search(text):
        rooms = float(rooms_match.group(1))
        if _ROOMS_RANGE[0] <= rooms <= _ROOMS_RANGE[1] and (rooms * 2).is_integer():
            fields["rooms"] = rooms
    sqm_match = _SQM_RE.search(text)
    if sqm_match and _SQM_RANGE[0] <= int(sqm_match.group(1)) <= _SQM_RANGE[1]:
        fields["square_meters"] = int(sqm_match.group(1))
    return fields



# --- 2026-10-19: where it is, what kind of deal, and is it an ad at all -----------------------------------------------
# The groups feed (scraper/facebook_browser/feed.py) brings posts from every joined group, so the post itself has to say
# the city and whether it is a rental, a sale or a sublet - the same free reader the bot uses for a user's own message
# (todira_common.search_text) reads both. A post by someone LOOKING for a flat is not a listing.

_SEEKER_RE = re.compile(
    r"(?<![א-ת])(?:מחפש|מחפשת|מחפשים|מחפשות|דרוש|דרושה|מעוניין|מעוניינת|מעוניינים)(?![א-ת])"
    r"[^.\n]{0,40}(?<![א-ת])(?:דירה|דירת|חדר|יחידה|יחידת|סאבלט|סבלט|שותף|שותפה|בית|להשכרה|לשכירות)",
)
_OFFER_RE = re.compile(r"(?<![א-ת])(?:להשכרה|למכירה|מפנה|מפנים|מתפנה|פנויה|משכיר|משכירה|מוכר|מוכרת|סאבלט|סבלט)(?![א-ת])")
_STREET_RE = re.compile(
    r"(?<![א-ת])(?:ב?רחוב|ב?רח['׳]|ב?שד['׳]|ב?שדרות)\s+([א-ת][א-ת\"'׳״\- ]{1,24}?)\s*(\d{1,3})?(?=[\s,.!\n]|$)"
)


def looks_like_seeker(text: str) -> bool:
    """True for "מחפשת דירת 2 חדרים בגבעתיים" - someone asking, not offering. A post that also clearly offers
    ("מפנה דירה, מחפשים מחליף") is an offer."""
    if not text:
        return False
    head = text[:200]
    return bool(_SEEKER_RE.search(head)) and not _OFFER_RE.search(head)


def parse_place_and_deal(text: str) -> dict[str, Any]:
    """raw_item keys "city", "street" and "dealHint" ("rent"/"sale"/"sublet") as far as the post states them."""
    from todira_common import search_text

    if not text:
        return {}
    fields: dict[str, Any] = {}
    found = search_text.parse(text)
    if found["cities"]:
        fields["city"] = found["cities"][0]
    if found["deal_type"]:
        fields["dealHint"] = found["deal_type"]
    street = _STREET_RE.search(text)
    if street:
        name = street.group(1).strip(" -")
        if 2 <= len(name) <= 24:
            fields["street"] = f"{name} {street.group(2)}" if street.group(2) else name
    return fields



# --- 2026-10-19 (owner: a guarantees-company ad with a "10,000 ₪" gift voucher reached everyone as an apartment) --------
# A group post becomes a listing only when it reads as a real flat on offer: it names the property ("דירה", "יחידת
# דיור", "סטודיו"...) or states a room count, AND it says it is on offer (rent/sale/sublet words, "מפנה", "פנויה",
# "כניסה") or gives a room count; and it carries none of the marks of an advertisement for a service.
_PROPERTY_RE = re.compile(
    r"(?<![א-ת])(?:ה?דירה|ה?דירת|דירות|יחידת\s*דיור|יח[\"״]ד|סטודיו|פנטהאוז|פנטהאוס|דופלקס|קוטג|וילה|בית\s+פרטי|"
    r"דירת\s+גן|חדר\s+(?:להשכרה|בדירת|בדירה|פנוי))(?![א-ת])"
)
_ON_OFFER_RE = re.compile(
    r"(?<![א-ת])(?:להשכרה|להשכיר|למכירה|למכור|סאבלט|סבלט|מפנה|מפנים|מתפנה|פנויה|פנוי|משכיר|משכירה|כניסה)(?![א-ת])"
)
_AD_MARKS_RE = re.compile(
    r"utm_|(?<![א-ת])(?:הגרלה|בהגרלה|להגרלה|שובר|שוברים|ערבות|ערבויות|משכנתא|משכנתאות|הלוואה|הלוואות|ביטוח|"
    r"ייעוץ|יועץ|קורס|סדנה|וובינר|מבצע|הנחה|קופון|פרסומת|ממומן|לחצו\s+על\s+הקישור|הירשמו|להרשמה)(?![א-ת])"
)


def looks_like_listing(text: str, raw_item: dict[str, Any] | None = None) -> bool:
    """True when a group post is a flat on offer, not an ad, a question or chatter. `raw_item` (parse_listing_fields
    output) supplies the room count when already read."""
    if not text or _AD_MARKS_RE.search(text):
        return False
    rooms = (raw_item or {}).get("rooms") if raw_item else rooms_and_size(text).get("rooms")
    names_property = bool(_PROPERTY_RE.search(text)) or rooms is not None
    on_offer = bool(_ON_OFFER_RE.search(text)) or rooms is not None
    return names_property and on_offer
