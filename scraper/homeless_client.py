"""Fetches raw listing payloads from Homeless's rental search (homeless.co.il/rent/).

STATUS 2026-09-13: SOLVED, and simpler than either Yad2 or Komo — confirmed live (see
.github/workflows/diagnose-komo-homeless-reachability.yaml) that homeless.co.il/rent/ is plain
server-rendered HTML (no session dance, no separate map/coordinates API, no JS rendering) at
ZenRows' cheapest tier (1 credit, confirmed via the real X-Request-Credits header). Every field
this project currently needs — property type, city, neighborhood, street, rooms, floor, price —
comes straight out of the SAME single fetch, in a plain HTML <table> whose own header row confirms
the column meanings (found live, not guessed):

    <th orderfield="vcTextShort2">עיר</th>          (city)
    <th orderfield="vcTextShort10">שכונה</th>       (neighborhood)
    <th orderfield="vcTextShort1">רחוב</th>         (street)
    <th orderfield="TextNumber4">חדרים</th>         (rooms)
    <th orderfield="iNumber12">קומה</th>            (floor)
    <th orderfield="fLong3">מחיר</th>               (price)

Each real listing is one <tr id="ad_<numeric id>" ...> row (confirmed live against real rows —
e.g. id="ad_746758": property="דירה", city="תל אביב", neighborhood="" (blank for this one),
street="דרך השלום", rooms="4", floor="2", price="2,130 ₪"), in this fixed column order:
checkbox, photo, property type, city, neighborhood, street, rooms, floor, price, entry date,
update date, details link. The row's own `id="ad_<id>"` attribute is the cleanest source for the
external_id (also embedded in its onclick's `ViewDetails,<id>.aspx` popup call, and in each
listing's own real anchor link elsewhere on the page, `/rent/viewad,<id>.aspx` — both confirmed to
carry the same numeric id; this module uses the row id since it needs no extra parsing).

NOT present anywhere in this table: square meters (no מ"ר column exists in the header row at
all — confirmed live, not an extraction miss) — square_meters is therefore always None from this
source; getting it would need a separate per-listing detail-page fetch, not built (not worth the
extra per-listing cost for a field that's a rarely-filtered nice-to-have, unlike description below).

DESCRIPTION (added 2026-09-13): the search-results table above has no description column either,
but each listing's own detail page (/rent/viewad,<id>.aspx) DOES carry a real, free-text Hebrew ad
description — confirmed live (diagnose-komo-gallery-and-homeless-description.yaml) against a real
row (id=746758): `<meta name="Description" content="דירה להשכרה בתל אביב, דרך השלום מודעה 746758
-  הכניסה מרחוב הורודצקי...">` (also duplicated in `<meta property="og:description">`, same
text). fetch_listing_description below fetches that one extra page — same confirmed-plain, 1-
credit ZenRows tier as everything else in this module — and scraper/main.py's _scrape_homeless
calls it ONLY for genuinely new listings (never for one already known — same "enrich once, cache
forever" policy as komo_client.fetch_listing_detail and Yad2's Bright Data enrichment), so the
real per-run cost is bounded by new listings, not total listings shown.

IMAGES (fixed 2026-09-13): the search-results table's own photo cell (`<td><div><img src="..."/>
</div></td>`) has ALWAYS carried a real photo URL — confirmed against the same row(s) already in
this module's own test fixtures (`https://uploads.homeless.co.il/rent/202609/300/nvFile5386664.jpg`
for id=746758) — but `_ROW_RE` only ever matched that cell to skip past it, discarding the URL on
every single run. Fixed: now captured into the row's own `images` list (normalize() already reads
this generically for every source, see PR #236/#254 for Komo's equivalent).

OUTBOUND LINK (found 2026-09-13, FIXED same night): a real user report after the first real
production Telegram send — clicking a Homeless listing's own "לפרטי הדירה המלאים" link redirected
to Homeless's homepage instead of the listing. Root cause (confirmed live,
diagnose-homeless-real-url-for-new-ids.yaml): this project always reconstructed the URL itself as
f"https://www.homeless.co.il/rent/viewad,{id}.aspx" — correct only for a plain private listing. A
real brokered ("Tivuch") listing's own real link uses a DIFFERENT path prefix,
/RentTivuch/viewad,{id}.aspx, which cannot be derived from the id alone. Fixed by reading each
row's own real href directly instead (see _ROW_RE/_HREF_RE and _parse_rows below) — never
reconstructed from the id anymore, whichever prefix the row actually uses.

TIVUCH COLUMN LAYOUT (found 2026-09-13, FIXED 2026-09-14): a brokered ("Tivuch") row's own real
column layout has NO floor column at all between rooms and price, unlike a plain listing row —
first flagged from a partial observation (one row, id=83480) and left as a known-but-unfixed gap,
then confirmed properly via a full live re-dump of every <td> cell for 4 real current Tivuch rows
plus 1 real plain row (diagnose-homeless-tivuch-column-layout.yaml). The real, confirmed shape:

    plain:  checkbox,photo,type,city,neighborhood,street,rooms,FLOOR,price,entrydate,updatedate,href
    Tivuch: checkbox,photo,type,city,neighborhood,street,rooms,price,entrydate,updatedate,href

i.e. identical for the first 7 columns and the last 4, with the ONE column in between (floor)
present only on a plain row. Before this fix, a Tivuch row's floor field silently captured its own
price string, and its price field captured the entry-date string that comes after — both wrong,
not just missing. _parse_rows below now splits each row generically into <td> cells and maps them
by position from the front (fixed) and from the back (fixed), treating whatever's left in the
middle as floor only if there's exactly one such column — genuinely None for Tivuch, not a miss.

NOT yet confirmed: whether /rent/ paginates for more listings beyond what one fetch returns (Komo
turned out to have ~175 pages behind its own single-page HTML view, Yad2 too — Homeless has not
been checked for the same real "how many total listings does this site actually have vs. how many
one fetch returns" question yet). fetch_search_results below reads exactly what one plain fetch of
the base URL returns and nothing more — treat that as a real, documented open question, not a
silent assumption that it's already complete coverage.

Requires ZENROWS_API_KEY (same account/key as yad2_client.py and komo_client.py)."""
from __future__ import annotations

import html
import logging
import os
import re
from typing import Any, Iterator
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

SEARCH_PAGE_URL = "https://www.homeless.co.il/rent/"
_DETAIL_PAGE_BASE = "https://www.homeless.co.il"

ZENROWS_API_KEY_ENV_VAR = "ZENROWS_API_KEY"
ZENROWS_FETCH_API_URL = "https://api.zenrows.com/v1/"

# Confirmed live 2026-09-13: plain fetch, no js_render/premium_proxy, 1 ZenRows credit.
PAGE_LOAD_TIMEOUT_S = 60

# Same shape/reasoning as yad2_client._ZENROWS_ERROR_CODE_RE/_ZENROWS_ERROR_TITLE_RE and
# komo_client's own copy — ZenRows' own JSON error body, not wrapped in any HTML shell. Duplicated
# here rather than imported/shared, matching this project's established file-per-source
# independence convention (see yad2_client.py's own module docstring).
_ZENROWS_ERROR_CODE_RE = re.compile(r'"code":"(?P<code>[A-Z0-9]+)"')
_ZENROWS_ERROR_TITLE_RE = re.compile(r'"title":"(?P<title>[^"]*)"')

# Matches the FULL span of one real listing row, id through closing </tr> (confirmed live against
# id="ad_746758" and many others — see module docstring). Everything inside is then split into its
# own <td> cells by _TD_RE and mapped by POSITION, not matched field-by-field in one fixed regex —
# see the 2026-09-14 finding below on why a single fixed column order no longer holds for every row.
_ROW_RE = re.compile(r'<tr[^>]*\bid="ad_(?P<id>\d+)"[^>]*>(?P<body>.*?)</tr>', re.S)

# One row's own <td>...</td> cells, in order, as raw (still-escaped) inner HTML — deliberately
# generic (not per-field) since 2026-09-14 (see below): the columns AFTER "rooms" differ in count
# between a plain listing and a brokered ("Tivuch") one, so a single fixed-position regex can't
# describe both. `[^>]*` on the opening tag tolerates any attributes (e.g. `style="..."`, `class=`).
_TD_RE = re.compile(r'<td[^>]*>(?P<content>.*?)</td>', re.S)

# The photo cell's own <img src="..."> — `[^"]*` (not `[^<]*`) since a src URL can't contain `<`
# but the group must stop at the closing quote, not at some later `<`. Captured, not discarded, as
# of 2026-09-13 — see module docstring's IMAGES note.
_IMG_SRC_RE = re.compile(r'\bsrc="(?P<src>[^"]*)"')

# The details-link cell's own real href — /rent/ for a plain listing, /RentTivuch/ for a brokered
# one (see module docstring's OUTBOUND LINK / TIVUCH COLUMN LAYOUT notes). Read from THIS one cell
# specifically (the last <td> in the row), not scanned across the whole row, since only this cell
# is ever expected to carry an <a href>.
_HREF_RE = re.compile(r'href="(?P<href>[^"]+)"')

# Fixed columns from the FRONT — identical for both a plain and a brokered ("Tivuch") row, per the
# table's own real header row and the 2026-09-14 live re-dump (diagnose-homeless-tivuch-column-
# layout.yaml) that settled this: checkbox, photo, property type, city, neighborhood, street, rooms.
# Property type isn't currently a field this project stores — its column still counts for position.
_FRONT_FIXED_COLUMN_COUNT = 7  # checkbox(0) photo(1) property_type(2) city(3) neighborhood(4) street(5) rooms(6)
# Fixed columns from the BACK — also identical for both row kinds (same 2026-09-14 re-dump): price,
# entry date, update date, details link. Entry/update date aren't parsed into the output dict at
# all (this project has never needed them) — they only matter here for counting past them.
_BACK_FIXED_COLUMN_COUNT = 4  # price(-4) entry_date(-3) update_date(-2) details_link(-1)

# Confirmed live 2026-09-13 (diagnose-komo-gallery-and-homeless-description.yaml) against a real
# listing's own detail page (id=746758) — a real free-text Hebrew ad description, byte-identical
# in both tags (og:description tried second only as a defensive fallback, not because it's ever
# been seen to differ here).
_DESCRIPTION_RE = re.compile(r'<meta name="Description" content="([^"]*)"', re.I)
_OG_DESCRIPTION_RE = re.compile(r'<meta property="og:description" content="([^"]*)"')

# 2026-09-21: real bug found live (owner's own Telegram screenshots + a DB dump confirming it,
# diagnose-homeless-description-raw-chars.yaml) — 6 of a real 30-listing sample had the SITE'S OWN
# generic description as their "description" instead of a real per-listing one. Not a fetch
# failure: the page genuinely has this as its <meta name="Description"> content — some Homeless
# listing pages simply never got a custom per-listing SEO description filled in, so the page falls
# back to the site's own site-wide default from the base template, which this regex then
# dutifully extracts as if it were real ad content. A substring check (not exact equality) on the
# two most distinctive phrases — safer than pinning the exact full string, which this project has
# only ever seen truncated (DB dumps here cut it at 80 chars) and could easily transcribe a stray
# space/dash wrong.
_GENERIC_SITE_DESCRIPTION_MARKERS = ("בלוח הומלס מחכה לך", "אינסוף מודעות עדכניות")


def _is_generic_site_description(description: str) -> bool:
    return all(marker in description for marker in _GENERIC_SITE_DESCRIPTION_MARKERS)


class HomelessFetchError(RuntimeError):
    """The Fetch API call failed, timed out, or ZenRows itself errored — see the wrapped
    exception. Homeless has shown no bot-challenge wall of its own in any live run so far (unlike
    Yad2's Radware wall) — every failure seen has been a plain HTTP/ZenRows-side problem."""


def _clean(text: str) -> str:
    return text.replace("&nbsp;", " ").strip()


def _parse_price(raw: str) -> int | None:
    digits = re.sub(r"[^0-9]", "", raw)
    return int(digits) if digits else None


def _parse_int(raw: str) -> int | None:
    text = _clean(raw)
    return int(text) if text.isdigit() else None


def _parse_rooms(raw: str) -> float | None:
    text = _clean(raw)
    try:
        return float(text) if text else None
    except ValueError:
        return None


def _get_zenrows_api_key() -> str:
    api_key = os.environ.get(ZENROWS_API_KEY_ENV_VAR, "").strip()
    if not api_key:
        raise HomelessFetchError(
            f"{ZENROWS_API_KEY_ENV_VAR} is not set — see PROJECT_STATE.md. This is the same "
            "ZenRows account/key yad2_client.py and komo_client.py use; Homeless needs only the "
            "cheapest (plain, 1-credit) tier, same as Komo."
        )
    return api_key


def _zenrows_get(url: str, *, context_label: str) -> str:
    """Shared plain-fetch-through-ZenRows mechanics for both the search page and a per-listing
    detail page — same confirmed-plain, 1-credit tier either way (see module docstring)."""
    api_key = _get_zenrows_api_key()

    try:
        response = httpx.get(
            ZENROWS_FETCH_API_URL,
            params={"apikey": api_key, "url": url},
            timeout=PAGE_LOAD_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        raise HomelessFetchError(
            f"ZenRows Fetch API request failed for {context_label}: {exc}"
        ) from exc

    body = response.text
    looks_like_zenrows_error = len(body) < 1000 and _ZENROWS_ERROR_CODE_RE.search(body) is not None
    if response.status_code != 200 or looks_like_zenrows_error:
        code_match = _ZENROWS_ERROR_CODE_RE.search(body)
        title_match = _ZENROWS_ERROR_TITLE_RE.search(body)
        raise HomelessFetchError(
            f"ZenRows returned an error instead of the Homeless page for {context_label}: "
            f"http_status={response.status_code} "
            f"code={code_match.group('code') if code_match else '?'!r} "
            f"title={title_match.group('title') if title_match else '?'!r} — check the ZenRows "
            "dashboard for usage/plan/auth issues."
        )

    return body


def _fetch_search_html() -> str:
    return _zenrows_get(SEARCH_PAGE_URL, context_label="Homeless search page")


def _parse_rows(search_html: str) -> Iterator[dict[str, Any]]:
    # Parameter named `search_html`, not `html` — this module imports the stdlib `html` module
    # (for `html.unescape` below); a same-named parameter would shadow it.
    flat = re.sub(r">\s+<", "><", search_html)  # collapse inter-tag whitespace only, keep tag text
    for row_match in _ROW_RE.finditer(flat):
        external_id = row_match.group("id")
        tds = _TD_RE.findall(row_match.group("body"))

        min_expected = _FRONT_FIXED_COLUMN_COUNT + _BACK_FIXED_COLUMN_COUNT  # 11, Tivuch's own count
        if len(tds) < min_expected:
            logger.warning(
                "Skipping Homeless row id=%s: only %d <td> cells found, expected at least %d "
                "(checkbox+photo+type+city+neighborhood+street+rooms, then price+entrydate+"
                "updatedate+detailslink) — the table's own markup may have changed again.",
                external_id, len(tds), min_expected,
            )
            continue

        image_match = _IMG_SRC_RE.search(tds[1])
        image_url = html.unescape(image_match.group("src")).strip() if image_match else ""

        city = _clean(tds[3]) or None
        neighborhood = _clean(tds[4]) or None
        street = _clean(tds[5]) or None
        rooms = _parse_rooms(tds[6])

        # Everything between "rooms" and the fixed back columns (price/entrydate/updatedate/
        # detailslink) — confirmed live 2026-09-14 (diagnose-homeless-tivuch-column-layout.yaml,
        # 4 real Tivuch rows + 1 real plain row): a PLAIN listing has exactly one such column
        # (floor); a brokered ("Tivuch") listing has NONE at all — its price sits directly after
        # rooms. This was the real, confirmed root cause of Tivuch rows getting a wrong floor AND
        # a wrong price (floor capturing the price string, price capturing the entry-date string)
        # before this fix — previously only flagged as a known gap, not fixed.
        middle = tds[_FRONT_FIXED_COLUMN_COUNT:-_BACK_FIXED_COLUMN_COUNT]
        if len(middle) == 0:
            floor = None  # Tivuch (brokered) row — genuinely has no floor column, not a miss
        elif len(middle) == 1:
            floor = _parse_int(middle[0])  # plain row
        else:
            logger.warning(
                "Homeless row id=%s has %d unexpected extra column(s) between rooms and price "
                "(%r) — expected 0 (Tivuch/brokered) or 1 (floor, plain). Taking the first as "
                "floor and ignoring the rest rather than guessing further.",
                external_id, len(middle), middle,
            )
            floor = _parse_int(middle[0])

        price = _parse_price(tds[-4])

        href_match = _HREF_RE.search(tds[-1])
        if href_match is None:
            logger.warning(
                "Skipping Homeless row id=%s: no href found in its own details-link cell (%r) — "
                "can't build a real detail-page URL for it.", external_id, tds[-1][:200],
            )
            continue
        # The row's own real href — /rent/ for a plain listing, /RentTivuch/ for a brokered one
        # (confirmed live, see module docstring) — never reconstructed from the id.
        detail_url = urljoin(_DETAIL_PAGE_BASE, html.unescape(href_match.group("href")).strip())

        yield {
            "id": external_id,
            "url": detail_url,
            "price": price,
            "rooms": rooms,
            "floor": floor,
            "square_meters": None,  # not present anywhere on this page — see module docstring
            "street": street,
            "neighborhood": neighborhood,
            "city": city,
            "images": [image_url] if image_url else [],
        }


def fetch_search_results() -> Iterator[dict[str, Any]]:
    """Yields raw listing dicts (normalize()-ready, same flat shape as yad2_client._parse_cards)
    for every real listing row found on ONE plain fetch of homeless.co.il/rent/ — confirmed live at
    1 ZenRows credit. See module docstring for the real, still-open question of whether this single
    fetch already covers every current listing or whether the site paginates beyond it."""
    search_html = _fetch_search_html()
    yield from _parse_rows(search_html)


def fetch_listing_description(url: str) -> str | None:
    """Fetches ONE listing's own detail page (its real url, as returned by fetch_search_results —
    see _ROW_RE's own comment on why this can no longer be reconstructed from the id alone: a
    brokered listing's real path is /RentTivuch/, not /rent/) and returns its real free-text
    description, or None on ANY failure (missing API key, network error, non-200, no description
    found) — never raises, same defensive contract as komo_client.fetch_listing_detail. This is
    genuinely OPTIONAL enrichment, unlike Komo's price (see that module's own cost note):
    Homeless's search-results row already has everything else this project needs, so a failed
    description fetch simply means a listing without a description, exactly as before this
    feature existed."""
    try:
        page_html = _zenrows_get(url, context_label=f"Homeless details url={url!r}")
    except HomelessFetchError:
        logger.exception("Failed to fetch Homeless listing detail page: url=%s", url)
        return None

    match = _DESCRIPTION_RE.search(page_html) or _OG_DESCRIPTION_RE.search(page_html)
    if match is None:
        return None
    description = html.unescape(match.group(1)).strip()
    if not description or _is_generic_site_description(description):
        return None
    return description
