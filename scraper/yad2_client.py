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

2026-09-03: added `fetch_all_listings` — a confirmed-live (not guessed) alternative to the per-city
`fetch_search_results` loop above, chasing the same "closer to real-time, like dorin.app" goal via
a different lever: 7 broad-region requests (REGION_SLUGS) instead of 42 per-city ones, ~6x cheaper
per full-country sweep on the same ZenRows plan already in use. See that function's own
module-level comment for the full reasoning and why it isn't wired into scraper/main.py yet.
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

# Yad2's OWN bot-challenge page text (not a ZenRows error — js_render+premium_proxy got a response,
# but Yad2's Radware Bot Manager wall itself is what came back instead of the real search page).
# Confirmed 2026-09-03 via an independent, already-working open-source Yad2 scraper
# (github.com/DavOstx7/yad2-scraper's ANTIBOT_CONTENT_IDENTIFIER constant), not verified live
# through this project's own ZenRows pipeline yet. Worth checking for because right now a Yad2-side
# block would just look like "0 cards this run" — indistinguishable from a genuinely quiet city —
# instead of surfacing as the real, debuggable error it is.
_YAD2_ANTIBOT_MARKER = "Are you for real"


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
    if "סטודיו" in text:
        # A studio's info line reads "סטודיו", never "N חדרים", so the regex below never matches
        # it — found live 2026-09-07: every studio listing got rooms=None, and matching.py's
        # rooms_range check has no benefit-of-the-doubt for missing rooms (unlike most other
        # fields), so ANY filter with a room-count range hard-failed every studio, even a range
        # like rooms_min=1 that should logically include one. Treating a studio as 1 room is this
        # project's own documented convention (see dorin_common.enums's STUDIO property type).
        rooms = 1.0
    elif m := re.search(r"([\d.]+)\s*חדרים", text):
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


# The search-results page (the one this project already fetches for every city, every run) turns
# out to embed the SAME kind of Next.js __NEXT_DATA__ hydration JSON a listing's own detail page
# does (see fetch_listing_detail's docstring below) — but here it covers EVERY listing on the
# page, categorized into `private`/`agency`/`platinum`/`booster` (real per-unit ads; "yad1" is
# sponsored whole-development marketing, already excluded from card parsing above for the same
# reason) — confirmed live 2026-09-02 against a real Jerusalem search page (see
# .github/workflows/diagnose-search-page-feed-shape.yaml): nearly every record carries real photo
# URLs (`metaData.images`) and a `tags` list (feature badges like "חניה"/"מעלית"/'ממ"ד'). This
# means real photos + amenity signals + a reliable broker/private distinction come from a request
# this project already pays for — no per-listing detail-page fetch needed (that path,
# fetch_listing_detail below, costs a real ~25 ZenRows credits PER LISTING and was rejected as too
# expensive to run automatically; kept as a separate, deliberately-unused-by-default utility, not
# wired into the normal scrape path — see scraper/main.py).
#
# The one thing NOT available here that the detail page has: a free-text description. Getting that
# would still mean paying for a per-listing fetch.
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

_FEED_CATEGORY_IS_BROKER = {
    "private": False,
    "agency": True,
    "platinum": True,
    "booster": True,
    # "yad1" (sponsored development/project ads) deliberately excluded - not a real per-unit
    # listing, already filtered out of card parsing via the /yad1/project/ check above.
}


def _extract_feed_records(html: str) -> dict[str, dict[str, Any]]:
    """Best-effort: maps each listing's Yad2 `token` (== the external id `_parse_cards` extracts
    from its card href) to its richer feed record — real photos, feature `tags`, and a confirmed
    broker/private category — embedded in the SAME search-page HTML already fetched (see the
    module comment above `_NEXT_DATA_RE`). Returns {} on any failure (missing/malformed
    __NEXT_DATA__): this is a free bonus enrichment layered on top of `_parse_cards`'s own
    regex-based parsing, never required for that to keep working."""
    match = _NEXT_DATA_RE.search(html)
    if match is None:
        return {}
    try:
        next_data = json.loads(match.group(1))
        queries = next_data["props"]["pageProps"]["dehydratedState"]["queries"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return {}

    records: dict[str, dict[str, Any]] = {}
    for query in queries:
        data = query.get("state", {}).get("data")
        if not isinstance(data, dict):
            continue
        for category, is_broker in _FEED_CATEGORY_IS_BROKER.items():
            items = data.get(category)
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("token"), str):
                    records[item["token"]] = {**item, "_is_broker_listing": is_broker}
    return records


def _parse_cards(html: str) -> Iterator[dict[str, Any]]:
    feed_records = _extract_feed_records(html)

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

        item = {
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
        feed_record = feed_records.get(external_id)
        if feed_record is not None:
            item["_feed_record"] = feed_record
        yield item


def _get_zenrows_api_key() -> str:
    api_key = os.environ.get(ZENROWS_API_KEY_ENV_VAR, "").strip()
    if not api_key:
        raise Yad2FetchError(
            f"{ZENROWS_API_KEY_ENV_VAR} is not set — see PROJECT_STATE.md for how to get a free "
            "ZenRows trial key. Scraping Yad2 without a residential-proxy service reliably hits "
            "its Radware Bot Manager wall (see YAD2_NOTES.md attempts 1-8)."
        )
    return api_key


def _fetch_search_html(url: str, *, context_label: str) -> str:
    """Fetches one Yad2 search-results URL through ZenRows' Fetch API and returns the raw HTML,
    or raises Yad2FetchError. Shared by fetch_search_results (one city) and fetch_all_listings
    (the whole country, unfiltered) — `context_label` is only used to make error messages say
    which caller/URL failed (e.g. "city='tel-aviv'" or "page=2")."""
    api_key = _get_zenrows_api_key()

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
        raise Yad2FetchError(f"ZenRows Fetch API request failed for {context_label}: {exc}") from exc

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
            f"ZenRows returned an error instead of the Yad2 page for {context_label}: "
            f"http_status={response.status_code} "
            f"code={code_match.group('code') if code_match else '?'!r} "
            f"title={title_match.group('title') if title_match else '?'!r} — check the ZenRows "
            "dashboard for usage/plan/auth issues."
        )

    if _YAD2_ANTIBOT_MARKER in html:
        raise Yad2FetchError(
            f"Yad2's own bot-challenge page came back for {context_label} instead of the real "
            "search page (js_render+premium_proxy didn't get past it this time) — this is Yad2 "
            "itself blocking the request, not a ZenRows account/quota issue."
        )

    return html


def fetch_search_results(city: str) -> Iterator[dict[str, Any]]:
    """Yields raw listing dicts (already close to normalize()'s expected shape) for one city.
    `city` is the slug used elsewhere in this project (e.g. "tel-aviv") — translated to Yad2's
    own numeric city ID via CITY_SLUG_TO_ID."""
    city_id = CITY_SLUG_TO_ID.get(city)
    if city_id is None:
        raise Yad2FetchError(
            f"No Yad2 numeric city ID mapped for slug {city!r} — add it to CITY_SLUG_TO_ID in "
            "yad2_client.py (search \"yad2 city id <name>\" to find it)."
        )

    html = _fetch_search_html(f"{SEARCH_PAGE_URL}?city={city_id}", context_label=f"city={city!r}")
    yield from _parse_cards(html)


# 2026-09-03: chasing the same goal as CITY_SLUG_TO_ID/fetch_search_results above (near-real-time
# coverage like the reference bot dorin.app appears to have) but from a different angle — one
# request per REGION instead of one request PER CITY (42 requests to cover everywhere, at ~25
# credits each — 1,050 credits per full sweep).
#
# First attempt (bare SEARCH_PAGE_URL with no filter at all, page=2/3/... for pagination) was
# WRONG and is gone — confirmed live 2026-09-03 via a throwaway pod on the real cluster (image
# ghcr.io/amirtoledano/todira-scraper, real ZENROWS_API_KEY from the todira-bot-secret), not
# guessed: the bare URL returns a real 200 page (no antibot block, __NEXT_DATA__ present) but ZERO
# listing cards — it's Yad2's "lobby" page (`lobbyData.recommendationsTitle` etc.), not a results
# feed. Yad2 apparently does require SOME area filter to show a results feed at all (matches the
# "לפני שנמשיך" behavior already seen when trying to set up an Alert with no area picked — see
# PROJECT_STATE.md) — this isn't a restriction worth trying to bypass, just how the site works.
#
# BUT that same lobby page's `lobbyData.recommendationLinks` embeds exactly 7 broad region URLs
# (`/rent/<slug>`) covering the whole country — extracted live from the real `__NEXT_DATA__` JSON,
# not invented: center-and-sharon, tel-aviv-area, jerusalem-area, south, coastal-north,
# north-and-valleys, partnership/east (see REGION_SLUGS below). Also confirmed live: fetching
# .../rent/tel-aviv-area returned 43 real cards spanning multiple cities in one request — תל אביב
# יפו, רמת גן, גבעתיים, בת ים, חולון all showed up in a single response (see PROJECT_STATE.md for
# the full output). That's a materially different, coarser area taxonomy than the dozens of
# fine-grained areas Yad2's own /filter "אזור" dropdown and paid Alerts feature offer (also seen
# live the same day) — not the same list, don't confuse the two. It doesn't need to be: each
# listing's own city still comes from parsing its own card (_parse_location), same as
# fetch_search_results — querying a broad region just means "cast a wider net per request," it
# doesn't change how a listing gets matched to a city or a user afterwards.
#
# Math: 7 regions × ~25 credits = ~175 credits per full-country sweep, vs. 1,050 for the 42-city
# loop — about 6x cheaper per sweep, on the SAME ZenRows plan the project already pays for (Build,
# 45,000 credits/mo): 45,000 / 175 ≈ 257 sweeps/month ≈ once every ~2.8 hours, with no plan
# upgrade at all. See PROJECT_STATE.md for the full cost table at other ZenRows tiers.
#
# NOT wired into scraper/main.py's run_once() yet — that still needs deciding: whether this
# REPLACES the per-city loop entirely or runs alongside it, and reworking _mark_delisted (currently
# scoped by the specific city slugs passed into that run — a region sweep doesn't pick cities in
# advance, it only knows which cities it actually saw after parsing results, and a single sweep
# isn't guaranteed to surface every city in a region if that city genuinely has nothing new right
# now — delisting logic needs to account for that difference before this goes live).
REGION_SLUGS = (
    "center-and-sharon",
    "tel-aviv-area",
    "jerusalem-area",
    "south",
    "coastal-north",
    "north-and-valleys",
    "partnership/east",
)


def fetch_all_listings(regions: tuple[str, ...] = REGION_SLUGS) -> Iterator[dict[str, Any]]:
    """Yields raw listing dicts from Yad2's broad-region rental searches — REGION_SLUGS by
    default, 7 requests covering the whole country instead of 42 (one per city). Each region
    returns whatever's on its first results page (same "rely on scan frequency, not deep
    pagination" design as fetch_search_results above) spanning many cities at once — a listing's
    own city still comes from parsing its own card via _parse_cards, not from which region was
    queried."""
    for region in regions:
        html = _fetch_search_html(
            f"https://www.yad2.co.il/realestate/rent/{region}", context_label=f"region={region!r}"
        )
        yield from _parse_cards(html)


# Yad2's own listing DETAIL page (one specific apartment, not the search-results list) uses the
# same __NEXT_DATA__ hydration mechanism as the search page (see _NEXT_DATA_RE and the comment
# above _extract_feed_records) and, for a single listing, additionally carries a free-text
# description (confirmed live 2026-09-02, see .github/workflows/diagnose-listing-detail-page.yaml)
# — the one field the search page's own feed records don't have.
#
# NOT wired into the normal scrape path (see scraper/main.py / normalize.py's enrich_from_detail):
# each call is a real, separate ~25-ZenRows-credit request, rejected as too expensive to run
# automatically per new listing once real per-listing cost was understood (see PROJECT_STATE.md,
# 2026-09-02). Kept as a deliberately unused-by-default, already-validated utility — e.g. for a
# possible future explicit/opt-in "fetch the full description for listing X" feature — rather than
# deleted and potentially rebuilt later.
def fetch_listing_detail(url: str) -> dict[str, Any] | None:
    """Fetches ONE listing's own detail page and returns its `__NEXT_DATA__` ad record as a plain
    dict, or None on ANY failure (missing API key, network error, non-200, no/unparseable
    __NEXT_DATA__). Never raises: this is an enrichment on top of a listing already known from its
    search card — a failed enrichment must never lose or block ingesting that already-known data.

    Costs one ZenRows Fetch API request, same as one search-results page. Not currently called by
    anything in the normal scrape path — see this function's module-level comment above."""
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
