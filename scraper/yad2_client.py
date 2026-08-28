"""Fetches raw listing payloads from Yad2's rental search.

STATUS (see YAD2_NOTES.md for the full trail): the direct-JSON-API approach (a plain httpx GET
to a guessed `gw.yad2.co.il` endpoint) is CONFIRMED blocked as of 2026-08-27 — the request was
redirected to `validate.perfdrive.com/...&ssk=support@shieldsquare.com...`, which is a
PerimeterX/HUMAN Security bot-protection challenge page, not real data. That code path has been
removed rather than left as dead code; see YAD2_NOTES.md if you need to look at it again.

This now goes straight to the plan's Fallback B: a real browser (Playwright-family) navigates to
Yad2's human-facing search page, and captures the JSON response Yad2's own frontend fetches
internally afterwards — so we still end up with clean JSON, not HTML to scrape.

Attempt history (see YAD2_NOTES.md for the full trail and research sources):
1. Plain headless Playwright — hit a "Radware Page" bot-check (Radware Bot Manager) that never
   resolved, even after an extra 8s wait for a possible timer-redirect.
2. Plain headless Playwright + `playwright-stealth` (JS-injection evasions only) — same result.
   Expected in hindsight: that library's own docs say not to expect it to beat more than basic
   bot detection, since it never touches CDP-level automation signals.
3. Playwright + stealth in **headed** mode (via Xvfb) — same result, and slow/flaky to run.
4. Swapped the whole `playwright` package for **`patchright`** — a maintained fork that avoids
   the CDP `Runtime.enable`/`Console.enable` leak at the driver level, plus built-in WebGL
   fingerprint spoofing. **This measurably helped**: instead of the opaque "Radware Page" seen
   in attempts #1-3, we now reach an actual **"Radware Bot Manager Captcha"** page (hCaptcha) —
   i.e. patchright got past the silent/automatic fingerprint block onto the same interactive
   challenge a suspicious real user would see. A categorically different, further-along outcome.
5. Since an hCaptcha requires solving (not just fingerprint evasion), added manual cookie
   harvesting — a human solves the captcha once in a real browser, and its resulting session
   cookie is loaded into the automated browser's context (`YAD2_COOKIE_HEADER` env var) so it
   doesn't need to re-solve it. **Result: the cookie loaded successfully but still got
   re-challenged** — the page got noticeably further (many more real yad2/tracker hosts
   contacted) before hitting the same wall, consistent with Radware tying session validity to
   IP/TLS-fingerprint consistency between the browser that solved it and the one presenting the
   cookie, not just the cookie value alone. See YAD2_NOTES.md attempt #5 for full diagnostics.
6. **Current**: pay-per-solve captcha-solving via **2Captcha** — extracts the hCaptcha sitekey
   from the challenge page, sends it to 2Captcha's API (solved by their workers/service, not us),
   and injects the returned token back into the page. This solves a *different* problem than
   attempts #1-5 (an interactive puzzle, not fingerprint/session evasion), so it's not redundant
   with patchright — patchright is still what gets us to a solvable captcha in the first place
   instead of an opaque silent block.

STILL UNVERIFIED (see YAD2_NOTES.md):
- Whether `?city=<slug>` is even the right query param for the human-facing search page.
- Pagination — this fetches only what loads on the initial page (no scroll/page-2 handling yet).
Both are naturally the next things to nail down once this run's logs show whether ANY response
matching FEED_URL_MARKER gets captured at all.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Iterator
from urllib.parse import urlparse

from patchright.sync_api import TimeoutError as PlaywrightTimeoutError
from patchright.sync_api import sync_playwright
from twocaptcha import TwoCaptcha

logger = logging.getLogger(__name__)

SEARCH_PAGE_URL = "https://www.yad2.co.il/realestate/rent"
FEED_URL_MARKER = "realestate-feed"  # substring used to recognize the internal JSON call

# Manual cookie harvesting (see YAD2_NOTES.md): a human solves Yad2's hCaptcha once in a real
# browser, then copies the resulting `cookie:` request-header value (DevTools > Network > the
# main document request > Request Headers) into this env var verbatim — "name1=value1;
# name2=value2; ...". We load it into the automated browser's context so it presents an
# already-validated session instead of hitting the challenge again. Expected to need periodic
# manual refresh as the cookie/session expires — a documented tradeoff of the free-and-manual
# approach, not a bug.
COOKIE_HEADER_ENV_VAR = "YAD2_COOKIE_HEADER"
COOKIE_DOMAIN = ".yad2.co.il"


def _load_manual_cookies() -> list[dict[str, Any]]:
    raw = os.environ.get(COOKIE_HEADER_ENV_VAR, "").strip()
    if not raw:
        return []
    cookies = []
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        cookies.append(
            {"name": name.strip(), "value": value.strip(), "domain": COOKIE_DOMAIN, "path": "/"}
        )
    return cookies

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
PAGE_LOAD_TIMEOUT_MS = 30_000

# 2026-08-27 finding (see YAD2_NOTES.md): Yad2 serves a "Radware Page" bot-management challenge
# — a lightweight page (only Google Fonts + yad2.co.il itself in its network log) that most
# likely runs a JS timer before redirecting to the real content. `networkidle` fires before that
# timer does, so we were giving up too early. CHALLENGE_TITLE_MARKER detects it; the extra wait
# below gives the redirect time to actually happen.
CHALLENGE_TITLE_MARKER = "radware"
CHALLENGE_WAIT_MS = 8_000

TWOCAPTCHA_API_KEY_ENV_VAR = "TWOCAPTCHA_API_KEY"
SOLVE_TIMEOUT_SECONDS = 180  # bumped from TwoCaptcha's own 120s default — real-world solves for
# this exact sitekey ranged from ~21s to a 120s timeout in testing; give it more room.


class Yad2FetchError(RuntimeError):
    """Playwright never saw the expected internal JSON response — most likely because
    PerimeterX's challenge wasn't passed, or the frontend's request shape changed since."""


def _find_hcaptcha_widget(page) -> dict[str, Any] | None:
    """Best-effort, standard-hCaptcha-embed extraction (a `[data-sitekey]` element, or a
    hcaptcha.com iframe with `sitekey=` in its src). Returns the sitekey, the `data-callback`
    name found on the SAME element (not a separate query — a page can have other unrelated
    `[data-callback]` elements), and a truncated snapshot of the markup for diagnostics, logged
    here so a failed run tells us Yad2's actual widget shape without needing manual DevTools
    inspection again."""
    info = page.evaluate(
        """() => {
            const el = document.querySelector('[data-sitekey]');
            if (el) {
                return {
                    sitekey: el.getAttribute('data-sitekey'),
                    callback: el.getAttribute('data-callback'),
                    markup: el.outerHTML.slice(0, 500),
                };
            }
            const iframe = document.querySelector('iframe[src*="hcaptcha.com"]');
            if (iframe) {
                const src = iframe.getAttribute('src') || '';
                const match = src.match(/[?&#]sitekey=([^&]+)/);
                if (match) {
                    return {
                        sitekey: decodeURIComponent(match[1]),
                        callback: null,
                        markup: iframe.outerHTML.slice(0, 500),
                    };
                }
            }
            return null;
        }"""
    )
    if info:
        logger.info(
            "hCaptcha widget found: callback=%r, markup=%s", info.get("callback"), info.get("markup")
        )
    return info


def _solve_hcaptcha(page, city: str) -> bool:
    """Returns True if a token was found and injected (not a guarantee the site accepted it —
    caller still re-checks for the real feed response afterward)."""
    api_key = os.environ.get(TWOCAPTCHA_API_KEY_ENV_VAR, "").strip()
    if not api_key:
        logger.info(
            "%s not set — skipping captcha solve for city=%s", TWOCAPTCHA_API_KEY_ENV_VAR, city
        )
        return False

    widget = _find_hcaptcha_widget(page)
    if not widget or not widget.get("sitekey"):
        logger.warning("Could not find an hCaptcha sitekey on the challenge page for city=%s", city)
        return False

    sitekey = widget["sitekey"]
    callback_name = widget.get("callback")
    logger.info(
        "Solving hCaptcha via 2Captcha for city=%s (sitekey=%s, callback=%r) — up to %ss",
        city,
        sitekey,
        callback_name,
        SOLVE_TIMEOUT_SECONDS,
    )
    try:
        result = TwoCaptcha(api_key, defaultTimeout=SOLVE_TIMEOUT_SECONDS).hcaptcha(
            sitekey=sitekey, url=page.url
        )
    except Exception:
        logger.exception("2Captcha failed to solve the hCaptcha for city=%s", city)
        return False

    token = result["code"]
    # standard hCaptcha integration: fill any h-captcha-response/g-recaptcha-response field(s),
    # fire input/change events in case any listener depends on them (not just a form submit),
    # and call the widget's own data-callback if it has one — setting the field alone is often
    # not enough to make the page's own JS notice the challenge passed.
    callback_fired = page.evaluate(
        """({token, callbackName}) => {
            for (const name of ["h-captcha-response", "g-recaptcha-response"]) {
                document.querySelectorAll(`[name="${name}"]`).forEach((el) => {
                    el.value = token;
                    el.innerHTML = token;
                    el.dispatchEvent(new Event("input", {bubbles: true}));
                    el.dispatchEvent(new Event("change", {bubbles: true}));
                });
            }
            if (callbackName && typeof window[callbackName] === "function") {
                window[callbackName](token);
                return true;
            }
            return false;
        }""",
        {"token": token, "callbackName": callback_name},
    )
    logger.info(
        "Injected hCaptcha token for city=%s (site callback triggered: %s)", city, callback_fired
    )
    return True


def fetch_search_results(city: str) -> Iterator[dict[str, Any]]:
    """Yields raw listing dicts (Yad2's own JSON shape, unmodified) for one city."""
    captured_payloads: list[dict[str, Any]] = []
    seen_response_urls: list[str] = []
    hosts_seen: set[str] = set()

    with sync_playwright() as p:
        # --no-sandbox: needed because this container runs as root, where Chromium's sandbox
        # refuses to start. headless=True — patchright's own CDP-level patches are what's being
        # tested here, not headed-mode; see the module docstring for why Xvfb was dropped.
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            context = browser.new_context(user_agent=DEFAULT_USER_AGENT, locale="he-IL")

            manual_cookies = _load_manual_cookies()
            if manual_cookies:
                context.add_cookies(manual_cookies)
                logger.info(
                    "Loaded %d manually-harvested cookie(s) from %s",
                    len(manual_cookies),
                    COOKIE_HEADER_ENV_VAR,
                )
            else:
                logger.info(
                    "No manual cookies set (%s is empty) — relying on patchright alone",
                    COOKIE_HEADER_ENV_VAR,
                )

            page = context.new_page()

            def _on_response(response) -> None:
                hosts_seen.add(urlparse(response.url).netloc)
                if FEED_URL_MARKER not in response.url:
                    return
                seen_response_urls.append(response.url)
                if not response.ok:
                    return
                try:
                    captured_payloads.append(response.json())
                    logger.info("Captured Yad2 feed response from %s", response.url)
                except Exception:
                    logger.debug("Response matched feed marker but wasn't JSON: %s", response.url)

            page.on("response", _on_response)
            url = f"{SEARCH_PAGE_URL}?city={city}"
            page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)

            title = (page.title() or "").lower()
            if CHALLENGE_TITLE_MARKER in title:
                # 2026-08-28 finding: checking the title THIS early (right after
                # domcontentloaded) is itself unreliable — on one run tel-aviv's title hadn't
                # updated to "...Captcha" yet at this exact point even though it clearly had by
                # the time of the final diagnostics. Don't gate the solve attempt on this title
                # string at all; _solve_hcaptcha's own sitekey lookup is the real, live check —
                # it just returns False harmlessly if there's nothing to solve.
                solved = _solve_hcaptcha(page, city)
                if not solved:
                    logger.info(
                        "Hit a bot-check page for city=%s — waiting %sms (no captcha solved "
                        "this run)",
                        city,
                        CHALLENGE_WAIT_MS,
                    )
                # either way, give the page's own JS time to react (verify with its backend,
                # reload/redirect, etc.) before we check what came through
                page.wait_for_timeout(CHALLENGE_WAIT_MS)

            try:
                page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                # best-effort — fall through and check what we actually captured regardless
                logger.debug("networkidle wait timed out for city=%s, proceeding anyway", city)

            final_url = page.url
            page_title = page.title()
        finally:
            browser.close()

    if not captured_payloads:
        seen_note = (
            f" Saw {len(seen_response_urls)} response(s) matching {FEED_URL_MARKER!r} but none "
            f"were usable JSON: {seen_response_urls}"
            if seen_response_urls
            else f" No response matched {FEED_URL_MARKER!r} at all — the frontend's internal "
            "API call may have a different URL shape now, or the challenge wasn't passed."
        )
        raise Yad2FetchError(
            f"Playwright loaded the Yad2 search page for city={city!r} but never captured a "
            f"usable feed response.{seen_note}\n"
            f"Diagnostics — final URL: {final_url!r}, page title: {page_title!r}, "
            f"hosts contacted: {sorted(hosts_seen)}.\n"
            "Update FEED_URL_MARKER / this function per YAD2_NOTES.md."
        )

    for payload in captured_payloads:
        items = payload.get("items") or payload.get("data") or []  # UNVERIFIED key name
        yield from items
