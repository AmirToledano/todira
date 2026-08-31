"""ONE-OFF diagnostic (2026-08-31) — NOT part of the production scraper flow, not imported by
main.py. Delete this file once the multi-city question below is answered; see PROJECT_STATE.md.

Question: does Yad2's search URL accept multiple city IDs in a single request (e.g.
`?city=5000,6300` or repeated `?city=5000&city=6300`), returning listings for all of them at
once? If so, `scraper/main.py`'s per-city rotation (added 2026-08-31 to fit ZenRows' free-tier
credit budget — see PROJECT_STATE.md) could cover far more cities per ZenRows request, cutting
the effective cost-per-city dramatically instead of trading off scan frequency.

Also tests a second, unrelated question raised the same night: ZenRows' own AI support chat
claimed yad2.co.il is on Extract's curated-domain list and `extract=auto` costs the same as a
plain Fetch call — plausible, but a 5-second AI chat answer isn't verified fact, especially a
specific per-domain claim like that. Rather than trust it, TEST C below calls it directly.

Runs 4 real ZenRows requests (~25 credits each via the proxy for A/B/control, real but unknown
cost for the Extract test — trivial against any paid tier's monthly budget either way, but real
money, hence not run automatically/repeatedly):
  1. Control: ramat-gan alone (a known-good single city per YAD2_NOTES.md's "Attempt 9: SOLVED"
     writeup) — confirms the pipeline + _CARD_RE still parses real cards at all before trusting
     the other two results. This has NOT been independently re-confirmed since 2026-08-29; every
     run since has actually been hitting ZenRows' AUTH004 error page, not real Yad2 HTML (see
     PROJECT_STATE.md's "found why there had NEVER been a single real listing").
  2. Comma-separated: `city=5000,6300` (tel-aviv, givatayim)
  3. Repeated param: `city=5000&city=6300` (tel-aviv, givatayim)
  4. Extract test: calls ZenRows' actual Fetch REST API (api.zenrows.com — NOT the proxy gateway
     the other three tests and production yad2_client.py use) with `extract=auto` on a single
     city, and reports exactly what comes back: structured JSON (support bot's claim holds),
     a 402 AUTH010 (domain not actually enabled — support bot was wrong), or something else.

For (2) and (3), checks whether the returned cards include listings whose `city` field is
tel-aviv AND givatayim (real multi-city support) vs. only one of them (Yad2 ignored/rejected the
extra value and silently fell back to a single city).

Usage: `python -u _diagnose_multi_city.py` with ZENROWS_API_KEY set in the environment. Meant to
be run once, via a temporary CI step or `docker run` against the built scraper image — see the
temporary "Diagnose multi-city Yad2 query support" step in ci-cd.yaml.
"""
from __future__ import annotations

import logging
import os
import sys

import httpx
from patchright.sync_api import TimeoutError as PlaywrightTimeoutError
from patchright.sync_api import sync_playwright

from yad2_client import (
    PAGE_LOAD_TIMEOUT_MS,
    POST_LOAD_WAIT_MS,
    SEARCH_PAGE_URL,
    ZENROWS_API_KEY_ENV_VAR,
    ZENROWS_PROXY_PARAMS,
    ZENROWS_PROXY_SERVER,
    _parse_cards,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("diagnose_multi_city")

ZENROWS_FETCH_API_URL = "https://api.zenrows.com/v1/"

TEL_AVIV_ID = "5000"
GIVATAYIM_ID = "6300"
RAMAT_GAN_ID = "8600"


def _fetch(url: str, api_key: str) -> str:
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
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                logger.error("Page never loaded for url=%s", url)
                return ""
            page.wait_for_timeout(POST_LOAD_WAIT_MS)
            try:
                page.wait_for_load_state("networkidle", timeout=20_000)
            except PlaywrightTimeoutError:
                pass
            return page.content()
        finally:
            browser.close()


def _report(label: str, url: str, api_key: str) -> None:
    logger.info("--- %s ---\nurl=%s", label, url)
    html = _fetch(url, api_key)
    if not html:
        logger.warning("%s: no HTML returned (timeout)", label)
        return
    items = list(_parse_cards(html))
    cities = sorted({item["city"] for item in items if item.get("city")})
    logger.info(
        "%s: html_length=%d cards_parsed=%d distinct_cities_seen=%s",
        label,
        len(html),
        len(items),
        cities,
    )
    if len(items) == 0 and len(html) < 1000:
        logger.warning("%s: short response, possible ZenRows error page: %r", label, html[:500])


def _report_extract(city_id: str, api_key: str) -> None:
    url = f"{SEARCH_PAGE_URL}?city={city_id}"
    logger.info("--- TEST C: extract=auto via Fetch REST API ---\nurl=%s", url)
    try:
        response = httpx.get(
            ZENROWS_FETCH_API_URL,
            params={
                "apikey": api_key,
                "url": url,
                "js_render": "true",
                "premium_proxy": "true",
                "extract": "auto",
            },
            timeout=90.0,
        )
    except httpx.HTTPError as exc:
        logger.error("TEST C: request failed: %s", exc)
        return

    logger.info("TEST C: status_code=%d content_type=%s", response.status_code, response.headers.get("content-type"))
    if response.status_code != 200:
        logger.warning("TEST C: non-200 response body (first 1000 chars): %r", response.text[:1000])
        return
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        logger.info("TEST C: got JSON back — extract=auto worked. Body (first 2000 chars): %r", response.text[:2000])
    else:
        logger.warning(
            "TEST C: got %s, not JSON — extract=auto did NOT trigger (likely fell back to plain "
            "HTML). Body (first 500 chars): %r",
            content_type,
            response.text[:500],
        )


def main() -> None:
    api_key = os.environ.get(ZENROWS_API_KEY_ENV_VAR, "").strip()
    if not api_key:
        logger.error("%s not set", ZENROWS_API_KEY_ENV_VAR)
        sys.exit(1)

    _report("CONTROL: ramat-gan alone", f"{SEARCH_PAGE_URL}?city={RAMAT_GAN_ID}", api_key)
    _report(
        "TEST A: comma-separated city ids",
        f"{SEARCH_PAGE_URL}?city={TEL_AVIV_ID},{GIVATAYIM_ID}",
        api_key,
    )
    _report(
        "TEST B: repeated city param",
        f"{SEARCH_PAGE_URL}?city={TEL_AVIV_ID}&city={GIVATAYIM_ID}",
        api_key,
    )
    _report_extract(RAMAT_GAN_ID, api_key)
    logger.info(
        "Done. Compare distinct_cities_seen across TEST A/B against the control — if either shows "
        "BOTH תל אביב יפו and גבעתיים, multi-city queries work. For TEST C, check whether it "
        "returned real JSON or fell back to HTML/an error. Update PROJECT_STATE.md and "
        "scraper/main.py/yad2_client.py accordingly, then delete this script."
    )


if __name__ == "__main__":
    main()
