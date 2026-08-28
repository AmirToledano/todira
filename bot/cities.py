"""A small bundled list of major Israeli cities, used only for fuzzy-match suggestions when a
user types a city name in the /filter conversation — NOT validated against Yad2's live data.

IMPORTANT caveat (see scraper/YAD2_NOTES.md): the matcher compares `filters.cities` values
against `listings.city` verbatim (array-overlap). Whatever string a user picks here must match
the string Yad2 actually puts in a listing's `city` field, or matching will silently fail.
Revisit this list's exact spellings once the Yad2 field-mapping research spike is done — for now
these are best-effort common Hebrew city names.
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


def find_matches(query: str, limit: int = 6) -> list[str]:
    query = _strip_quotes(query.strip())
    if not query:
        return []
    if query in _ALIASES:
        canonical = _ALIASES[query]
        rest = [c for c in CITIES if query in c and c != canonical]
        return [canonical, *rest][:limit]
    return [c for c in CITIES if query in c][:limit]
