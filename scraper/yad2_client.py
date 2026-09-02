"""Fetches raw listing payloads from Yad2's rental search.

STATUS 2026-08-29: **SOLVED** after 9 attempts (see YAD2_NOTES.md for the full trail through
attempts 1-8 — direct API, plain/stealth Playwright, patchright alone, manual cookies, 2Captcha).
Attempt 9 combined patchright routed through ZenRows' residential proxy GATEWAY
(`proxy.zenrows.com:8001`) — this correctly got past Yad2's Radware Bot Manager wall, but turned
out to have a serious cost problem never caught until real traffic: with `proxy` set at the
Playwright BROWSER level, every sub-resource the rendered page loaded — not just the main
document, but every listing photo AND every one of Yad2's Next.js JS chunk files
(`_next/static/chunks/*.js`, often dozens per page) — was a SEPARATE request through the proxy,
each billed the full ~25 credits regardless of size (confirmed with ZenRows support 2026-09-02).
A single real page load could cost 750+ credits instead of the ~25 the whole project's budget
math assumed, and burned two ZenRows plans' worth of credits in incidents on 2026-09-01/09-02 —
see PROJECT_STATE.md for the full incident history.

Attempt 10 (this version, 2026-09-02) switches to ZenRows' **Fetch API**
(`api.zenrows.com/v1/`) instead of the raw proxy gateway: we no longer run our own browser at
all — ZenRows renders the page on THEIR OWN infrastructure (still with `js_render=true` +
`premium_proxy=true`, same underlying tech) and returns the final HTML in ONE HTTP response,
billed as ONE flat request regardless of how many images/scripts/chunks that page internally
loaded on their end (confirmed via ZenRows' own docs/product pages — "Fetch: One API call per
URL" — the Extract/Batch products explicitly bill at the same per-request rate as Fetch, with no
separate line item for sub-resources). This is a straight HTTP GET + `block_resources` to skip
images/fonts/media/stylesheets ZenRows' own renderer would otherwise waste time on (a speed
optimization now, not a cost one — the flat per-request billing means blocking sub-resources no
longer changes what we pay) — no local browser, no patchright, no per-request-count safety cap
needed (removed, see git history if that logic is ever needed again for a different product).

The real feed items turned out to be plain server/client-rendered HTML (each a
`<li data-testid="platinum-item">...<a data-nagish="feed-item-layout-link" href="...">` block with
`data-testid="price"/"street-name"/"item-info-line-1st"/"item-info-line-2nd"` spans inside) — NOT
a separate JSON XHR matching a `realestate-feed` URL substring as attempts 1-8 assumed. Parsing is
unchanged from attempt 9 — `_parse_cards` just reads text out of whatever HTML we get back,
whether that HTML arrived via a local browser or ZenRows' own Fetch API.

Requires `ZENROWS_API_KEY` (free tier works — see PROJECT_STATE.md). Yad2 uses numeric city IDs in
its URL, not the slugs configured in `SCRAPE_CITIES` — `CITY_SLUG_TO_ID` below maps the ones this
project currently scrapes; extend it (search "yad2 city id <name>") before adding a new city to
`SCRAPE_CITIES` without also adding it here, or that city will silently fetch zero results.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Iterator
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

SEARCH_PAGE_URL = "https://www.yad2.co.il/realestate/rent"

# Yad2's own numeric city IDs — NOT the human-readable slugs used elsewhere in this project.
# Extended 2026-08-31, twice: first pass covered 24 of bot/cities.py's cities (the largest ones),
# deliberately holding back the rest over ZenRows request-credit cost (each scraped city is a
# recurring cost every 10-minute run, not one-time). Owner explicitly overrode that caution the
# same day ("תוסיף כל מקום וחוק בארץ... אנחנו רוצים להיות זמינים לכל בן אדם") — this second pass
# adds the remaining 18 and makes CITY_SLUG_TO_ID/CITY_SLUG_TO_HEBREW_NAME exhaustive: every city
# bot/cities.py's CITIES list offers in /filter now has a real Yad2 ID, so no selectable city is
# structurally unmatchable anymore. Each ID (both passes) was cross-checked against at least two
# independent yad2.co.il/realestate/rent search-result URLs containing that city's Hebrew name
# (via web search, since this environment can't browse Yad2 directly) — not guessed.
# NOTE: only the cities actually listed in SCRAPE_CITIES (values.yaml / .env.example) get scraped
# — adding an ID here alone does nothing until that env var also includes the slug. See
# values.yaml's own comment: it now lists every city here, per the owner's explicit request.
CITY_SLUG_TO_ID = {
    "tel-aviv": "5000",
    "ramat-gan": "8600",
    "givatayim": "6300",
    "jerusalem": "3000",
    "haifa": "4000",
    "beer-sheva": "9000",
    "rishon-lezion": "8300",
    "petah-tikva": "7900",
    "ashdod": "0070",
    "netanya": "7400",
    "bnei-brak": "6100",
    "holon": "6600",
    "ashkelon": "7100",
    "rehovot": "8400",
    "bat-yam": "6200",
    "beit-shemesh": "2610",
    "kfar-saba": "6900",
    "herzliya": "6400",
    "hadera": "6500",
    "raanana": "8700",
    "nahariya": "9100",
    "eilat": "2600",
    "modiin": "1200",
    "ramat-hasharon": "2650",
    "ramla": "8500",
    "nazareth": "7300",
    "lod": "7000",
    "hod-hasharon": "9700",
    "kiryat-ata": "6800",
    "kiryat-gat": "2630",
    "kiryat-motzkin": "8200",
    "kiryat-bialik": "9500",
    "kiryat-ono": "2620",
    "yavne": "2660",
    "or-yehuda": "2400",
    "tzfat": "8000",
    "afula": "7700",
    "tiberias": "6700",
    "dimona": "2200",
    "mevaseret-zion": "1015",
    "har-gilo": "3603",
    "karmiel": "1139",
}

# Maps each CITY_SLUG_TO_ID slug to the exact Hebrew string bot/cities.py's CITIES list uses for
# it, i.e. the string a user actually selects in /filter and that ends up in filters.cities.
# matching.py compares this verbatim against listings.city (Yad2's own text) — see bot/cities.py's
# module docstring for that caveat, unrelated to and not fixed by this table. This is purely a
# convenience map from this file's English slugs to bot/cities.py's Hebrew names, for anyone
# wiring up more SCRAPE_CITIES entries without re-deriving the pairing by hand.
CITY_SLUG_TO_HEBREW_NAME = {
    "tel-aviv": "תל אביב יפו",
    "ramat-gan": "רמת גן",
    "givatayim": "גבעתיים",
    "jerusalem": "ירושלים",
    "haifa": "חיפה",
    "beer-sheva": "באר שבע",
    "rishon-lezion": "ראשון לציון",
    "petah-tikva": "פתח תקווה",
    "ashdod": "אשדוד",
    "netanya": "נתניה",
    "bnei-brak": "בני ברק",
    "holon": "חולון",
    "ashkelon": "אשקלון",
    "rehovot": "רחובות",
    "bat-yam": "בת ים",
    "beit-shemesh": "בית שמש",
    "kfar-saba": "כפר סבא",
    "herzliya": "הרצליה",
    "hadera": "חדרה",
    "raanana": "רעננה",
    "nahariya": "נהריה",
    "eilat": "אילת",
    "modiin": "מודיעין מכבים רעות",
    "ramat-hasharon": "רמת השרון",
    "ramla": "רמלה",
    "nazareth": "נצרת",
    "lod": "לוד",
    "hod-hasharon": "הוד השרון",
    "kiryat-ata": "קריית אתא",
    "kiryat-gat": "קריית גת",
    "kiryat-motzkin": "קריית מוצקין",
    "kiryat-bialik": "קריית ביאליק",
    "kiryat-ono": "קריית אונו",
    "yavne": "יבנה",
    "or-yehuda": "אור יהודה",
    "tzfat": "צפת",
    "afula": "עפולה",
    "tiberias": "טבריה",
    "dimona": "דימונה",
    "mevaseret-zion": "מבשרת ציון",
    "har-gilo": "הר גילה",
    "karmiel": "כרמיאל",
}

ZENROWS_API_KEY_ENV_VAR = "ZENROWS_API_KEY"
ZENROWS_FETCH_API_URL = "https://api.zenrows.com/v1/"

# `block_resources` is a Fetch API param telling ZenRows' OWN renderer to skip these types — a
# speed optimization (their renderer wastes no time on bytes we never use), NOT a cost one: Fetch
# bills one flat rate per call regardless of what the page loaded internally, unlike attempt 9's
# proxy-gateway approach where every sub-resource was individually billed (see module docstring).
BLOCKED_RESOURCE_TYPES = "image,stylesheet,font,media"

PAGE_LOAD_TIMEOUT_S = 90  # ZenRows' own render round-trip is slow; give it real room

# One card = one <a data-nagish="feed-item-layout-link" href="..."> block containing these four
# data-testid spans, in this order, somewhere inside it (non-greedy match up to the next one).
_CARD_RE = re.compile(
    r'<a class="[^"]*itemLink[^"]*" data-nagish="feed-item-layout-link" href="([^"]+)".*?'
    r'data-testid="price">([^<]*)</span>.*?'
    r'data-testid="street-name">([^<]*)</span>.*?'
    r'data-testid="item-info-line-1st">([^<]*)</span>.*?'
    r'data-testid="item-info-line-2nd">([^<]*)</span>',
    re.S,
)
_DIRECTION_MARKS_RE = re.compile(r"[‎‏]")  # LTR/RTL marks Yad2 wraps numbers in

# Matches ZenRows' own JSON error body (e.g. `{"code":"AUTH004","title":"Usage exceeded
# (AUTH004)",...}`), returned as the HTTP response body directly (not wrapped in an HTML shell —
# that wrapping was specific to attempt 9's browser-based fetch, patchright's own "page content"
# framing). Matches "code" and "title" independently (not a single ordered pattern) since
# RFC-7807-style problem+json doesn't guarantee key order.
_ZENROWS_ERROR_CODE_RE = re.compile(r'"code":"(?P<code>[A-Z0-9]+)"')
_ZENROWS_ERROR_TITLE_RE = re.compile(r'"title":"(?P<title>[^"]*)"')


class Yad2FetchError(RuntimeError):
    """The Fetch API call failed, timed out, or ZenRows itself errored — see the wrapped
    exception. A single failed city shouldn't be common; if it becomes so, check ZenRows'
    dashboard for credit exhaustion or an account issue before assuming Yad2 changed something."""


def _clean(text: str) -> str:
    return _DIRECTION_MARKS_RE.sub("", text).strip()


def _parse_price(raw: str) -> int | None:
    digits = re.sub(r"[^0-9]", "", raw)
    return int(digits) if digits else None


def _parse_info_line_2(raw: str) -> tuple[float | None, int | None, int | None]:
    text = _clean(raw)
    rooms = floor = size = None
    if m := re.search(r"([\d.]+)\s*חדרים", text):
        rooms = float(m.group(1))
    if m := re.search(r"קומה\s*([^\s•]+)", text):
        value = m.group(1)
        floor = 0 if "קרקע" in value else (int(value) if value.isdigit() else None)
    if m := re.search(r"([\d.]+)\s*מ.ר", text):
        size = int(float(m.group(1)))
    return rooms, floor, size


def _parse_location(raw: str) -> tuple[str | None, str | None]:
    """Returns (neighborhood, city) from a comma-separated breadcrumb like
    '<property type>, <neighborhood...>, <city>' — city is always the last segment."""
    parts = [p.strip() for p in _clean(raw).split(",") if p.strip()]
    if not parts:
        return None, None
    city = parts[-1]
    neighborhood = ", ".join(parts[1:-1]) if len(parts) > 2 else None
    return neighborhood, city


def _parse_cards(html: str) -> Iterator[dict[str, Any]]:
    for href, price_raw, street_raw, info1_raw, info2_raw in _CARD_RE.findall(html):
        # Sponsored "new project" cards (`/yad1/project/...`) are marketing listings for a whole
        # development, not one rentable unit — they carry an absolute URL (not relative like real
        # item links) and their "price"/"rooms" describe a range across many units, not a single
        # apartment. Skip them; they don't fit this schema and would pollute the feed.
        if "/yad1/project/" in href or href.startswith("http"):
            continue

        external_id = href.rstrip("/").split("/")[-1].split("?")[0]
        rooms, floor, size_sqm = _parse_info_line_2(info2_raw)
        neighborhood, city = _parse_location(info1_raw)

        yield {
            "id": external_id,
            "url": urljoin(SEARCH_PAGE_URL, href.split("?")[0]),
            "price": _parse_price(price_raw),
            "rooms": rooms,
            "floor": floor,
            "square_meters": size_sqm,
            "street": _clean(street_raw),
            "neighborhood": neighborhood,
            "city": city,
        }


def fetch_search_results(city: str) -> Iterator[dict[str, Any]]:
    """Yields raw listing dicts (already close to normalize()'s expected shape) for one city.
    `city` is the slug used elsewhere in this project (e.g. "tel-aviv") — translated to Yad2's
    own numeric city ID via CITY_SLUG_TO_ID."""
    api_key = os.environ.get(ZENROWS_API_KEY_ENV_VAR, "").strip()
    if not api_key:
        raise Yad2FetchError(
            f"{ZENROWS_API_KEY_ENV_VAR} is not set — see PROJECT_STATE.md for how to get a free "
            "ZenRows trial key. Scraping Yad2 without a residential-proxy service reliably hits "
            "its Radware Bot Manager wall (see YAD2_NOTES.md attempts 1-8)."
        )

    city_id = CITY_SLUG_TO_ID.get(city)
    if city_id is None:
        raise Yad2FetchError(
            f"No Yad2 numeric city ID mapped for slug {city!r} — add it to CITY_SLUG_TO_ID in "
            "yad2_client.py (search \"yad2 city id <name>\" to find it)."
        )

    url = f"{SEARCH_PAGE_URL}?city={city_id}"

    try:
        response = httpx.get(
            ZENROWS_FETCH_API_URL,
            params={
                "apikey": api_key,
                "url": url,
                "js_render": "true",
                "premium_proxy": "true",
                "block_resources": BLOCKED_RESOURCE_TYPES,
            },
            timeout=PAGE_LOAD_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        raise Yad2FetchError(
            f"ZenRows Fetch API request failed for city={city!r}: {exc}"
        ) from exc

    html = response.text

    # ZenRows returning its own JSON error (quota exhausted, auth issue, etc.) instead of the
    # actual page — a non-200 status normally, but checked by body shape too since a quota error
    # has been seen wrapped oddly before (see PROJECT_STATE.md, 2026-08-31: every city was
    # silently parsing 0 cards, root-caused via live logs to `"code":"AUTH004","title":"Usage
    # exceeded (AUTH004)"` — ZenRows account had hit its usage limit, so the scraper never
    # actually reached Yad2 at all, and the 0 cards were mistaken for "genuinely no listings" run
    # after run). Raise instead of silently yielding nothing, so this surfaces as a real error
    # (counted in the run summary) rather than a quietly-empty result.
    looks_like_zenrows_error = len(html) < 1000 and _ZENROWS_ERROR_CODE_RE.search(html) is not None
    if response.status_code != 200 or looks_like_zenrows_error:
        code_match = _ZENROWS_ERROR_CODE_RE.search(html)
        title_match = _ZENROWS_ERROR_TITLE_RE.search(html)
        raise Yad2FetchError(
            f"ZenRows returned an error instead of the Yad2 page for city={city!r}: "
            f"http_status={response.status_code} "
            f"code={code_match.group('code') if code_match else '?'!r} "
            f"title={title_match.group('title') if title_match else '?'!r} — check the ZenRows "
            "dashboard for usage/plan/auth issues."
        )

    yield from _parse_cards(html)


# Yad2's own listing DETAIL page (one specific apartment, not the search-results list) is a
# Next.js page whose server-rendered data is embedded verbatim as a `<script id="__NEXT_DATA__"
# type="application/json">` blob in the HTML — confirmed live 2026-09-02 (see
# .github/workflows/diagnose-listing-detail-page.yaml, one real Jerusalem listing) to hold a
# clean, complete JSON record: price/rooms/floor/size (redundant with the search card, but also
# property type, amenity booleans, a free-text description, the REAL multi-photo image URLs, an
# entrance date, and broker/agency info — none of which the search-results cards this project has
# always scraped ever carry. Reading this embedded JSON is far more reliable than scraping visible
# HTML/icons (which change with every front-end redesign and require guessing at icon meaning).
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def fetch_listing_detail(url: str) -> dict[str, Any] | None:
    """Fetches ONE listing's own detail page and returns its `__NEXT_DATA__` ad record as a plain
    dict (the same shape confirmed live — see this function's module-level comment above), or
    None on ANY failure (missing API key, network error, non-200, no/unparseable __NEXT_DATA__).
    Never raises: this is an enrichment on top of a listing already known from its search card —
    a failed enrichment must never lose or block ingesting that already-known data.

    Costs one ZenRows Fetch API request, same as one search-results page — see this module's
    caller (scraper/main.py) for the cost-bounding rule: only ever called for a listing genuinely
    new to the DB this run, never re-fetched for a listing already known."""
    api_key = os.environ.get(ZENROWS_API_KEY_ENV_VAR, "").strip()
    if not api_key:
        return None

    try:
        response = httpx.get(
            ZENROWS_FETCH_API_URL,
            params={
                "apikey": api_key,
                "url": url,
                "js_render": "true",
                "premium_proxy": "true",
                "block_resources": BLOCKED_RESOURCE_TYPES,
            },
            timeout=PAGE_LOAD_TIMEOUT_S,
        )
    except httpx.HTTPError:
        logger.exception("Failed to fetch Yad2 listing detail page: %s", url)
        return None

    if response.status_code != 200:
        logger.warning(
            "Non-200 fetching Yad2 listing detail page %s: status=%d", url, response.status_code
        )
        return None

    match = _NEXT_DATA_RE.search(response.text)
    if match is None:
        logger.warning("No __NEXT_DATA__ found on Yad2 listing detail page: %s", url)
        return None

    try:
        next_data = json.loads(match.group(1))
        queries = next_data["props"]["pageProps"]["dehydratedState"]["queries"]
        for query in queries:
            data = query.get("state", {}).get("data")
            # "token" is the ad's own id field (confirmed live) — picking the query that actually
            # carries it, rather than blindly trusting queries[0], in case a future page ever
            # embeds more than one query.
            if isinstance(data, dict) and "token" in data:
                return data
        logger.warning("__NEXT_DATA__ had no ad-data query on Yad2 listing detail page: %s", url)
        return None
    except (KeyError, TypeError, IndexError, json.JSONDecodeError):
        logger.exception("Failed to parse __NEXT_DATA__ on Yad2 listing detail page: %s", url)
        return None
