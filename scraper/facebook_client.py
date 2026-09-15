"""Fetches raw listing payloads from Facebook Marketplace's property-rentals category feed, and
enriches genuinely new listings with their real city/description from each listing's own detail
page.

STATUS 2026-09-15: SOLVED — confirmed live via
.github/workflows/diagnose-facebook-marketplace-page-structure.yaml, run against the DEDICATED
scraping account's real stored session cookie (never the owner's personal account — see
set-facebook-cookies-secret.yaml's own header comment). Same "never guess at a page structure"
discipline this project's whole scraping history is built on (yad2_client.py needed 8 attempts;
komo_client.py/homeless_client.py were each only written after a live diagnostic) — every field
name below was seen in a real, live response before this file was written, not assumed.

DISCOVERY: https://www.facebook.com/marketplace/category/propertyrentals/ — a plain HTTPS GET with
the Cookie header plus a SPECIFIC set of browser client-hint headers returns a real 200 HTML page.
The Sec-Fetch-*/sec-ch-ua headers are NOT optional: a request carrying only Cookie+User-Agent+
Accept-Language got a genuine http_status=400 "Error" page from Facebook's own edge (confirmed
live, twice) — adding the exact headers a real Chrome navigation sends fixed it. No headless
browser/JS rendering needed at all: every current listing is embedded as GraphQL-shaped JSON inside
<script type="application/json"> blocks (104-107 of them on one real page) — same "plain fetch,
real embedded JSON" shape as homeless_client.py, just with Facebook's own React/Relay framing
instead of a plain HTML table.

Each listing is a MarketplaceFeedListingStory node (matched by __typename, not position — key
order and count have already differed between two real fetches the same day). Its own
for_sale_item (a GroupCommerceProductItem) carries, confirmed live:
    id, marketplace_listing_title (Hebrew), custom_title ("N bedrooms · N bathroom" — Facebook's
    own English bedroom/bathroom count, NOT the Israeli "total rooms" convention this project's own
    `rooms` field means, e.g. a real "3.5 חדרים" listing showed custom_title "3 bedrooms · 1
    bathroom" — so this is never used for `rooms`), formatted_price.text ("₪3,000"), location
    (latitude/longitude ONLY — no city/street text anywhere at this stage), listing_photos (list of
    {image: {uri, width, height}}), marketplace_listing_seller (name/id), story.url (the real
    https://www.facebook.com/marketplace/item/<id>/ permalink), is_sold/is_pending/is_hidden.

ENRICHMENT is REQUIRED, not optional (unlike Homeless's own description-only enrichment) — without
it there is no way to know which city a listing is even in. Confirmed live by fetching
item/1053986910834947's own detail page (the exact listing the owner independently opened in his
own browser and confirmed showed a real address "הרצליה, 46000" plus a street name inside the
description, "רחוב הכוזרי" — neither ever present in the search-feed node above): the SAME
__typename=GroupCommerceProductItem node, now with more fields populated:
    - redacted_description.text: the real free-text Hebrew description — this is the ONLY place a
      street name or the real Israeli "X.5 חדרים" room count appears, when the lister included one;
      never guaranteed, so `rooms`/`street` stay None even after enrichment unless a caller adds its
      own parsing of this text later.
    - home_address.street: despite the key name, this holds only the CITY (e.g. 'הרצליה') —
      Facebook redacts the real street-level address from anyone not actively messaging the seller.
    - reverse_geocode_detailed: a SEPARATE dict elsewhere in the same page (not nested under
      GroupCommerceProductItem, and carries no __typename of its own) — {city, state, postal_code},
      confirmed live {'city': 'הרצליה', 'state': '', 'postal_code': '46000'}. This is the clean,
      structured city fetch_listing_detail actually uses (cities.canonicalize_city handles whatever
      spelling comes back, same as every other source).

fetch_listing_detail is therefore called for EVERY genuinely new listing (never for one already
known — same "enrich once, cache forever" policy as komo_client.fetch_listing_detail/
homeless_client.fetch_listing_description), and scraper/main.py's own _scrape_facebook SKIPS a
listing entirely (not upserted at all, retried automatically next run) rather than upsert it with
city=None — there is no safe fallback for "unknown city" the way there is for Homeless's optional
description.

NOT yet confirmed: whether one fetch of the category page already covers every current rental
listing nationwide, or whether it paginates/varies by account region — same open question
homeless_client.py's own docstring carries for its own single-fetch feed. fetch_search_results
below reads exactly what one plain fetch of the given path returns, nothing more.

Requires FACEBOOK_COOKIES — the dedicated, NEVER personal, account's real session cookie string.
See set-facebook-cookies-secret.yaml's own header comment for why this must never be typed/pasted
anywhere except that workflow's own GitHub Actions form."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Iterator

import httpx

logger = logging.getLogger(__name__)

DEFAULT_URL_PATH = "category/propertyrentals/"
_MARKETPLACE_BASE = "https://www.facebook.com/marketplace/"
_DETAIL_PAGE_BASE = "https://www.facebook.com/marketplace/item/"

FACEBOOK_COOKIES_ENV_VAR = "FACEBOOK_COOKIES"

# Confirmed live 2026-09-15 (diagnose-facebook-marketplace-page-structure.yaml, second run) — a
# request missing these Sec-Fetch-*/sec-ch-ua client-hint headers gets a genuine http_status=400
# "Error" page from Facebook's own edge, even with a fully valid session Cookie. These are the
# exact headers a real Chrome navigation sends, and the exact set that got a real 200.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

PAGE_LOAD_TIMEOUT_S = 30.0

_SCRIPT_JSON_RE = re.compile(r'<script type="application/json"[^>]*>(.*?)</script>', re.S)


class FacebookFetchError(RuntimeError):
    """The request failed, timed out, or Facebook returned a non-200 — its own generic "Error"
    page (a malformed/blocked request), a login/checkpoint wall (the session cookie expired), or a
    real block. See PROJECT_STATE.md's 2026-09-15 Facebook entries for what each of those actually
    looked like when confirmed live."""


def _get_cookie_header() -> str:
    cookie = os.environ.get(FACEBOOK_COOKIES_ENV_VAR, "").strip()
    if not cookie:
        raise FacebookFetchError(
            f"{FACEBOOK_COOKIES_ENV_VAR} is not set — see set-facebook-cookies-secret.yaml. "
            "Facebook Marketplace/Groups require a real logged-in session; there is no anonymous "
            "access."
        )
    return cookie


def _fetch(url: str, *, context_label: str) -> str:
    headers = dict(_BROWSER_HEADERS)
    headers["Cookie"] = _get_cookie_header()
    try:
        response = httpx.get(
            url, headers=headers, timeout=PAGE_LOAD_TIMEOUT_S, follow_redirects=True
        )
    except httpx.HTTPError as exc:
        raise FacebookFetchError(f"Facebook request failed for {context_label}: {exc}") from exc

    if response.status_code != 200:
        raise FacebookFetchError(
            f"Facebook returned http_status={response.status_code} for {context_label} — the "
            "session cookie may have expired and need re-exporting (see "
            "set-facebook-cookies-secret.yaml), or this is a real login/checkpoint wall."
        )
    return response.text


def _iter_json_blocks(html: str) -> Iterator[Any]:
    """Yields every parseable JSON value embedded in the page's own <script type="application/
    json"> blocks — confirmed live these carry Facebook's own real GraphQL-shaped data, not a
    guess. Strips the rare `for (;;);` XSSI-protection prefix and HTML-comment wrapping seen on
    some blocks; a block that still doesn't parse is silently skipped — Facebook embeds many
    unrelated blocks on the same page (config/i18n/glimmer-placeholder data, confirmed live), not
    everything here is listing data."""
    for block in _SCRIPT_JSON_RE.findall(html):
        block = block.strip()
        if block.startswith("for (;;);"):
            block = block[len("for (;;);") :]
        if block.startswith("<!--") and block.endswith("-->"):
            block = block[4:-3].strip()
        if not block:
            continue
        try:
            yield json.loads(block)
        except json.JSONDecodeError:
            continue


def _find_nodes(obj: Any, typename: str) -> Iterator[dict[str, Any]]:
    """Recursively walks a parsed JSON structure for every dict with __typename == typename —
    generic on purpose, never a fixed path/index (this project's own diagnostic runs already saw
    key order and count differ between two real fetches the same day)."""
    if isinstance(obj, dict):
        if obj.get("__typename") == typename:
            yield obj
        for value in obj.values():
            yield from _find_nodes(value, typename)
    elif isinstance(obj, list):
        for item in obj:
            yield from _find_nodes(item, typename)


def _parse_price(text: str | None) -> int | None:
    if not text:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else None


def _parse_listing_story(story: dict[str, Any]) -> dict[str, Any] | None:
    item = story.get("for_sale_item")
    if not isinstance(item, dict):
        return None
    external_id = item.get("id")
    if not external_id:
        return None

    story_info = item.get("story")
    story_info = story_info if isinstance(story_info, dict) else {}
    url = story_info.get("url") or f"{_DETAIL_PAGE_BASE}{external_id}/"

    formatted_price = item.get("formatted_price")
    formatted_price = formatted_price if isinstance(formatted_price, dict) else {}
    price = _parse_price(formatted_price.get("text"))

    images: list[str] = []
    for photo in item.get("listing_photos") or []:
        if not isinstance(photo, dict):
            continue
        image = photo.get("image")
        if isinstance(image, dict) and image.get("uri"):
            images.append(image["uri"])

    return {
        "id": str(external_id),
        "url": url,
        "price": price,
        "images": images,
        # rooms/floor/square_meters/city/neighborhood/street/description are genuinely NOT
        # available at this discovery stage — see module docstring. Never guessed from
        # custom_title's English bedroom count, which is a different number entirely. Filled in
        # (city/description only) by fetch_listing_detail for genuinely new listings.
        "rooms": None,
        "floor": None,
        "square_meters": None,
        "city": None,
        "neighborhood": None,
        "street": None,
    }


def fetch_search_results(url_path: str = DEFAULT_URL_PATH) -> Iterator[dict[str, Any]]:
    """Yields raw listing dicts (normalize()-ready, same flat shape as komo_client's/
    homeless_client's own fetch_search_results) for every real MarketplaceFeedListingStory found on
    ONE fetch of the given Marketplace path. Every dict's city/street/rooms/description are None
    here — see module docstring; fetch_listing_detail fills city/description in separately, for
    genuinely new listings only."""
    html = _fetch(
        f"{_MARKETPLACE_BASE}{url_path}", context_label=f"Marketplace search url_path={url_path!r}"
    )
    seen_ids: set[str] = set()
    for block in _iter_json_blocks(html):
        for story in _find_nodes(block, "MarketplaceFeedListingStory"):
            parsed = _parse_listing_story(story)
            if parsed is None or parsed["id"] in seen_ids:
                continue
            seen_ids.add(parsed["id"])
            yield parsed


def fetch_listing_detail(item_id: str) -> dict[str, Any] | None:
    """Fetches ONE listing's own detail page and returns {"city": str | None, "description":
    str | None}, or None on ANY failure (missing cookie, network error, non-200) — never raises,
    same defensive contract as komo_client.fetch_listing_detail/
    homeless_client.fetch_listing_description. `city` staying None means the real
    reverse_geocode_detailed dict wasn't found on this particular fetch — the caller (scraper/
    main.py) treats that as "not usable yet", never upserting a listing with an unknown city.
    Only ever called for a listing genuinely new to the DB this run."""
    try:
        html = _fetch(
            f"{_DETAIL_PAGE_BASE}{item_id}/", context_label=f"Facebook detail item_id={item_id!r}"
        )
    except FacebookFetchError:
        logger.exception("Failed to fetch Facebook listing detail page: item_id=%s", item_id)
        return None

    city: str | None = None
    description: str | None = None

    def scan(obj: Any) -> None:
        nonlocal city, description
        if isinstance(obj, dict):
            if description is None and obj.get("__typename") == "GroupCommerceProductItem":
                desc = obj.get("redacted_description")
                if (
                    isinstance(desc, dict)
                    and isinstance(desc.get("text"), str)
                    and desc["text"].strip()
                ):
                    description = desc["text"].strip()
            if city is None:
                geocode = obj.get("reverse_geocode_detailed")
                if (
                    isinstance(geocode, dict)
                    and isinstance(geocode.get("city"), str)
                    and geocode["city"].strip()
                ):
                    city = geocode["city"].strip()
            for value in obj.values():
                scan(value)
        elif isinstance(obj, list):
            for entry in obj:
                scan(entry)

    for block in _iter_json_blocks(html):
        scan(block)
        if city is not None and description is not None:
            break

    return {"city": city, "description": description}
