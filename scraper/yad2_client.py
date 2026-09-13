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

2026-09-13: added `fetch_map_markers` — a completely different, MUCH cheaper source for the same
kind of data, found live by the owner in his own browser's DevTools (Network tab, filtered on
"bbox" while panning/zooming Yad2's own results map): a plain GET to
`gw.yad2.co.il/realestate-feed/rent/map?area=&region=&bBox=&zoom=` returns real, rich per-listing
JSON (price, address down to house number/floor, exact lat/lon, roomsCount, squareMeter, and
PHOTOS — all in one response, confirmed live to return 200 markers in a single call, vs. ~43-46
cards from one fetch_all_listings region request). ZenRows itself flatly refuses this endpoint at
every tier (REQS002, same as www.yad2.co.il — see
.github/workflows/diagnose-yad2-map-api-cost.yaml) — this instead goes through Bright Data's Web
Unlocker API (dorin_common.bright_data_client.fetch_via_web_unlocker, a DIFFERENT Bright Data
product from the Data Collector API scraper/main.py already uses for detail-page enrichment),
confirmed live to succeed on both this map API and the plain search page (see
diagnose-yad2-bright-data-cost.yaml) at $1.50 per 1,000 SUCCESSFUL requests only — dramatically
cheaper than ZenRows' forced ~25-credit tier, per real numbers from the owner's own Bright Data
dashboard, not a guess.

NOT wired into scraper/main.py's run_once() yet, deliberately — this is a bigger architectural
change than fetch_all_listings was (a different provider, a different data shape, and the real
bBox/area/region values needed to cover the whole country haven't been worked out yet, only the
one bbox the owner's own browser happened to be showing). Kept as a real, tested, ready building
block — the actual production switch-over is a follow-up decision, not made here."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Iterator
from urllib.parse import urljoin

import httpx
from dorin_common import bright_data_client

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
    returns whatever's on its first results page only — see fetch_region_pages below (added
    2026-09-12) for the version that actually keeps paging when there's more new volume than one
    page holds; scraper/main.py's run_once() uses that one now, not this function directly. Kept
    as-is (unchanged single-page behavior) since it's still a reasonable plain building block and
    existing tests pin its exact request-building behavior."""
    for region in regions:
        html = _fetch_search_html(
            f"https://www.yad2.co.il/realestate/rent/{region}", context_label=f"region={region!r}"
        )
        yield from _parse_cards(html)


def _region_url(region: str, page: int) -> str:
    """Builds one region's rental-feed URL for a given page number. Confirmed live 2026-09-12 (the
    owner clicked Yad2's own "2" page-number control and read the resulting URL back):
    `?page=<n>` appended to a region URL — page 1 has no query param at all (matches what
    fetch_all_listings above already sends unchanged)."""
    base = f"https://www.yad2.co.il/realestate/rent/{region}"
    return base if page <= 1 else f"{base}?page={page}"


# 2026-09-12: fetch_all_listings above only ever reads ONE results page per region (43-46 real
# cards, confirmed live) — fine exactly as long as fewer new listings appear between two scrape
# runs than one page holds, but the owner found live (via Yad2's own page-number UI) that
# tel-aviv-area alone has ~175 total pages of listings. There is no way to know "one page is
# always enough" is actually true without either checking real posting velocity, or removing the
# assumption entirely — this function does the latter.
#
# fetch_region_pages pages forward (page=1, 2, 3, ... via _region_url above) until a FULL page's
# listings are all already-known (source, external_id) pairs this project's own database already
# has — not a fixed page count, not a guessed "typical" posting rate. A quiet run between scrapes
# still costs exactly one ZenRows request per region (unchanged from fetch_all_listings); a busy
# one costs however many pages it actually took to catch up, and no more. This directly answers
# the owner's real requirement ("אני רוצה שכל ה-500 יהיו אצלי בבוט", 2026-09-12) without hardcoding
# any assumed volume threshold.
#
# Deliberately stops only when EVERY card on a page is already known, not on the FIRST known card
# seen: Yad2's feed interleaves paid-promotion categories (platinum/booster — see
# _FEED_CATEGORY_IS_BROKER) that can resurface an older, already-known ad ahead of genuinely new
# organic listings in that same page's ordering (this project has not independently re-verified
# that resurfacing live, this reasoning is inferred from _parse_cards/_extract_feed_records'
# own module comments about those categories — but stopping on "all known" costs nothing extra
# when it happens not to apply, and meaningfully reduces the risk when it does, so there's no
# reason to take the cheaper-but-riskier "first known" shortcut). This is NOT a mathematical
# guarantee against every possible reordering — genuine certainty would mean walking all ~175
# pages every run, rejected outright as financially unworkable (175 requests × 25 ZenRows credits
# each, for ONE region, versus this project's entire 45,000-credit monthly plan). Documented here
# as a known, accepted limitation rather than a solved problem.
#
# max_pages is a hard safety cap, not an expected value — hitting it logs a warning (real, unusual
# posting volume, or the catch-up check itself misbehaving, e.g. known_ids not actually covering
# this region) rather than silently looping forever or silently stopping short with no signal
# either way.
def fetch_region_pages(
    region: str, known_ids: set[str], *, max_pages: int = 15
) -> Iterator[dict[str, Any]]:
    """Yields every raw listing dict found while paging through `region`'s rental feed (page 1,
    2, 3, ...) until a full page's listings are all already in `known_ids`, or there are no more
    pages. `known_ids` should be every external_id this project already has for Yad2 (across all
    regions/cities — a listing's region isn't tracked separately, so this isn't scoped per-region)
    — the caller (scraper/main.py) owns fetching that from the database; this module has no DB
    access of its own, same separation as everywhere else in this file.

    Costs exactly one real ZenRows request per page actually fetched: 1 on a quiet run (identical
    cost to fetch_all_listings before this function existed), more only when there's genuinely new
    volume to catch up on. max_pages caps the worst case at `max_pages` requests for this one
    region — see the module comment above for the full reasoning."""
    for page in range(1, max_pages + 1):
        html = _fetch_search_html(
            _region_url(region, page), context_label=f"region={region!r} page={page}"
        )
        cards = list(_parse_cards(html))
        if not cards:
            break  # ran out of real pages before max_pages — nothing left to catch up on
        yield from cards
        if all(card["id"] in known_ids for card in cards):
            break  # caught up: every listing on this page was already known
    else:
        logger.warning(
            "region=%r hit max_pages=%d while paginating without catching up to already-known "
            "listings — either genuinely unusual posting volume, or the catch-up check itself "
            "isn't working right for this region (e.g. known_ids not covering it). Consider "
            "raising max_pages or investigating live before assuming this is fine.",
            region, max_pages,
        )


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


# 2026-09-13: see module docstring for the full discovery story (owner's own DevTools) and cost
# comparison. This is a real, separate Yad2 endpoint — not the same one _parse_cards/fetch_all_listings
# read from — reached via Bright Data's Web Unlocker instead of ZenRows (ZenRows refuses it outright,
# REQS002, at every tier — confirmed live, see diagnose-yad2-map-api-cost.yaml).
MAP_API_URL = "https://gw.yad2.co.il/realestate-feed/rent/map"


class Yad2MapFetchError(RuntimeError):
    """fetch_map_markers failed outright — Bright Data's Web Unlocker request itself failed (see
    bright_data_client.fetch_via_web_unlocker's own docstring for its failure modes), or it
    succeeded but returned something that isn't the expected {"data": {"markers": [...]}} shape."""


def _build_map_url(bbox: str, *, area: int, region: int, zoom: int) -> str:
    return f"{MAP_API_URL}?area={area}&region={region}&bBox={bbox}&zoom={zoom}"


def _marker_to_raw_item(marker: dict[str, Any]) -> dict[str, Any] | None:
    """Converts one raw map-API marker record into the same flat shape _parse_cards yields
    (id/url/price/rooms/floor/square_meters/street/neighborhood/city) so normalize() handles either
    source identically — see that function's `_get(raw_item, ...)` fallback-key lookups, which this
    output is deliberately built to satisfy (using the SAME key names _parse_cards already uses,
    e.g. "square_meters" not "squareMeter", "rooms" not "roomsCount"). Also includes "images"
    (a key normalize() already checks) since, unlike a plain search card, this source carries real
    photo URLs for free — no separate detail-page fetch needed to get them.

    Returns None (never raises) for a marker missing its "token" (the only field this project has
    no fallback for — without it there's no external_id to key a Listing row on at all), matching
    _parse_cards' and fetch_listing_detail's shared "skip what's unusable, never abort the whole
    batch over one bad record" convention."""
    token = marker.get("token")
    if not token:
        return None

    address = marker.get("address")
    address = address if isinstance(address, dict) else {}
    house = address.get("house")
    house = house if isinstance(house, dict) else {}
    additional = marker.get("additionalDetails")
    additional = additional if isinstance(additional, dict) else {}
    meta = marker.get("metaData")
    meta = meta if isinstance(meta, dict) else {}

    def _address_text(field: str) -> str | None:
        value = address.get(field)
        return value.get("text") if isinstance(value, dict) else None

    street_text = _address_text("street")
    house_number = house.get("number")
    # Matches the same "<street name> <house number>" shape a real Yad2 card's own street-name
    # span already carries (see _CARD_RE) — confirmed live house_number is a plain int (94), not a
    # pre-formatted string, on the one real marker this was built against (see module docstring).
    street = f"{street_text} {house_number}".strip() if street_text and house_number else street_text

    images = meta.get("images")
    image_urls = (
        [url for url in images if isinstance(url, str) and url.strip()]
        if isinstance(images, list)
        else []
    )

    item: dict[str, Any] = {
        "id": str(token),
        "url": f"https://www.yad2.co.il/item/{token}",
        "price": marker.get("price"),
        "rooms": additional.get("roomsCount"),
        "floor": house.get("floor"),
        "square_meters": additional.get("squareMeter"),
        "street": street,
        "neighborhood": _address_text("neighborhood"),
        "city": _address_text("city"),
    }
    if image_urls:
        item["images"] = image_urls
    return item


def fetch_map_markers(
    bbox: str, *, area: int, region: int, zoom: int = 11
) -> Iterator[dict[str, Any]]:
    """Yields raw listing dicts (normalize()-ready, same shape as _parse_cards) from Yad2's own
    map-markers API for one bounding box — see module docstring for the real cost/coverage numbers
    (confirmed live: 200 markers in ONE request, vs. ~43-46 from one fetch_all_listings region
    request, at a small fraction of the cost since this goes through Bright Data's Web Unlocker,
    not ZenRows).

    `bbox` is Yad2's own comma-separated "south,west,north,east" string (confirmed live from the
    owner's own browser — see module docstring); `area`/`region` are Yad2's own numeric ids for
    the broader area being searched (3 = "תל אביב והסביבה" in the one real example this was built
    against — NOT yet mapped out for other areas/regions; a caller covering more of the country
    needs to find those ids the same way this one was found, live, before assuming they follow any
    particular numbering pattern). `zoom` defaults to 11, matching the one real confirmed request.

    Raises Yad2MapFetchError on any failure (missing Bright Data config, network error, non-200,
    unparseable/unexpected JSON shape) — unlike fetch_listing_detail's "return None" contract,
    this matches fetch_all_listings/fetch_region_pages' own "raise, don't silently yield nothing"
    convention for a primary discovery source, so a real outage surfaces as a countable error
    rather than a silently-empty run."""
    url = _build_map_url(bbox, area=area, region=region, zoom=zoom)
    body = bright_data_client.fetch_via_web_unlocker(url)
    if body is None:
        raise Yad2MapFetchError(
            f"Bright Data Web Unlocker failed to fetch Yad2's map API: {url} — see its own logs "
            "for the specific failure (missing config, network error, or non-200 status)."
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise Yad2MapFetchError(f"Yad2 map API response for {url} wasn't valid JSON: {exc}") from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    markers = data.get("markers") if isinstance(data, dict) else None
    if not isinstance(markers, list):
        raise Yad2MapFetchError(
            f"Yad2 map API response for {url} had no usable 'data.markers' list: "
            f"{str(payload)[:500]!r}"
        )

    for marker in markers:
        if not isinstance(marker, dict):
            continue
        item = _marker_to_raw_item(marker)
        if item is not None:
            yield item
