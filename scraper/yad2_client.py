"""Fetches raw listing payloads from Yad2's rental search.

STATUS 2026-08-29: **SOLVED** after 9 attempts (see YAD2_NOTES.md for the full trail through
attempts 1-8 — direct API, plain/stealth Playwright, patchright alone, manual cookies, 2Captcha).
Attempt 9 combines two pieces: patchright (still needed — its CDP-leak patches are what stop an
opaque silent fingerprint block) routed through **ZenRows' residential proxy gateway**
(`proxy.zenrows.com:8001`, `premium_proxy=true&js_render=true` passed via the proxy password
field) instead of this container's own datacenter IP. Zero Radware/hCaptcha challenges seen across
repeated real requests once IP reputation stopped being the blocker — the earlier attempts'
fingerprint/session work was necessary but not sufficient; the datacenter IP itself was always
going to get flagged eventually.

The real feed items turned out to be plain server/client-rendered HTML (each a
`<li data-testid="platinum-item">...<a data-nagish="feed-item-layout-link" href="...">` block with
`data-testid="price"/"street-name"/"item-info-line-1st"/"item-info-line-2nd"` spans inside) — NOT
a separate JSON XHR matching a `realestate-feed` URL substring as attempts 1-8 assumed. That
assumption was never actually verified (see the old FEED_URL_MARKER approach, removed here) and
turned out to be wrong; parsing the rendered HTML directly is simpler anyway.

Requires `ZENROWS_API_KEY` (free tier works — see PROJECT_STATE.md). Yad2 uses numeric city IDs in
its URL, not the slugs configured in `SCRAPE_CITIES` — `CITY_SLUG_TO_ID` below maps the ones this
project currently scrapes; extend it (search "yad2 city id <name>") before adding a new city to
`SCRAPE_CITIES` without also adding it here, or that city will silently fetch zero results.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Iterator
from urllib.parse import urljoin

from patchright.sync_api import TimeoutError as PlaywrightTimeoutError
from patchright.sync_api import sync_playwright

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
ZENROWS_PROXY_SERVER = "http://proxy.zenrows.com:8001"
ZENROWS_PROXY_PARAMS = "js_render=true&premium_proxy=true"

PAGE_LOAD_TIMEOUT_MS = 75_000  # ZenRows' own render+proxy round-trip is slow; give it real room
POST_LOAD_WAIT_MS = 9_000  # extra settle time for client-side rendering after domcontentloaded

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
# (AUTH004)",...}`), which patchright still hands back as "page content" wrapped in a minimal
# <html><body><pre>...</pre></body></html> shell — a 200-ish response, not a network failure, so
# it would otherwise look exactly like a real page with zero matching cards on it. Matches "code"
# and "title" independently (not a single ordered pattern) since RFC-7807-style problem+json
# doesn't guarantee key order.
_ZENROWS_ERROR_CODE_RE = re.compile(r'"code":"(?P<code>[A-Z0-9]+)"')
_ZENROWS_ERROR_TITLE_RE = re.compile(r'"title":"(?P<title>[^"]*)"')


class Yad2FetchError(RuntimeError):
    """The page never loaded through the proxy, or ZenRows itself errored — see the wrapped
    exception. A single failed city shouldn't be common; if it becomes so, check ZenRows'
    dashboard for trial-credit exhaustion or an account issue before assuming Yad2 changed
    something."""


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

    with sync_playwright() as p:
        proxy = {
            "server": ZENROWS_PROXY_SERVER,
            "username": api_key,
            "password": ZENROWS_PROXY_PARAMS,
        }
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"], proxy=proxy)
        try:
            context = browser.new_context(locale="he-IL", ignore_https_errors=True)
            page = context.new_page()
            # `proxy` is set at the BROWSER level above, so every sub-resource this page loads —
            # not just the main document — is a separate request through ZenRows' proxy, billed
            # individually (confirmed with ZenRows support 2026-09-02, after an incident where one
            # diagnostic run alone produced 1,172+ billed requests to img.yad2.co.il: a real Yad2
            # search page renders dozens of listing-card photos, and each one was a full ~25-credit
            # proxy request despite us never using the image bytes — _parse_cards only reads text
            # out of the HTML). Blocking image/media/font before they ever leave the browser cuts
            # the real per-city cost by whatever multiple those sub-resources represented, with zero
            # effect on what gets parsed (script/stylesheet/XHR stay unblocked — script in particular
            # is why js_render=true is used at all, for the client-side-rendered card markup).
            page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ("image", "media", "font")
                else route.continue_(),
            )
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
            except PlaywrightTimeoutError as exc:
                raise Yad2FetchError(
                    f"Page never loaded for city={city!r} within {PAGE_LOAD_TIMEOUT_MS}ms via "
                    "the ZenRows proxy — check ZenRows dashboard for credit/quota issues; this "
                    "combo has otherwise been reliable in testing."
                ) from exc

            page.wait_for_timeout(POST_LOAD_WAIT_MS)
            try:
                page.wait_for_load_state("networkidle", timeout=20_000)
            except PlaywrightTimeoutError:
                pass  # best-effort — the fixed wait above already gives rendering time

            html = page.content()
        finally:
            browser.close()

    # ZenRows returning its own JSON error (quota exhausted, auth issue, etc.) instead of the
    # actual page shows up as a tiny, fixed-shape HTML shell wrapping a `<pre>{"code":"AUTH...
    # This was diagnosed 2026-08-31: every city was silently parsing 0 cards, root-caused via
    # live logs to `"code":"AUTH004","title":"Usage exceeded (AUTH004)"` — ZenRows account had
    # hit its usage limit, so the scraper never actually reached Yad2 at all, ever, and the 0
    # cards were mistaken for "genuinely no listings" run after run. Raise instead of silently
    # yielding nothing, so this surfaces as a real error (counted in the run summary) rather than
    # a quietly-empty result — check the ZenRows dashboard for plan/usage if this fires again.
    if len(html) < 1000 and (code_match := _ZENROWS_ERROR_CODE_RE.search(html)) is not None:
        title_match = _ZENROWS_ERROR_TITLE_RE.search(html)
        raise Yad2FetchError(
            f"ZenRows returned an API error instead of the Yad2 page for city={city!r}: "
            f"code={code_match.group('code')!r} "
            f"title={title_match.group('title') if title_match else '?'!r} — check the ZenRows "
            "dashboard for usage/plan/auth issues."
        )

    yield from _parse_cards(html)
