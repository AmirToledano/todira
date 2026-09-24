"""Fetches raw listing payloads from Homeless's rental and sale search (homeless.co.il/rent/,
homeless.co.il/sale/).

STATUS 2026-09-24: REBUILT after a real site redesign broke the original 2026-09-13 implementation.
Confirmed live (diagnose-homeless-pagination.yaml) two separate, related changes on Homeless's own
side:

1. The search page no longer server-renders its listing grid into plain HTML a non-JS fetch can
   read — a PLAIN ZenRows fetch (the original 1-credit tier this module used to run on) now returns
   ZenRows' own `RESP001 "Could not get content"` error, confirmed happening live, not a stale
   tracking entry. The page's own markup carries real Cloudflare Rocket Loader markers
   (`__cfRLUnblockHandlers`, `data-cf-modified-...` on the search form) — Rocket Loader defers
   script execution until real JS runs, which is almost certainly why a non-JS fetch no longer gets
   real content. `js_render=true` (ZenRows renders with a real browser) DOES get the real page back
   — confirmed live: a real 200 with real listing cards and real ₪ prices — at a real, meaningfully
   higher cost (5 ZenRows credits vs. the old plain tier's 1, confirmed via the real
   X-Request-Credits response header). This module now always sends js_render=true for the SEARCH
   page. The per-listing DETAIL page (fetch_listing_description) was NOT re-tested against this
   same redesign — left on the plain tier for now since it's optional enrichment; revisit if it
   turns out to need js_render too.

2. The listing grid's own markup changed from a plain HTML <table> of <tr id="ad_<id>"> rows (the
   original 2026-09-13 finding) to a <div>-based card grid — confirmed live against several real
   cards on both /rent/ and /sale/:

    <div id="ad_710102" class="image-carousel">
        <div>
            <a class="R promotedAd" href="/rent/viewad,710102.aspx"
               title="דירה, 3 חדרים, שד.מנחם בגין, כפר הים  ">
                <img src="https://uploads.homeless.co.il/rent/202405/300/nvFile5334656.jpeg" alt="...">
                 <div class="promotedAdLabel">מקודמת</div>   <!-- promoted listings only -->
                <div class="price">
                   6,000 ₪
                </div>
                <h3 class="desc" ...>
                   <span>דירה</span>&nbsp;להשכרה ברמת אביב&nbsp;•&nbsp;<!-- optional neighborhood after • -->
                <div class="custom-divider"></div>
                    2.5 חדרים • 40 מ"ר • קומה 2
                </h3>
            </a>
            <input type="checkbox" id="chk_746287" ...>
            ...
        </div>
    </div>

   The real upside: this new markup carries square meters (מ"ר) directly in the card — the OLD
   table never had a מ"ר column at all (see the 2026-09-13 STATUS note this replaces), so
   square_meters was always None from this source before. It's a real, populated field now.

   The <a>'s own `title` attribute is a clean, comma-separated "<type>, <rooms> חדרים, <street>,
   <city>" string — confirmed live across every real card seen — used here for city/street (more
   reliable than parsing the free-text <h3> description). The <h3>'s own second line (after the
   <div class="custom-divider">) is a clean "<rooms> חדרים • <sqm> מ\"ר • קומה <floor>" bullet
   list — parsed by searching for each pattern independently (same defensive approach as
   yad2_client._parse_info_line_2), not by fixed segment position, so a missing/reordered field
   (e.g. a brokered listing with no floor) degrades to None instead of silently misreading a
   neighboring field — the exact bug class the OLD table's fixed-column-position parsing had to
   work around for "Tivuch" (brokered) rows (see git history). The <h3>'s FIRST line (before the
   divider) sometimes carries a real neighborhood after a "•" separator — optional, None when
   absent (confirmed live: present for one real sale card, absent for one real rent card).

Only ever seen "R promotedAd"/"R" style classes on the <a> tag and a "promotedAdLabel" div on
promoted cards specifically — the href/title extraction below doesn't require either class, so a
genuinely non-promoted (regular) card should parse identically once one is actually seen live
(not yet confirmed distinctly — every real card fetched so far, on both /rent/ and /sale/, happened
to be a promoted one, likely because promoted listings are shown first on the page).

DESCRIPTION (added 2026-09-13, unchanged by tonight's redesign): each listing's own detail page
(/rent/viewad,<id>.aspx or /sale/viewad,<id>.aspx) carries a real, free-text Hebrew ad description
in its <meta name="Description">/<meta property="og:description"> tags. fetch_listing_description
below fetches that one extra page, still on the plain (untested-for-redesign) tier — see point 1
above. scraper/main.py's _scrape_homeless calls it ONLY for genuinely new listings (never for one
already known — same "enrich once, cache forever" policy as komo_client.fetch_listing_detail and
Yad2's Bright Data enrichment).

OUTBOUND LINK: each card's own <a href> is used directly, never reconstructed from the id — a
brokered ("Tivuch") listing has historically used a different path prefix than a plain one
(/RentTivuch/ vs. /rent/, found live 2026-09-13), and the href-matching regex below accepts any
real "/<whatever>/viewad,<id>.aspx" path rather than assuming a fixed prefix, same discipline.

NOT yet confirmed: whether /rent/ or /sale/ paginate for more listings beyond what one fetch
returns (Komo turned out to have ~175 pages behind its own single-page HTML view, Yad2 too —
Homeless has not been checked for the same real "how many total listings does this site actually
have vs. how many one fetch returns" question yet, before OR after tonight's redesign).

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
SALE_SEARCH_PAGE_URL = "https://www.homeless.co.il/sale/"
_DETAIL_PAGE_BASE = "https://www.homeless.co.il"

ZENROWS_API_KEY_ENV_VAR = "ZENROWS_API_KEY"
ZENROWS_FETCH_API_URL = "https://api.zenrows.com/v1/"

# 2026-09-24: js_render's own real round-trip is noticeably slower than the old plain tier's —
# widened from the original plain-tier value (60s) to give real headroom.
PAGE_LOAD_TIMEOUT_S = 90

# Same shape/reasoning as yad2_client._ZENROWS_ERROR_CODE_RE/_ZENROWS_ERROR_TITLE_RE and
# komo_client's own copy — ZenRows' own JSON error body, not wrapped in any HTML shell. Duplicated
# here rather than imported/shared, matching this project's established file-per-source
# independence convention (see yad2_client.py's own module docstring).
_ZENROWS_ERROR_CODE_RE = re.compile(r'"code":"(?P<code>[A-Z0-9]+)"')
_ZENROWS_ERROR_TITLE_RE = re.compile(r'"title":"(?P<title>[^"]*)"')

# One real card's own outer div, id through the next card's own opening div (or end of document) —
# confirmed live against several real cards on both /rent/ and /sale/ (see module docstring). Divs
# nest inside a card, so a real "matching close tag" isn't reliably matchable by plain regex; the
# lookahead for the NEXT card's own opening div (or \Z) is what actually bounds each card, same
# "can't balance tags, bound by the next sibling instead" approach this project hasn't needed
# before now (every other source's own repeating unit was either a <tr> or already delimited by a
# fixed count of <td> siblings).
_CARD_RE = re.compile(
    r'<div id="ad_(?P<id>\d+)" class="[^"]*">(?P<body>.*?)(?=<div id="ad_\d+" class="|\Z)',
    re.S,
)

# The card's own real details-page link + its title attribute — confirmed live to always carry a
# clean "<type>, <rooms> חדרים, <street>, <city>" string (see module docstring). Href/title order
# in the tag isn't assumed fixed (real HTML attribute order isn't guaranteed) — this only requires
# both attributes to be present somewhere on the same <a ...> opening tag, not adjacent or ordered.
# href accepts ANY real "/<prefix>/viewad,<id>.aspx" path, never a fixed "/rent/" or "/sale/" prefix
# assumption — a brokered ("Tivuch") listing has historically used a different real prefix.
_CARD_LINK_RE = re.compile(
    r'<a[^>]*\bhref="(?P<href>/[^"]*?viewad,\d+\.aspx)"(?=[^>]*\btitle=)[^>]*\btitle="(?P<title>[^"]*)"',
    re.S,
)
# Same fallback the other direction (title before href in the tag) — a real <a> tag's own attribute
# order isn't guaranteed, so this covers the reverse ordering without one huge alternation regex.
_CARD_LINK_RE_REVERSED = re.compile(
    r'<a[^>]*\btitle="(?P<title>[^"]*)"(?=[^>]*\bhref=)[^>]*\bhref="(?P<href>/[^"]*?viewad,\d+\.aspx)"',
    re.S,
)

# The card's own first real photo — `[^"]*` (not `[^<]*`) since a src URL can't contain `<` but the
# group must stop at the closing quote, not at some later `<`.
_CARD_IMG_RE = re.compile(r'<img[^>]*\bsrc="(?P<src>[^"]*)"', re.S)

# The card's own real price div — confirmed live: "<div class=\"price\">\s*N,NNN ₪\s*</div>".
_CARD_PRICE_RE = re.compile(r'<div class="price">\s*([\d,]+)\s*₪', re.S)

# The card's own free-text <h3 class="desc" ...> body — confirmed live to carry two real lines
# separated by a <div class="custom-divider"></div>: line 1 is "<type> <deal> ב<area>[ • <neighborhood>]",
# line 2 is "<rooms> חדרים • <sqm> מ\"ר • קומה <floor>" (see module docstring). Parsed by searching
# each target pattern independently within its own line (never by fixed segment position) — same
# defensive approach as yad2_client._parse_info_line_2, so a missing/reordered field degrades to
# None instead of silently misreading a neighboring one.
_CARD_H3_RE = re.compile(r'<h3[^>]*>(?P<body>.*?)</h3>', re.S)
_CARD_DIVIDER_RE = re.compile(r'<div class="custom-divider"[^>]*></div>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")

_ROOMS_IN_LINE_RE = re.compile(r"([\d.]+)\s*חדרים")
_SQM_IN_LINE_RE = re.compile(r'([\d.]+)\s*מ["״]?ר')  # מ"ר — tolerate a straight or Hebrew gershayim quote
_FLOOR_IN_LINE_RE = re.compile(r"קומה\s*([^\s•]+)")
# The optional neighborhood, if any, after a "•" on the h3's FIRST line (before the divider) —
# confirmed live present for one real sale card ("...בפתח תקווה פז • פסגת הדר נווה עוז") and absent
# for one real rent card (nothing after its own trailing "•") — genuinely optional, not a miss.
_NEIGHBORHOOD_AFTER_BULLET_RE = re.compile(r"•\s*(.+)$", re.S)

# Confirmed live 2026-09-13 (diagnose-komo-gallery-and-homeless-description.yaml) against a real
# listing's own detail page (id=746758) — a real free-text Hebrew ad description, byte-identical
# in both tags (og:description tried second only as a defensive fallback, not because it's ever
# been seen to differ here). Unaffected by tonight's search-page redesign (a different page).
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
    Yad2's Radware wall) — every failure seen has been a plain HTTP/ZenRows-side problem (most
    recently, RESP001 on a plain fetch of the search page — see module docstring — now worked
    around with js_render=true, not a wall this project needs to defeat itself)."""


def _clean(text: str) -> str:
    return html.unescape(text.replace("&nbsp;", " ")).strip()


def _strip_tags(raw: str) -> str:
    return _clean(_TAG_RE.sub("", raw))


def _parse_price(raw: str) -> int | None:
    digits = re.sub(r"[^0-9]", "", raw)
    return int(digits) if digits else None


def _parse_rooms_sqm_floor(line2_raw: str) -> tuple[float | None, int | None, int | None]:
    text = _strip_tags(line2_raw)
    rooms = sqm = floor = None
    if m := _ROOMS_IN_LINE_RE.search(text):
        try:
            rooms = float(m.group(1))
        except ValueError:
            rooms = None
    if m := _SQM_IN_LINE_RE.search(text):
        try:
            sqm = int(float(m.group(1)))
        except ValueError:
            sqm = None
    if m := _FLOOR_IN_LINE_RE.search(text):
        value = m.group(1)
        # Same "ground floor" convention as yad2_client._parse_info_line_2 — not yet confirmed
        # live that Homeless itself ever uses קרקע here, but costs nothing to handle the same way.
        floor = 0 if "קרקע" in value else (int(value) if value.isdigit() else None)
    return rooms, sqm, floor


def _parse_city_street(title_attr: str) -> tuple[str | None, str | None]:
    """The card's own <a title="..."> attribute — confirmed live as a clean "<type>, <rooms>
    חדרים, <street>, <city>" comma-separated string across every real card seen. city is always
    the last segment, street the one before it — same "last segment is the city" convention as
    yad2_client._parse_location, just without that function's own multi-part-neighborhood-joining
    (not needed here: title only ever carries exactly 4 segments in every real sample seen)."""
    parts = [p.strip() for p in _clean(title_attr).split(",") if p.strip()]
    if len(parts) < 2:
        return None, None
    city = parts[-1]
    street = parts[-2] if len(parts) >= 4 else None
    return city, street


def _parse_neighborhood(line1_raw: str) -> str | None:
    text = _strip_tags(line1_raw)
    m = _NEIGHBORHOOD_AFTER_BULLET_RE.search(text)
    if m is None:
        return None
    neighborhood = m.group(1).strip()
    return neighborhood or None


def _get_zenrows_api_key() -> str:
    api_key = os.environ.get(ZENROWS_API_KEY_ENV_VAR, "").strip()
    if not api_key:
        raise HomelessFetchError(
            f"{ZENROWS_API_KEY_ENV_VAR} is not set — see PROJECT_STATE.md. This is the same "
            "ZenRows account/key yad2_client.py and komo_client.py use."
        )
    return api_key


def _zenrows_get(url: str, *, context_label: str, js_render: bool = False) -> str:
    """Shared fetch-through-ZenRows mechanics. js_render=True is required for the search page
    since the 2026-09-24 redesign (see module docstring, point 1) — real, meaningfully higher cost
    (5 credits vs. 1), so callers that don't need it (the per-listing detail page, still untested
    against this same redesign) default to the cheaper plain tier."""
    api_key = _get_zenrows_api_key()

    params = {"apikey": api_key, "url": url}
    if js_render:
        params["js_render"] = "true"

    try:
        response = httpx.get(ZENROWS_FETCH_API_URL, params=params, timeout=PAGE_LOAD_TIMEOUT_S)
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


def _fetch_search_html(url: str) -> str:
    return _zenrows_get(url, context_label=f"Homeless search page url={url!r}", js_render=True)


def _parse_cards(search_html: str) -> Iterator[dict[str, Any]]:
    for card_match in _CARD_RE.finditer(search_html):
        external_id = card_match.group("id")
        body = card_match.group("body")

        link_match = _CARD_LINK_RE.search(body) or _CARD_LINK_RE_REVERSED.search(body)
        if link_match is None:
            logger.warning(
                "Skipping Homeless card id=%s: no real details-page link/title found in its own "
                "markup (%r) — the card's own <a> markup may have changed again.",
                external_id, body[:300],
            )
            continue
        detail_url = urljoin(_DETAIL_PAGE_BASE, html.unescape(link_match.group("href")).strip())
        city, street = _parse_city_street(link_match.group("title"))

        image_match = _CARD_IMG_RE.search(body)
        image_url = html.unescape(image_match.group("src")).strip() if image_match else ""

        price_match = _CARD_PRICE_RE.search(body)
        price = _parse_price(price_match.group(1)) if price_match else None

        rooms = sqm = floor = None
        neighborhood = None
        h3_match = _CARD_H3_RE.search(body)
        if h3_match is not None:
            h3_body = h3_match.group("body")
            divider_parts = _CARD_DIVIDER_RE.split(h3_body, maxsplit=1)
            line1 = divider_parts[0]
            line2 = divider_parts[1] if len(divider_parts) > 1 else ""
            neighborhood = _parse_neighborhood(line1)
            rooms, sqm, floor = _parse_rooms_sqm_floor(line2)

        yield {
            "id": external_id,
            "url": detail_url,
            "price": price,
            "rooms": rooms,
            "floor": floor,
            "square_meters": sqm,
            "street": street,
            "neighborhood": neighborhood,
            "city": city,
            "images": [image_url] if image_url else [],
        }


def fetch_search_results(url: str = SEARCH_PAGE_URL) -> Iterator[dict[str, Any]]:
    """Yields raw listing dicts (normalize()-ready, same flat shape as yad2_client._parse_cards)
    for every real listing card found on ONE js_render=true fetch of `url` (SEARCH_PAGE_URL for
    rent, SALE_SEARCH_PAGE_URL for sale — same URL-per-call pattern facebook_client.py's own
    fetch_search_results uses for its rent/forsale categories) — confirmed live at 5 ZenRows
    credits (see module docstring for the real cost/redesign story). See module docstring for the
    real, still-open question of whether this single fetch already covers every current listing or
    whether the site paginates beyond it."""
    search_html = _fetch_search_html(url)
    yield from _parse_cards(search_html)


def fetch_listing_description(url: str) -> str | None:
    """Fetches ONE listing's own detail page (its real url, as returned by fetch_search_results)
    and returns its real free-text description, or None on ANY failure (missing API key, network
    error, non-200, no description found) — never raises, same defensive contract as
    komo_client.fetch_listing_detail. This is genuinely OPTIONAL enrichment, unlike Komo's price
    (see that module's own cost note): Homeless's search-results card already has everything else
    this project needs, so a failed description fetch simply means a listing without a
    description, exactly as before this feature existed. Still on the plain (cheaper) ZenRows
    tier — not yet confirmed whether the detail page also needs js_render after the 2026-09-24
    search-page redesign (see module docstring, point 1); revisit if evidence emerges it does."""
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
