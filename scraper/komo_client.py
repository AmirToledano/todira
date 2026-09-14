"""Fetches raw listing payloads from Komo's rental search (komo.co.il).

STATUS 2026-09-12: real, live pipeline confirmed end-to-end through ZenRows' Fetch API (see
.github/workflows/diagnose-komo-homeless-reachability.yaml, runs #9-#13) — SOLVED, no reverse-
engineering trail like Yad2's needed. Komo turned out to be a classic server-rendered ASP/jQuery
site (no __NEXT_DATA__/__NUXT__, no SPA at all), found via the owner's own live DevTools Network
tab after automated JS-bundle/map-link hunting came up short. The real pipeline is THREE plain
fetches, none needing js_render or premium_proxy (Yad2's forced, expensive tier) — confirmed via
ZenRows' own `X-Request-Credits` response header, always `1` for every one of these:

1. GET code/nadlan/apartments-for-rent.asp?nehes=1&cityName=<Hebrew city name> — a real search
   page. Genuinely client-rendered for its own listing CARDS (confirmed live: zero price matches
   in its own View Source), so this project does NOT parse cards out of it — but it embeds
   `window.sessionToken = "<32-char hex>";` directly in the plain server-rendered HTML, generated
   fresh per page load. That token is the only thing this project actually needs from this page.
2. POST api/modaotservice/adscoordinates/list/ with form body `iska=1&sessionToken=<token>`
   (found via the owner's own DevTools Payload tab) — cheap JSON: `{"status":"OK","list":
   [{"id","uid","lat","lng"}, ...]}`, dozens of entries confirmed live (1MB+ response). This is
   Komo's OWN map-pins endpoint (the owner's own hunch, confirmed correct) — no price, no address,
   just enough to enumerate every listing currently on the map plus its Komo id (`modaaNum`).
   CONFIRMED live 2026-09-13 (diagnose-komo-region-coverage.yaml, prompted by an owner question):
   this endpoint is NATIONWIDE regardless of cityName — a real side-by-side test queried
   "ירושלים" and "תל אביב יפו" (opposite ends of the country) and got back byte-identical
   11,976-id sets. cityName only matters for step 1's own sessionToken issuance, not for what this
   endpoint returns. Use fetch_all_coordinate_ids() (below fetch_coordinate_ids), which calls this
   ONCE, not once per tracked city — the old per-city loop paid 42x (84 credits/run) for the exact
   same data every time before this was confirmed and fixed the same night.
3. GET code/nadlan/details/?modaaNum=<id> — the real per-listing detail page. CONFIRMED against a
   real listing (id 4471462, owner's own "שערי ירושלים 5" / "7,000 ₪" listing) to contain exactly
   the fields below, parsed straight out of its markup (not a JSON API — an actual HTML page, like
   Yad2's own listing cards) — see _parse_details_html for the exact confirmed anchors:
     - price: `<div class="price modaaWPrice"><span class="ModaaWDetailsValue ...">7,000&nbsp;
       &#8362;</span></div>`
     - rooms + city + street: NOT in the visible body markup this project searched — pulled
       instead from `<meta property="og:title" content="להשכרה&nbsp;דירות&nbsp;2 חדרים
       &nbsp;בירושלים, שערי ירושלים 5" />`, a single clean machine-readable string Komo itself
       generates per listing (more reliable than scraping the rendered page for these three).
     - floor + size (מ"ר): a repeating `<div class="<key> firstInfoBlockWrap" ...><div
       class="firstInfo"> <value> </div><div class="firstInfoTitle"> <label></div></div>` stat
       family — `key="floor"` (label "קומה") and `key="mr"` (label מ"ר) confirmed live (floor=1,
       size=38 for the sample listing). The family's other keys (rooms/total-floors/etc, if any)
       were NOT read past floor+mr in the one live diagnostic run before this file was written —
       not needed since rooms already comes from og:title above, but if this project ever wants
       total-floor-count, re-run that diagnostic step with a wider context window first.

IMPORTANT COST NOTE (2026-09-12, matches PROJECT_STATE.md's "חיסכון קרדיטים" mandate): unlike
Yad2 — where the search-results page's own cards/feed already carry price, so a per-listing
fetch_listing_detail call is pure OPTIONAL enrichment (see yad2_client.py) — Komo's adscoordinates
map endpoint carries NO price at all. fetch_listing_detail below is therefore NOT optional: it is
the ONLY way to learn a Komo listing's price, and every listing needs it fetched at least once.
Each call is cheap (1 credit, confirmed), but calling it for EVERY id on EVERY scrape run — not
just newly-discovered ones — would mean paying per already-known listing per run, forever, for no
new information (a listing's price rarely changes minute to minute). Whoever wires this into
scraper/main.py's run_once() should call fetch_listing_detail only for (source, external_id) pairs
not already in the database — exactly the same "only enrich genuinely new rows" rule
_upsert_listings already applies for Yad2's own (unwired) fetch_listing_detail, just mandatory
here instead of optional. NOT done yet — this file only provides the building blocks.

STATUS 2026-09-14: MIGRATED off ZenRows entirely, onto Bright Data's flat-rate ISP proxy (the
same $2/month proxy yad2_client.fetch_map_markers uses for the tel-aviv-area region — see that
module's own comment for the mechanism and cost story). Confirmed live, one endpoint at a time
(diagnose-isp-proxy-coverage-all-sources.yaml for the search page + details page,
diagnose-komo-isp-proxy-full-discovery.yaml for the real two-step discovery flow: session-token
GET + adscoordinates POST, 11,635 real ids returned) that all three of Komo's endpoints — unlike
Yad2's own listing-detail page or Homeless's search page, both of which hit a Cloudflare/Radware-
style block via the same proxy — come back clean with no block at all. Since none of these three
endpoints ever needed ZenRows' expensive js_render/premium_proxy tier to begin with (plain server-
rendered HTML/JSON the whole way, see steps 1-3 above), moving them to a flat-rate proxy with zero
per-request cost is a strict improvement over metered ZenRows credits, not a tradeoff — this frees
up 100% of Komo's own ZenRows spend (previously 2 credits/run discovery + up to
KOMO_MAX_NEW_DETAIL_FETCHES_PER_RUN credits/run for new listings) for Yad2, the source actually
under real credit pressure (see PROJECT_STATE.md's ongoing ZenRows-budget entries).

Requires BRIGHT_DATA_ISP_HOST/BRIGHT_DATA_ISP_USER/BRIGHT_DATA_ISP_PASS (see
dorin_common.bright_data_client's own module docstring) — the same three env vars
scraper-cronjob.yaml already wires in for Yad2's tel-aviv-area migration. No longer needs
ZENROWS_API_KEY at all for anything in this file."""
from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, Iterator
from urllib.parse import urljoin

from dorin_common import bright_data_client
from yad2_client import CITY_SLUG_TO_HEBREW_NAME

logger = logging.getLogger(__name__)

# Komo takes the site's own Hebrew city name directly as a query param (no numeric city id, unlike
# Yad2) — reusing yad2_client's own slug->Hebrew-name table rather than re-deriving all 42 names a
# second time. This assumes Komo's own city-name spelling matches Yad2's/bot/cities.py's Hebrew
# spelling closely enough for its own search form to accept it — confirmed only for ירושלים so
# far (the one city this project's live diagnostics actually used); not yet verified for every
# other slug in that table. A city whose exact Komo-side spelling differs would likely just return
# an empty/wrong search page rather than erroring — worth spot-checking a few more before relying
# on this for every SCRAPE_CITIES entry.
SEARCH_PAGE_URL = "https://www.komo.co.il/code/nadlan/apartments-for-rent.asp"
ADSCOORDINATES_URL = "https://www.komo.co.il/api/modaotservice/adscoordinates/list/"
DETAILS_PAGE_URL = "https://www.komo.co.il/code/nadlan/details/"

# Confirmed live 2026-09-12: `window.sessionToken = "E327BE43D5B24F55A3AD23AA35FF5F2D";` embedded
# directly in the search page's own plain HTML (see module docstring, step 1).
_SESSION_TOKEN_RE = re.compile(r'sessionToken\s*=\s*"([A-Za-z0-9]{16,64})"')

# Confirmed live against modaaNum=4471462 (see module docstring, step 3).
_PRICE_RE = re.compile(r'class="price modaaWPrice"[^>]*>\s*<span[^>]*>([\d,]+)')
_OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]+)"')
# Confirmed live 2026-09-13 (diagnose-komo-homeless-reachability.yaml run #12, re-read while
# investigating why Komo listings never carry a description): a real, free-text Hebrew ad
# description — the poster's own words, not a generated summary — sits in the SAME details page
# this project already fetches for price/rooms/floor/size, at zero extra ZenRows cost. Confirmed
# sample (modaaNum=4471462): `<meta name="Description" content="דירה יוקרתית מושקעת ברמה גבוהה
# עם מיזוג מרכזי וחימום תת רצפתי...">`. This was simply never looked for until now — nothing
# about Komo's own page structure made it unavailable, unlike Yad2's search-results feed (which
# genuinely has no description field at all, see normalize.py's own history).
_DESCRIPTION_RE = re.compile(r'<meta name="Description" content="([^"]*)"', re.I)
# Confirmed live 2026-09-13 (diagnose-komo-detail-images.yaml, then diagnose-komo-gallery-and-
# homeless-description.yaml): the SAME sample listing (modaaNum=4471462) has a real og:image tag
# AND a real desktopPics/tmunotDesktop photo gallery with 4 distinct real photos total (og:image's
# own picNum plus 3 more) — confirmed genuinely this listing's own, not a "same ads" (recommended
# listings) carousel's OTHER photos further down the same page, by checking that every one of
# those 4 picNums appears strictly BEFORE the page's own "sameads"/"cItemWrap" markup, while the
# carousel's own (different) photos appear only after it. og:image kept as the ordering-independent
# single-photo fallback (a page's own og:image always describes itself); _extract_gallery_images
# below is the real multi-photo source, scoped to that confirmed boundary.
_OG_IMAGE_RE = re.compile(r'<meta property="og:image" content="([^"]+)"')
_GALLERY_IMG_RE = re.compile(r'<img[^>]+src="(/api/modaot/tmunot/showPic/list/[^"]+)"')
_SAME_ADS_BOUNDARY_RE = re.compile(r"sameads|cItemWrap")
_ROOMS_RE = re.compile(r"([\d.]+)\s*חדרים")
# Matches the city name right after "חדרים" and Hebrew's own "ב" (=\"in\") prefix, up to the
# comma that separates it from the street — e.g. "...2 חדרים  בירושלים, שערי ירושלים 5" ->
# "ירושלים". Multi-word cities (e.g. "תל אביב") are expected to work the same way ("בתל אביב")
# since the ב prefix simply glues onto the city name with no space in standard Hebrew, but this
# has only actually been confirmed live for ירושלים.
_OG_TITLE_CITY_RE = re.compile(r"חדרים\s*ב(.+)$")


def _firstinfo_block_re(class_name: str) -> re.Pattern[str]:
    """Builds the regex for one `firstInfoBlockWrap` stat box by its own class name (e.g.
    "floor", "mr") — see module docstring's step 3 for the confirmed real markup shape this
    matches. A helper instead of one regex per field since every box shares the same structure."""
    return re.compile(
        rf'class="{re.escape(class_name)} firstInfoBlockWrap"[^>]*>\s*'
        r'<div class="firstInfo"[^>]*>\s*([^<]+?)\s*<'
    )


_FLOOR_RE = _firstinfo_block_re("floor")
_SIZE_SQM_RE = _firstinfo_block_re("mr")


def _extract_gallery_images(page_html: str, *, modaa_num: str) -> list[str]:
    """Every real photo belonging to THIS listing, full URLs, in page order, de-duplicated (the
    confirmed sample page repeats each picNum's <img> tag more than once — once per responsive
    desktop/mobile layout — for the SAME real photo). See _GALLERY_IMG_RE's own comment for why
    this is scoped to before the "sameads"/cItemWrap boundary rather than every <img> on the page.
    Falls back to scanning the whole page if that boundary marker isn't found at all (logged, not
    silently assumed safe) — better one possibly-extra photo than zero, since a false grab from an
    unrelated "same ads" listing would need Komo to have removed that marker AND placed different
    real content in what would now be an unrecognizable location, an unlikely combination."""
    boundary_match = _SAME_ADS_BOUNDARY_RE.search(page_html)
    if boundary_match is None:
        logger.warning(
            "No sameads/cItemWrap boundary found on Komo details page for modaaNum=%s — "
            "scanning the whole page for gallery images instead of stopping at a confirmed "
            "boundary; a same-ads photo could theoretically leak in here.",
            modaa_num,
        )
        searchable = page_html
    else:
        searchable = page_html[: boundary_match.start()]

    seen_paths: dict[str, None] = {}
    for match in _GALLERY_IMG_RE.finditer(searchable):
        seen_paths.setdefault(html.unescape(match.group(1)), None)
    return [urljoin(DETAILS_PAGE_URL, path) for path in seen_paths]


class KomoFetchError(RuntimeError):
    """A Komo fetch failed outright — Bright Data's ISP proxy request itself failed (see
    bright_data_client.fetch_via_isp_proxy/_post's own docstrings for their failure modes: missing
    config, network error, non-200), or Komo's own response wasn't the expected shape. Komo has
    shown no bot-challenge wall of its own in any live run so far (unlike Yad2's Radware wall) —
    every failure seen has been a plain HTTP/proxy-side problem."""


def _isp_proxy_get(url: str, *, context_label: str) -> str:
    """Shared ISP-proxy GET mechanics for the search page and detail page fetches below — raises
    KomoFetchError (never returns None) so every caller keeps the same try/except shape it always
    had, matching yad2_client.fetch_map_markers' own "raise on failure" convention for a primary
    fetch (as opposed to fetch_listing_detail's own "return None" contract for optional
    enrichment — see that function for where this distinction actually matters)."""
    body = bright_data_client.fetch_via_isp_proxy(url)
    if body is None:
        raise KomoFetchError(
            f"Bright Data ISP proxy failed to fetch {context_label}: {url} — see its own logs "
            "for the specific failure (missing config, network error, or non-200 status)."
        )
    return body


def _isp_proxy_post(url: str, data: dict[str, str], *, context_label: str) -> str:
    """POST counterpart to _isp_proxy_get above — used only by fetch_coordinate_ids' own second
    stage (the adscoordinates/list/ endpoint, which requires a POST body, not a GET)."""
    body = bright_data_client.fetch_via_isp_proxy_post(url, data)
    if body is None:
        raise KomoFetchError(
            f"Bright Data ISP proxy failed to POST to {context_label}: {url} — see its own logs "
            "for the specific failure (missing config, network error, or non-200 status)."
        )
    return body


def _extract_session_token(search_page_html: str) -> str | None:
    match = _SESSION_TOKEN_RE.search(search_page_html)
    return match.group(1) if match else None


def fetch_coordinate_ids(city: str) -> list[dict[str, str]]:
    """Stage 1+2: resolves `city` (a slug from this project's own SCRAPE_CITIES, e.g. "jerusalem")
    to Komo's search page, extracts its embedded sessionToken, then POSTs that token to Komo's own
    map-pins endpoint. Returns the raw `list` array — each item a dict with (at least) "id" (the
    modaaNum needed by fetch_listing_detail), "uid", "lat", "lng". Carries NO price/address/rooms
    — see module docstring's cost note for why a further per-listing fetch is required, not
    optional, before any of these can be shown to a user.

    2026-09-13: CONFIRMED live (diagnose-komo-region-coverage.yaml) that `city` does NOT actually
    filter this endpoint at all — a real side-by-side test queried "ירושלים" and "תל אביב יפו"
    (opposite ends of the country) and got back byte-identical 11,976-id sets. cityName only
    matters for issuing step 1's own sessionToken, not for what step 2 (the coordinates endpoint
    itself) returns — this function is kept as-is (still genuinely useful, e.g. if this ever needs
    re-verifying against a specific city later) but production code should call
    fetch_all_coordinate_ids() below instead of looping this per city — see that function and
    scraper/main.py's _scrape_komo for the real cost this fixed (84 credits/run -> 2).

    Two real requests through Bright Data's flat-rate ISP proxy (2026-09-14 — see module docstring's
    STATUS entry) — zero per-request cost either way, unlike the ZenRows credits this used to
    spend; this function is cheap to call for every SCRAPE_CITIES entry every run regardless."""
    hebrew_name = CITY_SLUG_TO_HEBREW_NAME.get(city)
    if hebrew_name is None:
        raise KomoFetchError(
            f"No Hebrew city name mapped for slug {city!r} — add it to "
            "yad2_client.CITY_SLUG_TO_HEBREW_NAME (Komo reuses that same table; see this module's "
            "own top-level comment for why)."
        )

    search_url = f"{SEARCH_PAGE_URL}?nehes=1&cityName={hebrew_name}"
    search_html = _isp_proxy_get(search_url, context_label=f"komo search page city={city!r}")

    session_token = _extract_session_token(search_html)
    if session_token is None:
        raise KomoFetchError(
            f"No sessionToken found in Komo's search page for city={city!r} — Komo may have "
            "changed how/where it embeds this value (see module docstring, step 1). Re-run "
            "diagnose-komo-homeless-reachability.yaml before assuming this is a transient error."
        )

    body = _isp_proxy_post(
        ADSCOORDINATES_URL,
        {"iska": "1", "sessionToken": session_token},
        context_label=f"komo adscoordinates city={city!r}",
    )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise KomoFetchError(
            f"Komo's adscoordinates response for city={city!r} wasn't valid JSON: {exc}"
        ) from exc
    if payload.get("status") != "OK":
        raise KomoFetchError(
            f"Komo's adscoordinates endpoint returned a non-OK status for city={city!r}: "
            f"{payload.get('status')!r}"
        )
    listing_ids = payload.get("list")
    if not isinstance(listing_ids, list):
        raise KomoFetchError(
            f"Komo's adscoordinates response for city={city!r} had no usable 'list' array: "
            f"{payload!r}"
        )
    return listing_ids


# 2026-09-13: see fetch_coordinate_ids' own docstring for the confirmed finding (identical
# 11,976-id sets for Jerusalem and Tel Aviv) that makes this the correct way to call it now — ANY
# valid city slug returns the same nationwide data, so "tel-aviv" here is an arbitrary but
# guaranteed-valid pick (already in CITY_SLUG_TO_HEBREW_NAME), not a meaningful choice of region.
_NATIONWIDE_COVERAGE_CITY_SLUG = "tel-aviv"


def fetch_all_coordinate_ids() -> list[dict[str, str]]:
    """Komo's adscoordinates endpoint is confirmed nationwide regardless of which city is queried
    (see fetch_coordinate_ids' own docstring) — this is the one real call scraper/main.py's
    _scrape_komo should make per run instead of looping over every tracked city (this used to
    matter for ZenRows credits — 84/run vs 2/run — before the 2026-09-14 ISP-proxy migration made
    it free either way; still the right call, one real request pair instead of 42 identical ones).
    Returns exactly what fetch_coordinate_ids(_NATIONWIDE_COVERAGE_CITY_SLUG) would."""
    return fetch_coordinate_ids(_NATIONWIDE_COVERAGE_CITY_SLUG)


def _parse_details_html(page_html: str, *, modaa_num: str) -> dict[str, Any] | None:
    """Parses one Komo listing detail page (see module docstring, step 3) into a raw dict shaped
    like yad2_client._parse_cards' own output (id/url/price/rooms/floor/square_meters/street/
    neighborhood/city) for downstream consistency. Returns None (logging why) rather than raising
    on a missing/malformed page — same defensive contract as yad2_client.fetch_listing_detail:
    a failed detail fetch for one listing must never abort the whole scrape.

    Parameter named `page_html`, not `html` — this module imports the stdlib `html` module (for
    `html.unescape` on the description field below); a same-named parameter would shadow it for
    the whole function body."""
    price_match = _PRICE_RE.search(page_html)
    if price_match is None:
        logger.warning("No price found on Komo details page for modaaNum=%s", modaa_num)
        return None
    price = int(price_match.group(1).replace(",", ""))

    og_title_match = _OG_TITLE_RE.search(page_html)
    if og_title_match is None:
        logger.warning("No og:title found on Komo details page for modaaNum=%s", modaa_num)
        return None
    # og:title looks like "להשכרה&nbsp;דירות&nbsp;2 חדרים  &nbsp;בירושלים, שערי ירושלים 5" — a
    # comma always separates "<rooms text> ב<city>" from "<street> <house number>" (confirmed live
    # for the one sample listing; see module docstring step 3).
    og_title = og_title_match.group(1).replace("&nbsp;", " ")
    head, _, street_part = og_title.partition(",")

    rooms_match = _ROOMS_RE.search(head)
    rooms = float(rooms_match.group(1)) if rooms_match else None

    city_match = _OG_TITLE_CITY_RE.search(head)
    city = city_match.group(1).strip() if city_match else None

    street = street_part.strip() or None

    floor_match = _FLOOR_RE.search(page_html)
    floor = int(floor_match.group(1)) if floor_match and floor_match.group(1).isdigit() else None

    size_match = _SIZE_SQM_RE.search(page_html)
    square_meters = (
        int(size_match.group(1)) if size_match and size_match.group(1).isdigit() else None
    )

    description_match = _DESCRIPTION_RE.search(page_html)
    description = html.unescape(description_match.group(1)).strip() if description_match else None

    images = _extract_gallery_images(page_html, modaa_num=modaa_num)
    if not images:
        # Fallback only — a page whose gallery markup doesn't match _GALLERY_IMG_RE for some
        # reason (a future Komo markup change) still gets its one confirmed og:image rather than
        # nothing, same benefit-of-the-doubt policy as every other optional field here.
        og_image_match = _OG_IMAGE_RE.search(page_html)
        if og_image_match:
            images = [urljoin(DETAILS_PAGE_URL, html.unescape(og_image_match.group(1)))]

    return {
        "id": modaa_num,
        "url": urljoin(DETAILS_PAGE_URL, f"?modaaNum={modaa_num}"),
        "price": price,
        "rooms": rooms,
        "floor": floor,
        "square_meters": square_meters,
        "description": description,
        "images": images,
        "street": street,
        "neighborhood": None,  # not present anywhere on Komo's own details page — see docstring
        "city": city,
    }


def fetch_listing_detail(modaa_num: str) -> dict[str, Any] | None:
    """Stage 3: fetches ONE Komo listing's detail page and returns a raw dict, or None on ANY
    failure (missing ISP proxy config, network error, non-200, unparseable page) — never raises,
    matching yad2_client.fetch_listing_detail's own defensive contract. See module docstring's cost
    note: unlike Yad2's same-named function, this one is NOT optional enrichment — it's the only
    source of price for a Komo listing, so it must be called at least once per genuinely new
    listing."""
    try:
        page_html = _isp_proxy_get(
            f"{DETAILS_PAGE_URL}?modaaNum={modaa_num}",
            context_label=f"komo details modaaNum={modaa_num!r}",
        )
    except KomoFetchError:
        logger.exception("Failed to fetch Komo listing detail page: modaaNum=%s", modaa_num)
        return None
    return _parse_details_html(page_html, modaa_num=modaa_num)


def fetch_search_results(city: str) -> Iterator[dict[str, Any]]:
    """Convenience wrapper matching yad2_client.fetch_search_results' own signature/shape: yields
    one fully-priced raw listing dict per id currently on Komo's map for `city`, by calling
    fetch_coordinate_ids then fetch_listing_detail for EVERY id it returns.

    WARNING — read module docstring's cost note before calling this in a real scrape loop: this
    fetches EVERY listing's detail page EVERY time it's called (one real request pair, then N more
    for N listings), with no "already known, skip it" logic of its own — that logic needs the
    caller's own database state (which ids are already known), which this module has no access to.
    Even with the 2026-09-14 ISP-proxy migration removing the per-request ZenRows cost, re-fetching
    every already-known listing every run is still real, unnecessary request volume against Komo's
    own servers — this function exists mainly for manual/one-off use (e.g. a diagnostic run);
    scraper/main.py's real integration should very likely call fetch_coordinate_ids +
    fetch_listing_detail directly so it can skip already-known ids itself, not use this wrapper
    as-is."""
    for item in fetch_coordinate_ids(city):
        modaa_num = item.get("id")
        if not modaa_num:
            continue
        detail = fetch_listing_detail(str(modaa_num))
        if detail is not None:
            yield detail
