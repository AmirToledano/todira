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

OUTBOUND LINK (found 2026-09-13, NOT fixed — not fixable in this codebase): a real user report
after the first real production Telegram send — clicking a Homeless listing's own "לפרטי הדירה
המלאים" link (e.g. https://www.homeless.co.il/rent/viewad,83480.aspx, this module's own confirmed
URL shape) redirected to Homeless's homepage instead of the listing. Investigated with a real
headless browser (diagnose-homeless-detail-url-and-images.yaml): BOTH the reported-broken id AND
the previously-confirmed-working one (746758) hit a Cloudflare-style "Just a moment..." bot-
challenge page (HTTP 403) — a plain ZenRows fetch bypasses this (that's the whole point of ZenRows,
and how this module already reads real content for description/price/etc.), but an ordinary end
user's own browser clicking the link gets no such help from this project at all. This is Homeless's
own bot-protection on direct/deep-linked access to a listing page, not a URL-construction bug here
— genuinely nothing to change in this module for it. Real challenge pages like this usually resolve
automatically for a genuine (non-automated) browser within a few seconds, so this may simply work
fine for an actual user despite failing in an automated headless-browser test — unconfirmed either
way without a real, non-automated click to compare against.

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

import httpx

logger = logging.getLogger(__name__)

SEARCH_PAGE_URL = "https://www.homeless.co.il/rent/"
# Confirmed live 2026-09-13 (diagnose-komo-gallery-and-homeless-description.yaml) — the same
# real per-listing URL shape fetch_search_results already builds for each row's own "url" field.
DETAIL_PAGE_URL_TEMPLATE = "https://www.homeless.co.il/rent/viewad,{external_id}.aspx"

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

# Matches one real listing row (confirmed live against id="ad_746758" and others — see module
# docstring). The leading `<td class="selectionarea">...</td>` (a checkbox, never useful data) is
# skipped non-greedily rather than matched field-by-field, since its own inner HTML (an <input>
# with its own id/name attributes) isn't needed and its exact attribute order isn't worth pinning
# down. Column order after that is fixed (photo, property type, city, neighborhood, street, rooms,
# floor, price) per the table's own real header row.
#
# 2026-09-13: the photo cell's own <img src="..."> is now CAPTURED, not just matched-and-discarded
# — a real bug found the hard way (a real Telegram send with zero photos): the confirmed real
# sample row for id=746758 has always carried a real photo URL here
# (https://uploads.homeless.co.il/rent/202609/300/nvFile5386664.jpg, see this module's own test
# fixtures) that this regex simply threw away every single time. `[^"]*` (not `[^<]*`) since a src
# URL can't contain `<` but the group must stop at the closing quote, not at some later `<`.
_ROW_RE = re.compile(
    r'<tr[^>]*\bid="ad_(?P<id>\d+)"[^>]*>'
    r'<td[^>]*class="selectionarea"[^>]*>.*?</td>'
    r'<td[^>]*><div><img[^>]*\bsrc="(?P<image_url>[^"]*)"[^>]*/?></div></td>'
    r'<td[^>]*>(?P<property_type>[^<]*)</td>'
    r'<td[^>]*>(?P<city>[^<]*)</td>'
    r'<td[^>]*>(?P<neighborhood>[^<]*)</td>'
    r'<td[^>]*>(?P<street>[^<]*)</td>'
    r'<td[^>]*>(?P<rooms>[^<]*)</td>'
    r'<td[^>]*>(?P<floor>[^<]*)</td>'
    r'<td[^>]*>(?P<price>[^<]*)</td>',
    re.S,
)

# Confirmed live 2026-09-13 (diagnose-komo-gallery-and-homeless-description.yaml) against a real
# listing's own detail page (id=746758) — a real free-text Hebrew ad description, byte-identical
# in both tags (og:description tried second only as a defensive fallback, not because it's ever
# been seen to differ here).
_DESCRIPTION_RE = re.compile(r'<meta name="Description" content="([^"]*)"', re.I)
_OG_DESCRIPTION_RE = re.compile(r'<meta property="og:description" content="([^"]*)"')


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
    # (for `html.unescape` on the description field below); a same-named parameter would shadow it.
    flat = re.sub(r">\s+<", "><", search_html)  # collapse inter-tag whitespace only, keep tag text
    for match in _ROW_RE.finditer(flat):
        external_id = match.group("id")
        rooms = _parse_rooms(match.group("rooms"))
        floor = _parse_int(match.group("floor"))
        neighborhood = _clean(match.group("neighborhood")) or None
        image_url = html.unescape(match.group("image_url")).strip()

        yield {
            "id": external_id,
            "url": f"https://www.homeless.co.il/rent/viewad,{external_id}.aspx",
            "price": _parse_price(match.group("price")),
            "rooms": rooms,
            "floor": floor,
            "square_meters": None,  # not present anywhere on this page — see module docstring
            "street": _clean(match.group("street")) or None,
            "neighborhood": neighborhood,
            "city": _clean(match.group("city")) or None,
            "images": [image_url] if image_url else [],
        }


def fetch_search_results() -> Iterator[dict[str, Any]]:
    """Yields raw listing dicts (normalize()-ready, same flat shape as yad2_client._parse_cards)
    for every real listing row found on ONE plain fetch of homeless.co.il/rent/ — confirmed live at
    1 ZenRows credit. See module docstring for the real, still-open question of whether this single
    fetch already covers every current listing or whether the site paginates beyond it."""
    search_html = _fetch_search_html()
    yield from _parse_rows(search_html)


def fetch_listing_description(external_id: str) -> str | None:
    """Fetches ONE listing's own detail page and returns its real free-text description, or None
    on ANY failure (missing API key, network error, non-200, no description found) — never raises,
    same defensive contract as komo_client.fetch_listing_detail. This is genuinely OPTIONAL
    enrichment, unlike Komo's price (see that module's own cost note): Homeless's search-results
    row already has everything else this project needs, so a failed description fetch simply means
    a listing without a description, exactly as before this feature existed."""
    try:
        page_html = _zenrows_get(
            DETAIL_PAGE_URL_TEMPLATE.format(external_id=external_id),
            context_label=f"Homeless details id={external_id!r}",
        )
    except HomelessFetchError:
        logger.exception("Failed to fetch Homeless listing detail page: id=%s", external_id)
        return None

    match = _DESCRIPTION_RE.search(page_html) or _OG_DESCRIPTION_RE.search(page_html)
    if match is None:
        return None
    description = html.unescape(match.group(1)).strip()
    return description or None
