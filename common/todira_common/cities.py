"""A small bundled list of major Israeli cities — used for fuzzy-match suggestions when a user
types a city name in the Telegram bot's /filter conversation, and the known-cities list passed to
Gemini. Moved here from bot/cities.py 2026-09-01 so the bot, the website (and
scraper/yad2_client.py's own tests, which cross-check CITY_SLUG_TO_ID against this list) use the
exact same names.

IMPORTANT caveat (see scraper/YAD2_NOTES.md): the matcher compares `filters.cities` values
against `listings.city` verbatim (array-overlap / exact string equality — see
todira_common.matching's city check and scraper/notifier.py's SQL pre-filter). Whatever string a
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

import html
import re

CITIES: list[str] = [
    "תל אביב יפו", "ירושלים", "חיפה", "ראשון לציון", "פתח תקווה", "אשדוד", "נתניה",
    "באר שבע", "בני ברק", "חולון", "רמת גן", "אשקלון", "רחובות", "בת ים", "בית שמש",
    "כפר סבא", "הרצליה", "חדרה", "מודיעין מכבים רעות", "רעננה", "רמלה", "רמת השרון",
    "נצרת", "לוד", "גבעתיים", "הוד השרון", "נהריה", "אילת", "קריית אתא", "קריית גת",
    "קריית מוצקין", "קריית ביאליק", "קריית אונו", "יבנה", "אור יהודה", "צפת", "עפולה",
    "טבריה", "דימונה", "מבשרת ציון", "הר גילה", "כרמיאל",
    # 2026-09-27: real owner request — the original 42-city list above was a "major cities" curation,
    # not every city with real listings. diagnose-city-filter-coverage-gap.yaml confirmed live:
    # 3,763 of 13,031 active listings (~29%) had a city outside it, entirely unreachable by picking
    # ANY combination of checkboxes (only the empty-filter bypass reached them — see
    # website/main.py's filter_update and the "all cities" toggle that fix added). Every city below
    # has 10+ real active listings in that same live check — the long tail under that (hundreds of
    # small villages/kibbutzim/moshavim with 1-9 listings each) is deliberately left to the "all
    # cities" toggle rather than hand-typed here one at a time; a filter checkbox grid isn't the
    # right UI for hundreds of options nobody scrolls to, and the toggle already reaches every one
    # of them correctly. canonicalize_city() (below) picks up every new entry here automatically —
    # no code change needed there — so a future scrape of e.g. "קרית שמונה" (defective spelling)
    # auto-corrects to "קריית שמונה" (this list's spelling) the same way it already does for the
    # original 42; existing rows already stored under a pre-expansion spelling were reconciled in
    # a one-time live backfill run alongside this change (see PROJECT_STATE.md / git history for
    # that specific run, not repeated here since it only needed to happen once).
    "אריאל", "מעלה אדומים", "גבעת זאב", "נשר", "נתיבות", "מגדל העמק", "חריש", "עכו",
    "קריית שמונה", "קריית ים", "אורנית", "ערד", "נוף הגליל", "מעלות תרשיחא", "טירת כרמל",
    "אופקים", "ראש העין", "יקנעם עילית", "בית שאן", "אור עקיבא", "זכרון יעקב", "אלפי מנשה",
    "קיסריה", "פרדס חנה כרכור", "אזור", "עתלית", "גן יבנה", "גבעת שמואל", "שלומי",
    "יהוד מונוסון", "להבים", "סביון", "גדרה", "שדרות", "עץ אפרים", "באר יעקב", "צור הדסה",
    "אלקנה", "רכסים", "קדימה צורן", "ראש פינה", "אפרת", "מעלה אפרים", "נס ציונה",
    "שערי תקווה", "כפר יונה", "קריית טבעון", "קרני שומרון", "אבו גוש", "עומר", "כפר ורדים",
    "בנימינה גבעת עדה", "קצרין", "מצפה רמון", "מטולה", "קריית מלאכי", "מגדל", "רמת ישי",
    "ירוחם", "חצור הגלילית", "הר אדר", "ביתר עילית", "תל מונד", "אבני חפץ", "קדומים",
    "גבעון החדשה", "ברקן", "אבן יהודה", "גני תקווה", "עלי זהב", "עוספיא", "כורזים",
]

# Common Hebrew abbreviations/nicknames that AREN'T literal substrings of the full city name
# (e.g. "ב"ש" for "באר שבע" — different letters entirely, not a typo), so the plain containment
# check below can't catch them on its own. Keys are stored WITHOUT quote characters (see
# _strip_quotes) since people type these with a mix of ASCII "/' and Hebrew geresh/gershayim
# (׳/״) depending on their keyboard, and the exact punctuation shouldn't matter — _strip_quotes
# already strips both the query AND these keys are written bare, so "ראשל\"צ", "ראשל׳צ" and
# "ראשלצ" all resolve the same way with no extra work per alias.
#
# Expanded 2026-09-02 from the original 4 (בש/תא/פת/רג) after an explicit ask to cover "every
# combination that exists on the internet" for a city name, not just the ones a bug report
# happened to surface — every one of these is a genuinely common, unambiguous Israeli usage;
# deliberately left OUT any that are ambiguous in real usage (e.g. no alias for בית שמש, since
# "ב"ש" colloquially means באר שבע almost everywhere and a second mapping would just overwrite
# the first) rather than guess and risk pointing someone at the wrong city.
_ALIASES: dict[str, str] = {
    "בש": "באר שבע",
    "תא": "תל אביב יפו",
    "פת": "פתח תקווה",
    "רג": "רמת גן",
    "ראשלצ": "ראשון לציון",
    "כס": "כפר סבא",
    "קא": "קריית אתא",
    "קג": "קריית גת",
    "קמ": "קריית מוצקין",
    "קב": "קריית ביאליק",
    "רמהש": "רמת השרון",
    "בב": "בני ברק",
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


def locality_key(name: str | None) -> str:
    """One comparison form for every spelling of a place name (2026-10-13): HTML entities decoded, punctuation and
    quote marks dropped ("תל אביב - יפו", "תל-אביב-יפו", "ג&rsquo;סר א זרקא"), full/defective doubling collapsed."""
    text = html.unescape(name or "")
    for ch in "()/-–־,.":
        text = text.replace(ch, " ")
    for ch in (*_QUOTE_CHARS, "’", "‘", "`"):
        text = text.replace(ch, "")
    return normalize_spelling(" ".join(text.split()))


# 2026-10-13 (owner request: "all the cities, moshavim, settlements, villages and areas"): every official locality and
# area, generated by scripts/build_localities.py from the Central Bureau of Statistics list and our listings' spellings.
try:
    from todira_common.localities_data import ALIASES, EXTRA_LOCALITIES, REGIONS
except ImportError:  # only while scripts/build_localities.py builds it for the very first time
    ALIASES, EXTRA_LOCALITIES, REGIONS = {}, [], {}

# CITIES first and unchanged, so an index into CITIES (old bot buttons) is the same index here.
# 2026-10-19 (owner: "make sure every place in the country is there"): the Central Bureau of Statistics list also names
# 25 Bedouin tribes (שבט) in the Negev, which the generated list left out. Appended at the END, so every existing index
# into LOCALITIES (old bot buttons) stays the same.
BEDOUIN_TRIBES: list[str] = [
    "אעצם (שבט)", "אבו עבדון (שבט)", "אבו עמאר (שבט)", "אבו עמרה (שבט)", "אבו ג'ווייעד (שבט)", "אבו קורינאת (שבט)",
    "אבו רובייעה (שבט)", "אבו רוקייק (שבט)", "אבו סריחאן (שבט)", "אפיניש (שבט)", "אסד (שבט)", "עטאוונה (שבט)",
    "אטרש (שבט)", "הוואשלה (שבט)", "הוזייל (שבט)", "ג'נאביב (שבט)", "ח'ואלד (שבט)", "נצאצרה (שבט)", "קבועה (שבט)",
    "קוואעין (שבט)", "קודייראת א-צאנע (שבט)", "סואעד (כמאנה) (שבט)", "סייד (שבט)", "תראבין א-צאנע (שבט)",
    "זבארגה (שבט)",
]
LOCALITIES: list[str] = [
    *CITIES, *[name for name in EXTRA_LOCALITIES if name not in CITIES],
    *[name for name in BEDOUIN_TRIBES if name not in EXTRA_LOCALITIES],
]
LOCALITY_SET = frozenset(LOCALITIES)
_SPLIT_COMBINED = re.compile(r"\s*/\s*|\s+[-–]\s+")


def locality_skeleton(name: str | None) -> str:
    """locality_key without the vowel letters י and ו inside words (2026-10-19, owner: "קידר" found nothing - the place
    is stored "קדר"). Hebrew is written both with and without them ("קידר"/"קדר", "גבעון"/"גיבעון", "אורנית"/"ארנית"), so
    two spellings that differ only there meet here. A word's first letter is kept ("יבנה" stays "יבנה")."""
    return " ".join(word[:1] + word[1:].replace("י", "").replace("ו", "") for word in locality_key(name).split())


_SKELETON_INDEX: dict[str, set[str]] = {}
for _name in LOCALITIES:
    _SKELETON_INDEX.setdefault(locality_skeleton(_name), set()).add(_name)


def resolve_locality(name: str | None) -> str | None:
    """The stored spelling of whatever locality `name` is (any official or listings spelling, a common abbreviation
    such as ת"א, or a combined "מיתר / כרמית" name), or None when it is no known locality."""
    if not name:
        return None
    if name in LOCALITY_SET:
        return name
    key = locality_key(name)
    if key in ALIASES:
        return ALIASES[key]
    if key.replace(" ", "") in _ALIASES:
        return _ALIASES[key.replace(" ", "")]
    pieces = [piece for piece in _SPLIT_COMBINED.split(html.unescape(name)) if piece.strip()]
    if len(pieces) > 1:
        for piece in pieces:
            found = ALIASES.get(locality_key(piece))
            if found:
                return found
    # Written with or without the vowel letters ("קידר" for "קדר") - only when that leaves exactly one place.
    same_skeleton = _SKELETON_INDEX.get(locality_skeleton(name), set())
    if len(same_skeleton) == 1:
        return next(iter(same_skeleton))
    return None


def find_matches(query: str, limit: int = 6) -> list[str]:
    """Typed search over every locality: an abbreviation's city first, then the major cities, then the rest."""
    query = _strip_quotes(query.strip())
    if not query:
        return []
    if query in _ALIASES:
        canonical = _ALIASES[query]
        rest = [c for c in CITIES if query in c and c != canonical]
        return [canonical, *rest][:limit]
    normalized_query = normalize_spelling(query)
    exact = resolve_locality(query)
    found = [exact] if exact else []
    for name in LOCALITIES:
        if len(found) >= limit:
            break
        if name not in found and normalized_query in normalize_spelling(name):
            found.append(name)
    return found[:limit]


def canonicalize_city(raw_city: str | None) -> str | None:
    """Maps a raw scraped city string (Yad2's own page text) to this list's spelling, when they
    differ only by a full/defective Hebrew doubling — see normalize_spelling and this module's
    docstring for the confirmed real-world case (Yad2's "קרית מוצקין" vs. this list's "קריית
    מוצקין"). Used by scraper/normalize.py at the data-ingestion boundary, once per scraped
    listing, so `listings.city` always agrees with whatever spelling `filters.cities` stores
    (chosen from THIS list, never typed freely) — both the SQL array-overlap pre-filter in
    scraper/notifier.py and the Python equality check in todira_common.matching stay plain exact-
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
    # 2026-10-13: every other known locality too (official list + listings variants, see resolve_locality), so a new
    # listing is stored under the one spelling a filter for that place uses.
    return resolve_locality(raw_city) or resolve_messy_city(raw_city) or raw_city


# --- 2026-10-19: messy city text (owner: "make sure every place is there") ---------------------------------------------
# Measured live: ~330 live listings (mostly Homeless, where the poster types the city freely) carried a "city" no
# filter could ever match: a neighbourhood ("קרית חיים", "רמת אביב", "גילה"), a typo ("תל אביבב", "בניברק"), English
# or Russian ("Haifa", "Хайфа"), a place word in front ("קיבוץ מצובה"), or a whole address ("נתניה ישראל בורגנסקי 4").
# resolve_messy_city reads those; anything still unclear stays as it was (never a guess between two places).

_PLACE_WORDS = re.compile(r"^(?:אזור תעשי+ה|א\.?ת\.?|קיבוץ|קבוץ|מושב|מושבה|כפר|שכונת|שכ['׳]|יישוב|ישוב|העיר|עיר)\s+")
_INDUSTRIAL_ZONE = re.compile(r"^(?:אזור תעשי+ה|א\.?ת\.?)\s")
_SETTLEMENT_WORD = re.compile(r"^(?:קיבוץ|קבוץ|מושב|מושבה|יישוב|ישוב)\s")
_FOREIGN_NAMES = {
    "tel aviv": "תל אביב יפו", "tel-aviv": "תל אביב יפו", "tel aviv yafo": "תל אביב יפו", "telaviv": "תל אביב יפו",
    "jerusalem": "ירושלים", "haifa": "חיפה", "herzliya": "הרצליה", "herzlia": "הרצליה", "herzelia": "הרצליה",
    "netanya": "נתניה", "ashdod": "אשדוד", "ashkelon": "אשקלון", "beer sheva": "באר שבע", "beersheba": "באר שבע",
    "rishon lezion": "ראשון לציון", "rishon le zion": "ראשון לציון", "ramat gan": "רמת גן", "holon": "חולון",
    "bat yam": "בת ים", "eilat": "אילת", "petah tikva": "פתח תקווה", "petach tikva": "פתח תקווה", "rehovot": "רחובות",
    "raanana": "רעננה", "kfar saba": "כפר סבא", "givatayim": "גבעתיים", "oranit": "אורנית", "haderah": "חדרה",
    "hadera": "חדרה", "nahariya": "נהריה", "modiin": "מודיעין מכבים רעות", "bnei brak": "בני ברק",
    "тель-авив": "תל אביב יפו", "тель авив": "תל אביב יפו", "иерусалим": "ירושלים", "хайфа": "חיפה",
    "бат ям": "בת ים", "бат-ям": "בת ים", "нетания": "נתניה", "ашдод": "אשדוד", "ашкелон": "אשקלון",
    "беэр шева": "באר שבע", "беэр-шева": "באר שבע", "холон": "חולון", "ришон ле цион": "ראשון לציון",
    "ришон лецион": "ראשון לציון", "рамат ган": "רמת גן", "хадера": "חדרה", "эйлат": "אילת",
    "ariel": "אריאל", "ari'el": "אריאל", "betar ilit": "ביתר עילית", "beitar illit": "ביתר עילית", "efrat": "אפרת",
    "elkana": "אלקנה", "karne shomron": "קרני שומרון", "karnei shomron": "קרני שומרון", "kiryat arba": "קרית ארבע",
    "ramla": "רמלה", "lod": "לוד", "beit dagan": "בית דגן", "katzrin": "קצרין", "nili": "ניל\"י", "bt yam": "בת ים",
    "giv'on hahadasha": "גבעון החדשה", "givon hahadasha": "גבעון החדשה", "beit shemesh": "בית שמש",
    "kiryat gat": "קריית גת", "kiryat ata": "קריית אתא", "kiryat yam": "קריית ים", "kiryat bialik": "קריית ביאליק",
    "kiryat motzkin": "קריית מוצקין", "yavne": "יבנה", "nes ziona": "נס ציונה", "rosh haayin": "ראש העין",
    "afula": "עפולה", "tiberias": "טבריה", "nazareth": "נצרת", "acre": "עכו", "akko": "עכו", "dimona": "דימונה",
    "sderot": "שדרות", "ofakim": "אופקים", "netivot": "נתיבות", "maale adumim": "מעלה אדומים", "harish": "חריש",
    "петах тиква": "פתח תקווה", "реховот": "רחובות", "кирьят ям": "קריית ים", "кирьят ата": "קריית אתא",
}
# Neighbourhoods people write as the "city" - only well-known ones that belong to exactly one city.
_NEIGHBOURHOODS = {
    "קרית חיים": "חיפה", "קרית חיים מזרחית": "חיפה", "קרית חיים מערבית": "חיפה", "קרית שמואל": "חיפה",
    "קרית אליעזר": "חיפה", "נוה שאנן": "חיפה", "הדר": "חיפה", "הדר הכרמל": "חיפה", "רמות רמז": "חיפה",
    "דניה": "חיפה", "רמת הדר": "חיפה", "בת גלים": "חיפה", "מרכז הכרמל": "חיפה",
    "יפו": "תל אביב יפו", "רמת אביב": "תל אביב יפו", "רמת אביב ג": "תל אביב יפו", "רמת אביב נוה אביבים": "תל אביב יפו",
    "נוה אביבים": "תל אביב יפו", "תל ברוך": "תל אביב יפו", "תל ברוך צפון": "תל אביב יפו", "נוה עופר": "תל אביב יפו",
    "שכונת התקוה": "תל אביב יפו", "התקוה": "תל אביב יפו", "יד אליהו": "תל אביב יפו", "בבלי": "תל אביב יפו",
    "פלורנטין": "תל אביב יפו", "נוה צדק": "תל אביב יפו", "הצפון הישן": "תל אביב יפו", "הצפון החדש": "תל אביב יפו",
    "לב תל אביב": "תל אביב יפו", "רמת החייל": "תל אביב יפו", "כרם התימנים": "תל אביב יפו", "שיכון בבלי": "תל אביב יפו",
    "תל אביב צפון": "תל אביב יפו", "רמת הטייסים": "תל אביב יפו", "נוה שאנן תל אביב": "תל אביב יפו",
    "גילה": "ירושלים", "הר חומה": "ירושלים", "רמות": "ירושלים", "רמות ב": "ירושלים", "פסגת זאב": "ירושלים",
    "רמת שלמה": "ירושלים", "בית הכרם": "ירושלים", "קטמון": "ירושלים", "תלפיות": "ירושלים", "ארנונה": "ירושלים",
    "קרית יובל": "ירושלים", "קרית מנחם": "ירושלים", "רחביה": "ירושלים", "בקעה": "ירושלים", "נחלאות": "ירושלים",
    "רמת מוצא": "ירושלים", "גבעת שאול": "ירושלים", "הר נוף": "ירושלים", "רמת אשכול": "ירושלים", "בית וגן": "ירושלים",
    "רמת הנשיא": "בת ים", "רמת פנקס": "אור יהודה", "קרית חתני פרס נובל": "ראשון לציון", "פרס נובל": "ראשון לציון",
    "נוה ים": "ראשון לציון", "מרום נוה": "רמת גן", "רמת אפעל": "רמת גן", "רמת חן": "רמת גן", "הבורסה": "רמת גן",
    "עפולה הצעירה": "עפולה", "נצרת עילית": "נוף הגליל", "נוף הגליל נצרת עלית": "נוף הגליל", "עיר ימים": "נתניה",
    "קרית השרון": "נתניה", "רמת פולג": "נתניה", "קרית יערים": "טלז סטון", "רמלה לוד": None,
}
# Short or misspelt names of a city that the official list doesn't hold.
_SHORT_NAMES = {
    "מודיעין": "מודיעין מכבים רעות", "מודעין": "מודיעין מכבים רעות", "מודיעין מכבי": "מודיעין מכבים רעות",
    "מודיעין מכבים": "מודיעין מכבים רעות", "תל אביב": "תל אביב יפו", "תל אביב מרכז": "תל אביב יפו",
    "שכונת שפירא": "תל אביב יפו", "שפירא": "תל אביב יפו", "באקה": "באקה אל גרביה", "יבניאל": "יבנאל",
    "יבניל": "יבנאל", "ברגיורא": "בר גיורא",
}
_PHONE_OR_NUMBER = re.compile(r"[\d\-]{6,}")
_BIDI_MARKS = re.compile(r"[\u200e\u200f\u202a-\u202e]")


_WHOLE_WORD_CANDIDATES = [name for name in LOCALITIES if name in CITIES or " " in locality_key(name)]
# The official list's second names in brackets ("כפר רוזנואלד (זרעית)", "ג'ש (גוש חלב)", "ניר דוד (תל עמל)"), which the
# stored spelling dropped: each one is another way of writing that place.
SECOND_NAMES = {
    "זרעית": "כפר רוזנואלד", "גוש חלב": "ג'ש", "תל עמל": "ניר דוד", "אבן יצחק": "גלעד", "בוקייעה": "פקיעין",
    "בנו עוקבה": "עוקבי", "לי און": "שריגים", "חמירה": "סואעד", "דהרה": "חוג'ייראת", "חלמיש": "נווה צוף",
    "צופין": "צופים", "גרנות הגליל": "גורנות הגליל", "גרונות הגליל": "גורנות הגליל",
}
for _other, _name in SECOND_NAMES.items():
    ALIASES.setdefault(locality_key(_other), _name)
# Each half of a combined official name ("כוכב יאיר / צור יגאל"), when that half names only one place.
_COMBINED_PIECES: dict[str, str] = {}
for _name in LOCALITIES:
    _pieces = [p for p in _SPLIT_COMBINED.split(_name) if p.strip()]
    for _piece in _pieces if len(_pieces) > 1 else ():
        _COMBINED_PIECES[locality_key(_piece)] = None if locality_key(_piece) in _COMBINED_PIECES else _name
# Every way of writing a city, for the typo match ("תל אביבב" is closest to "תל אביב", not "תל אביב יפו").
_CITY_SPELLINGS: dict[str, str] = {locality_key(c): c for c in CITIES}
_LOCALITY_KEYS: dict[str, str] = {locality_key(n): n for n in LOCALITIES}
_CITY_SPELLINGS.update({k: v for k, v in ALIASES.items() if v in CITIES and len(k) >= 4})


def _whole_word_places(text: str) -> set[str]:
    """Places named whole-word inside a longer text ("פסגת זאב ירושלים", "נתניה ישראל בורגנסקי 4")."""
    key = f" {locality_key(text)} "
    found = set()
    # Only cities and multi-word places: a one-word village ("רחוב", "שני") is also an everyday word or a first name
    # inside an agent's name ("חכמת רחוב", "שני ליבנה").
    for name in sorted(_WHOLE_WORD_CANDIDATES, key=len, reverse=True):
        name_key = locality_key(name)
        if len(name_key) >= 3 and f" {name_key} " in key:
            found.add(name)
            key = key.replace(f" {name_key} ", " ")
    for short, name in _SHORT_NAMES.items():
        if " " in short and f" {locality_key(short)} " in key:
            found.add(name)
    return found


def resolve_messy_city(raw_city: str | None) -> str | None:
    """The locality a free-typed city text means, or None when it can't be told for sure."""
    if not raw_city:
        return None
    text = _BIDI_MARKS.sub("", raw_city).strip()
    text = _PHONE_OR_NUMBER.split(text)[0]
    text = " ".join(re.sub(r"\d+", " ", html.unescape(text)).split()).strip(" ,.-")
    if not text:
        return None
    found = resolve_locality(text)
    if found:
        return found
    stripped = _PLACE_WORDS.sub("", text).strip()
    if stripped != text:
        found = resolve_locality(stripped)
        if found:
            return found

    foreign = _FOREIGN_NAMES.get(" ".join(text.lower().replace("-", " ").split())) or _FOREIGN_NAMES.get(text.lower())
    if foreign:
        return foreign
    key = locality_key(stripped)
    for spelling in (locality_key(text), key):
        short = {locality_key(k): v for k, v in _SHORT_NAMES.items()}.get(spelling)
        if short:
            return short
        neighbourhood = {locality_key(k): v for k, v in _NEIGHBOURHOODS.items()}.get(spelling)
        if neighbourhood:
            return neighbourhood
    if _COMBINED_PIECES.get(key):
        return _COMBINED_PIECES[key]
    if key in {locality_key(n) for n in _NEIGHBOURHOODS}:
        return next(city for n, city in _NEIGHBOURHOODS.items() if locality_key(n) == key)
    # "בניברק", "רמת גן ן", "קרית אונוון": a doubled last letter or a missing space.
    squeezed = key.replace(" ", "")
    for name in CITIES:
        if locality_key(name).replace(" ", "") == squeezed or locality_key(name).replace(" ", "") == squeezed[:-1]:
            return name
    # "קרית שדה התעופה / איירפורט סיטי": a piece that is a known place, when only one place is named.
    pieces = {resolve_locality(p) for p in _SPLIT_COMBINED.split(text) if p.strip()} - {None}
    if len(pieces) == 1 and len(_SPLIT_COMBINED.split(text)) > 1:
        return next(iter(pieces))
    places = _whole_word_places(stripped if _INDUSTRIAL_ZONE.match(text) else text)
    # Inside a longer text only a two-word neighbourhood counts ("רמות" alone is also "רמות ים" near Netanya).
    neighbourhood_cities = {
        city for n, city in _NEIGHBOURHOODS.items()
        if city and " " in locality_key(n) and f" {locality_key(n)} " in f" {key} "
    }
    candidates = places | neighbourhood_cities
    if len(candidates) == 1:
        return next(iter(candidates))
    # A typo of a major city ("תל אביבב", "תל אבבי", "קרית חים") - only when one city is clearly closest.
    import difflib

    close = difflib.get_close_matches(key, list(_CITY_SPELLINGS), n=3, cutoff=0.85)
    meant = {_CITY_SPELLINGS[k] for k in close}
    if len(meant) == 1:
        return next(iter(meant))
    # Any other place, only a very close spelling of a longer name ("פקיעין החדשה" for "פקיעין חדשה").
    if len(key) >= 7:
        close = difflib.get_close_matches(key, list(_LOCALITY_KEYS), n=2, cutoff=0.9)
        if len({_LOCALITY_KEYS[k] for k in close}) == 1:
            return _LOCALITY_KEYS[close[0]]
    # "מושב צופר בערבה", "מושב מרגליות סמוך למכללת...": after "מושב"/"קיבוץ", the place's name comes first.
    if _SETTLEMENT_WORD.match(text):
        words = stripped.split()
        for size in range(min(3, len(words) - 1), 0, -1):
            found = resolve_locality(" ".join(words[:size]))
            if found:
                return found
    return None

