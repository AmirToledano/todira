"""A small bundled list of major Israeli cities — used for fuzzy-match suggestions when a user
types a city name in the Telegram bot's /filter conversation, and shared with the WhatsApp
onboarding webhook (website/whatsapp_webhook.py) as the known-cities list passed to Gemini. Moved
here from bot/cities.py 2026-09-01 when WhatsApp support was added, so both channels (and
scraper/yad2_client.py's own tests, which cross-check CITY_SLUG_TO_ID against this list) use the
exact same names.

IMPORTANT caveat (see scraper/YAD2_NOTES.md): the matcher compares `filters.cities` values
against `listings.city` verbatim (array-overlap / exact string equality — see
dorin_common.matching's city check and scraper/notifier.py's SQL pre-filter). Whatever string a
user picks here must match the string Yad2 actually puts in a listing's `city` field, or matching
silently fails. CONFIRMED live 2026-09-02 (not guessed): Yad2's own page text for Kiryat Motzkin
is "קרית מוצקין" (1 yud, כתיב חסר), not this list's "קריית מוצקין" (2 yuds, כתיב מלא) — every one
of 81 real scraped listings used the 1-yud spelling, so no filter using this list's spelling could
ever match them. Fixed at the data boundary instead of here: scraper/normalize.py now runs
`canonicalize_city()` (below) on every scraped listing's raw city text before it's stored, so
`listings.city` always ends up using THIS list's spelling regardless of which variant Yad2's own
page happened to use — `filters.cities` and `listings.city` stay exact-string-comparable without
touching either comparison site. The other קריית-prefixed cities (קריית אתא/גת/ביאליק/אונו) are
UNVERIFIED against live Yad2 data the same way Kiryat Motzkin was before 2026-09-02 — treat them
with the same caution until confirmed, though canonicalize_city() would auto-correct them the
same way the moment real listings for those cities are scraped, precisely because it's spelling-
based, not a per-city guess.
"""
from __future__ import annotations

CITIES: list[str] = [
    "תל אביב יפו", "ירושלים", "חיפה", "ראשון לציון", "פתח תקווה", "אשדוד", "נתניה",
    "באר שבע", "בני ברק", "חולון", "רמת גן", "אשקלון", "רחובות", "בת ים", "בית שמש",
    "כפר סבא", "הרצליה", "חדרה", "מודיעין מכבים רעות", "רעננה", "רמלה", "רמת השרון",
    "נצרת", "לוד", "גבעתיים", "הוד השרון", "נהריה", "אילת", "קריית אתא", "קריית גת",
    "קריית מוצקין", "קריית ביאליק", "קריית אונו", "יבנה", "אור יהודה", "צפת", "עפולה",
    "טבריה", "דימונה", "מבשרת ציון", "הר גילה", "כרמיאל",
]

# Common Hebrew abbreviations/nicknames that AREN'T literal substrings of the full city name
# (e.g. "ב"ש" for "באר שבע" — different letters entirely, not a typo), so the plain containment
# check below can't catch them on its own. Deliberately a short, non-exhaustive list of the most
# common ones — found missing by the user manually testing "ב"ש" against the real bot. Keys are
# stored WITHOUT quote characters (see _strip_quotes) since people type these with a mix of
# ASCII "/' and Hebrew geresh/gershayim (׳/״) depending on their keyboard, and the exact
# punctuation shouldn't matter.
_ALIASES: dict[str, str] = {
    "בש": "באר שבע",
    "תא": "תל אביב יפו",
    "פת": "פתח תקווה",
    "רג": "רמת גן",
}

_QUOTE_CHARS = ('"', "'", "׳", "״")  # ASCII quote/apostrophe, Hebrew geresh/gershayim


def _strip_quotes(text: str) -> str:
    for ch in _QUOTE_CHARS:
        text = text.replace(ch, "")
    return text


def normalize_spelling(text: str) -> str:
    # Collapses the two most common Hebrew "full" (כתיב מלא) doubled letters down to their
    # "defective" (כתיב חסר) single form, so e.g. a user typing "קרית מוצקין" (1 yud) still finds
    # "קריית מוצקין" (2 yuds, our canonical spelling), and "פתח תקוה" (1 vav) still finds
    # "פתח תקווה" (2 vavs) — found missing 2026-09-02 when a real user's "קרית מוצקין" typo (a
    # spelling many Israelis use interchangeably, not a "real" typo) returned zero matches. Public
    # (not the `find_matches`-only helper it started as) — canonicalize_city() below reuses it.
    return text.replace("יי", "י").replace("וו", "ו")


def find_matches(query: str, limit: int = 6) -> list[str]:
    query = _strip_quotes(query.strip())
    if not query:
        return []
    if query in _ALIASES:
        canonical = _ALIASES[query]
        rest = [c for c in CITIES if query in c and c != canonical]
        return [canonical, *rest][:limit]
    normalized_query = normalize_spelling(query)
    return [c for c in CITIES if normalized_query in normalize_spelling(c)][:limit]


def canonicalize_city(raw_city: str | None) -> str | None:
    """Maps a raw scraped city string (Yad2's own page text) to this list's spelling, when they
    differ only by a full/defective Hebrew doubling — see normalize_spelling and this module's
    docstring for the confirmed real-world case (Yad2's "קרית מוצקין" vs. this list's "קריית
    מוצקין"). Used by scraper/normalize.py at the data-ingestion boundary, once per scraped
    listing, so `listings.city` always agrees with whatever spelling `filters.cities` stores
    (chosen from THIS list, never typed freely) — both the SQL array-overlap pre-filter in
    scraper/notifier.py and the Python equality check in dorin_common.matching stay plain exact-
    string comparisons; neither needs to know about spelling variants.

    Uses an EQUALITY check after normalizing (not find_matches' containment check, which is meant
    for partial-typing search) — deliberately conservative: only remaps when a bundled city name
    is a confident, unambiguous spelling match for the exact raw string, so a real city not yet in
    CITIES (or genuinely different text) is left untouched rather than mapped to something wrong.
    """
    if not raw_city:
        return raw_city
    if raw_city in CITIES:
        return raw_city
    normalized_raw = normalize_spelling(raw_city)
    for city in CITIES:
        if normalize_spelling(city) == normalized_raw:
            return city
    return raw_city
