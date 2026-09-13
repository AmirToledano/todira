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
all — confirmed live, not an extraction miss). square_meters is therefore always None from this
source; getting it would need a separate per-listing detail-page fetch, not yet built (see Komo's
own fetch_listing_detail for the equivalent pattern on that source, if this is ever wanted here).

NOT yet confirmed: whether /rent/ paginates for more listings beyond what one fetch returns (Komo
turned out to have ~175 pages behind its own single-page HTML view, Yad2 too — Homeless has not
been checked for the same real "how many total listings does this site actually have vs. how many
one fetch returns" question yet). fetch_search_results below reads exactly what one plain fetch of
the base URL returns and nothing more — treat that as a real, documented open question, not a
silent assumption that it's already complete coverage.

Requires ZENROWS_API_KEY (same account/key as yad2_client.py and komo_client.py)."""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Iterator

import httpx

logger = logging.getLogger(__name__)

SEARCH_PAGE_URL = "https://www.homeless.co.il/rent/"

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
_ROW_RE = re.compile(
    r'<tr[^>]*\bid="ad_(?P<id>\d+)"[^>]*>'
    r'<td[^>]*class="selectionarea"[^>]*>.*?</td>'
    r'<td[^>]*><div><img[^>]*/?></div></td>'
    r'<td[^>]*>(?P<property_type>[^<]*)</td>'
    r'<td[^>]*>(?P<city>[^<]*)</td>'
    r'<td[^>]*>(?P<neighborhood>[^<]*)</td>'
    r'<td[^>]*>(?P<street>[^<]*)</td>'
    r'<td[^>]*>(?P<rooms>[^<]*)</td>'
    r'<td[^>]*>(?P<floor>[^<]*)</td>'
    r'<td[^>]*>(?P<price>[^<]*)</td>',
    re.S,
)


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


def _fetch_search_html() -> str:
    api_key = _get_zenrows_api_key()

    try:
        response = httpx.get(
            ZENROWS_FETCH_API_URL,
            params={"apikey": api_key, "url": SEARCH_PAGE_URL},
            timeout=PAGE_LOAD_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        raise HomelessFetchError(f"ZenRows Fetch API request failed for Homeless: {exc}") from exc

    html = response.text
    looks_like_zenrows_error = len(html) < 1000 and _ZENROWS_ERROR_CODE_RE.search(html) is not None
    if response.status_code != 200 or looks_like_zenrows_error:
        code_match = _ZENROWS_ERROR_CODE_RE.search(html)
        title_match = _ZENROWS_ERROR_TITLE_RE.search(html)
        raise HomelessFetchError(
            f"ZenRows returned an error instead of the Homeless page: "
            f"http_status={response.status_code} "
            f"code={code_match.group('code') if code_match else '?'!r} "
            f"title={title_match.group('title') if title_match else '?'!r} — check the ZenRows "
            "dashboard for usage/plan/auth issues."
        )

    return html


def _parse_rows(html: str) -> Iterator[dict[str, Any]]:
    flat = re.sub(r">\s+<", "><", html)  # collapse inter-tag whitespace only, keep tag text
    for match in _ROW_RE.finditer(flat):
        external_id = match.group("id")
        rooms = _parse_rooms(match.group("rooms"))
        floor = _parse_int(match.group("floor"))
        neighborhood = _clean(match.group("neighborhood")) or None

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
        }


def fetch_search_results() -> Iterator[dict[str, Any]]:
    """Yields raw listing dicts (normalize()-ready, same flat shape as yad2_client._parse_cards)
    for every real listing row found on ONE plain fetch of homeless.co.il/rent/ — confirmed live at
    1 ZenRows credit. See module docstring for the real, still-open question of whether this single
    fetch already covers every current listing or whether the site paginates beyond it."""
    html = _fetch_search_html()
    yield from _parse_rows(html)
