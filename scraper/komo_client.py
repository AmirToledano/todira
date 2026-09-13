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

Requires ZENROWS_API_KEY (same account/key already used for yad2_client.py — this is the same
paid ZenRows Fetch API infrastructure, not a separate cost account). See yad2_client.py's own
module docstring for why ZenRows (a legitimate paid service) is used here and not custom
bot-detection-bypass code — same reasoning, same infra, different (much cheaper) target site.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Iterator
from urllib.parse import urljoin

import httpx

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

ZENROWS_API_KEY_ENV_VAR = "ZENROWS_API_KEY"
ZENROWS_FETCH_API_URL = "https://api.zenrows.com/v1/"

# All three of Komo's endpoints are confirmed plain-fetchable (1 ZenRows credit each) — no
# js_render, no premium_proxy, unlike Yad2's forced 25-credit tier. Deliberately NOT passing
# block_resources either: that Fetch API param only matters when ZenRows is doing its own browser
# rendering (js_render=true), which none of these requests use.
PAGE_LOAD_TIMEOUT_S = 60

# Confirmed live 2026-09-12: `window.sessionToken = "E327BE43D5B24F55A3AD23AA35FF5F2D";` embedded
# directly in the search page's own plain HTML (see module docstring, step 1).
_SESSION_TOKEN_RE = re.compile(r'sessionToken\s*=\s*"([A-Za-z0-9]{16,64})"')

# Same shape/reasoning as yad2_client._ZENROWS_ERROR_CODE_RE/_ZENROWS_ERROR_TITLE_RE — ZenRows'
# own JSON error body (quota/auth issues), not wrapped in any HTML shell. See that module's own
# comment for the full reasoning; duplicated here rather than imported since these two client
# modules are deliberately kept independently readable (see yad2_client.py's own file-per-source
# convention already established in this project).
_ZENROWS_ERROR_CODE_RE = re.compile(r'"code":"(?P<code>[A-Z0-9]+)"')
_ZENROWS_ERROR_TITLE_RE = re.compile(r'"title":"(?P<title>[^"]*)"')

# Confirmed live against modaaNum=4471462 (see module docstring, step 3).
_PRICE_RE = re.compile(r'class="price modaaWPrice"[^>]*>\s*<span[^>]*>([\d,]+)')
_OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]+)"')
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


class KomoFetchError(RuntimeError):
    """A Komo/ZenRows fetch failed outright (bad API key, ZenRows account issue, network error,
    or a non-200 from Komo itself). Unlike Yad2, Komo has shown no bot-challenge wall of its own
    in any live run so far — every failure seen has been a plain HTTP/ZenRows-side problem."""


def _get_zenrows_api_key() -> str:
    api_key = os.environ.get(ZENROWS_API_KEY_ENV_VAR, "").strip()
    if not api_key:
        raise KomoFetchError(
            f"{ZENROWS_API_KEY_ENV_VAR} is not set — see PROJECT_STATE.md. This is the same "
            "ZenRows account/key yad2_client.py uses; Komo just needs its cheapest (plain, 1-"
            "credit) tier, not Yad2's forced premium_proxy+js_render tier."
        )
    return api_key


def _check_zenrows_response(response: httpx.Response, *, context_label: str) -> str:
    """Shared response-validation for all three Komo endpoints — raises KomoFetchError on a
    ZenRows-side error body or non-200; otherwise returns the raw text body. Mirrors
    yad2_client._fetch_search_html's own ZenRows-error check, minus the Yad2-specific antibot
    marker (never seen from Komo — see KomoFetchError's own docstring)."""
    body = response.text
    looks_like_zenrows_error = len(body) < 1000 and _ZENROWS_ERROR_CODE_RE.search(body) is not None
    if response.status_code != 200 or looks_like_zenrows_error:
        code_match = _ZENROWS_ERROR_CODE_RE.search(body)
        title_match = _ZENROWS_ERROR_TITLE_RE.search(body)
        raise KomoFetchError(
            f"ZenRows returned an error instead of the Komo page for {context_label}: "
            f"http_status={response.status_code} "
            f"code={code_match.group('code') if code_match else '?'!r} "
            f"title={title_match.group('title') if title_match else '?'!r} — check the ZenRows "
            "dashboard for usage/plan/auth issues."
        )
    return body


def _zenrows_get(url: str, *, context_label: str) -> str:
    """Plain GET through ZenRows' Fetch API — no js_render/premium_proxy, confirmed 1 credit for
    every Komo endpoint (see module docstring). Shared by all three fetch stages below."""
    api_key = _get_zenrows_api_key()
    try:
        response = httpx.get(
            ZENROWS_FETCH_API_URL,
            params={"apikey": api_key, "url": url},
            timeout=PAGE_LOAD_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        raise KomoFetchError(f"ZenRows Fetch API request failed for {context_label}: {exc}") from exc
    return _check_zenrows_response(response, context_label=context_label)


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

    Two real requests, both confirmed 1 credit each (2 credits total per call, regardless of how
    many listings come back) — this function alone is cheap to call for every SCRAPE_CITIES entry
    every run; the cost this project actually needs to manage lives in fetch_listing_detail."""
    hebrew_name = CITY_SLUG_TO_HEBREW_NAME.get(city)
    if hebrew_name is None:
        raise KomoFetchError(
            f"No Hebrew city name mapped for slug {city!r} — add it to "
            "yad2_client.CITY_SLUG_TO_HEBREW_NAME (Komo reuses that same table; see this module's "
            "own top-level comment for why)."
        )

    search_url = f"{SEARCH_PAGE_URL}?nehes=1&cityName={hebrew_name}"
    search_html = _zenrows_get(search_url, context_label=f"komo search page city={city!r}")

    session_token = _extract_session_token(search_html)
    if session_token is None:
        raise KomoFetchError(
            f"No sessionToken found in Komo's search page for city={city!r} — Komo may have "
            "changed how/where it embeds this value (see module docstring, step 1). Re-run "
            "diagnose-komo-homeless-reachability.yaml before assuming this is a transient error."
        )

    api_key = _get_zenrows_api_key()
    try:
        response = httpx.post(
            ZENROWS_FETCH_API_URL,
            params={"apikey": api_key, "url": ADSCOORDINATES_URL},
            data={"iska": "1", "sessionToken": session_token},
            timeout=PAGE_LOAD_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        raise KomoFetchError(
            f"ZenRows Fetch API request failed for komo adscoordinates city={city!r}: {exc}"
        ) from exc
    body = _check_zenrows_response(response, context_label=f"komo adscoordinates city={city!r}")

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
    _scrape_komo should make per run (2 ZenRows credits total) instead of looping over every
    tracked city (84 credits/run for the exact same data, every time). Returns exactly what
    fetch_coordinate_ids(_NATIONWIDE_COVERAGE_CITY_SLUG) would."""
    return fetch_coordinate_ids(_NATIONWIDE_COVERAGE_CITY_SLUG)


def _parse_details_html(html: str, *, modaa_num: str) -> dict[str, Any] | None:
    """Parses one Komo listing detail page (see module docstring, step 3) into a raw dict shaped
    like yad2_client._parse_cards' own output (id/url/price/rooms/floor/square_meters/street/
    neighborhood/city) for downstream consistency. Returns None (logging why) rather than raising
    on a missing/malformed page — same defensive contract as yad2_client.fetch_listing_detail:
    a failed detail fetch for one listing must never abort the whole scrape."""
    price_match = _PRICE_RE.search(html)
    if price_match is None:
        logger.warning("No price found on Komo details page for modaaNum=%s", modaa_num)
        return None
    price = int(price_match.group(1).replace(",", ""))

    og_title_match = _OG_TITLE_RE.search(html)
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

    floor_match = _FLOOR_RE.search(html)
    floor = int(floor_match.group(1)) if floor_match and floor_match.group(1).isdigit() else None

    size_match = _SIZE_SQM_RE.search(html)
    square_meters = (
        int(size_match.group(1)) if size_match and size_match.group(1).isdigit() else None
    )

    return {
        "id": modaa_num,
        "url": urljoin(DETAILS_PAGE_URL, f"?modaaNum={modaa_num}"),
        "price": price,
        "rooms": rooms,
        "floor": floor,
        "square_meters": square_meters,
        "street": street,
        "neighborhood": None,  # not present anywhere on Komo's own details page — see docstring
        "city": city,
    }


def fetch_listing_detail(modaa_num: str) -> dict[str, Any] | None:
    """Stage 3: fetches ONE Komo listing's detail page and returns a raw dict, or None on ANY
    failure (missing API key, network error, non-200, unparseable page) — never raises, matching
    yad2_client.fetch_listing_detail's own defensive contract. See module docstring's cost note:
    unlike Yad2's same-named function, this one is NOT optional enrichment — it's the only source
    of price for a Komo listing, so it must be called at least once per genuinely new listing."""
    try:
        html = _zenrows_get(
            f"{DETAILS_PAGE_URL}?modaaNum={modaa_num}",
            context_label=f"komo details modaaNum={modaa_num!r}",
        )
    except KomoFetchError:
        logger.exception("Failed to fetch Komo listing detail page: modaaNum=%s", modaa_num)
        return None
    return _parse_details_html(html, modaa_num=modaa_num)


def fetch_search_results(city: str) -> Iterator[dict[str, Any]]:
    """Convenience wrapper matching yad2_client.fetch_search_results' own signature/shape: yields
    one fully-priced raw listing dict per id currently on Komo's map for `city`, by calling
    fetch_coordinate_ids then fetch_listing_detail for EVERY id it returns.

    COST WARNING — read module docstring's cost note before calling this in a real scrape loop:
    this fetches every listing's detail page every time it's called (2 + N ZenRows credits for N
    listings), with no "already known, skip it" logic of its own — that logic needs the caller's
    own database state (which ids are already known), which this module has no access to. This
    function exists mainly for manual/one-off use (e.g. a diagnostic run); scraper/main.py's real
    integration should very likely call fetch_coordinate_ids + fetch_listing_detail directly so it
    can skip already-known ids itself, not use this wrapper as-is."""
    for item in fetch_coordinate_ids(city):
        modaa_num = item.get("id")
        if not modaa_num:
            continue
        detail = fetch_listing_detail(str(modaa_num))
        if detail is not None:
            yield detail
