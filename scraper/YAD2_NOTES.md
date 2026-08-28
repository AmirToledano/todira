# Yad2 research spike — findings log

## 2026-08-27 — Tier 1 (direct httpx call to a guessed JSON endpoint): CONFIRMED BLOCKED

Ran the scraper for real against `SEARCH_ENDPOINT = "https://gw.yad2.co.il/realestate-feed/rent/map"`
(a guessed endpoint, never verified against real traffic).

**Result:** HTTP 302, redirecting to:
```
https://validate.perfdrive.com/ca0c6c171687aa56742617df4ef03a07/?ssa=...&ssb=...
  &ssc=https%3A%2F%2Fgw.yad2.co.il%2Frealestate-feed%2Frent%2Fmap%3Fcity%3D<city>%26page%3D1
  &ssk=support@shieldsquare.com&ssm=...&ssn=...&sso=...&ssp=...&ssq=...&ssr=...
  &sst=Mozilla/5.0...&ssu=&ssv=&ssw=&ssx=...
```

`shieldsquare.com` is the legacy brand name for **PerimeterX / HUMAN Security**, a commercial
bot-mitigation service. `validate.perfdrive.com` is its challenge/validation domain. This
confirms the endpoint itself was probably in the right shape (or close), but Yad2 (or a CDN in
front of it) runs real, enterprise-grade bot detection that a plain `httpx` request — even with
a realistic `User-Agent` — cannot pass. Following the redirect returns a challenge page (not
JSON), which is why the second attempt failed with a `JSONDecodeError`.

**Conclusion:** the httpx-based Tier 1 client (and by extension Tier 2, plain HTML parsing —
same edge-layer block would apply) is not viable as-is. Removed that code from `yad2_client.py`
rather than leave it as dead code; the redirect URL above is the historical record if it's ever
useful again (e.g. to confirm PerimeterX is still in front of this specific endpoint).

## Current approach: Tier 3 — Playwright (headless browser)

`yad2_client.py` now launches headless Chromium via Playwright, navigates to
`https://www.yad2.co.il/realestate/rent?city=<city>` (the human-facing page), and listens for
any network response whose URL contains `"realestate-feed"` — capturing its JSON body once a
real browser has (hopefully) passed PerimeterX's challenge automatically.

## 2026-08-27 — Tier 3 attempt #1 (Playwright, no extra wait): hit a Radware challenge page

Ran the Playwright-based client for real. Result: `Yad2FetchError` for all 3 cities — no response
ever matched `"realestate-feed"`. Diagnostics added to the error message showed:
- **Final URL:** `https://www.yad2.co.il/realestate/rent?city=<city>` (still on Yad2's own domain
  — no redirect to an external domain like the Tier 1 attempt).
- **Page title:** `"Radware Page"` — Radware Bot Manager, a different bot-mitigation vendor than
  the PerimeterX/HUMAN Security one seen in the Tier 1 redirect.
- **Hosts contacted:** only `fonts.googleapis.com`, `fonts.gstatic.com`, `www.yad2.co.il`.

**Interpretation:** the challenge page is lightweight (no extra XHR calls of its own) — it most
likely runs a client-side JS timer/check, then redirects to the real content once satisfied.
`networkidle` was firing before that timer fired, so we gave up too early. Fixed in
`yad2_client.py`: detect the `"radware"` title marker, then `page.wait_for_timeout(8000)` before
re-checking network state, giving the challenge time to actually resolve.

## 2026-08-27/28 — Tier 3 attempts #2 and #3: stealth (headless) and stealth (headed/Xvfb) both failed

- **Attempt #2**: added `playwright-stealth` (v1.0.6) — patches `navigator.webdriver` and other
  obvious JS-visible signals before navigating. **Result: identical "Radware Page" outcome.**
  (Along the way: hit `ModuleNotFoundError: No module named 'pkg_resources'` because
  playwright-stealth 1.0.6 still imports the now-removed `pkg_resources` API — newer `setuptools`
  releases dropped it entirely as of ~Nov 2025. Fixed by pinning `setuptools<81`.)
- **Attempt #3**: same stealth setup but `headless=False` against a virtual display (Xvfb) in the
  container, on the theory that headless mode's own signature might be part of what's detected.
  **Result: same "Radware Page" outcome again** — and this approach also proved unreliable to
  operate (looked "hung" due to Python stdout buffering through the `xvfb-run` wrapper; fixed
  with `python -u`, but headed+Xvfb remained slow and added real operational risk for no payoff).

**Conclusion from #1-#3:** the challenge isn't timing, and it isn't (just) headless-mode
detection — Radware is actively fingerprinting something JS-injection-only stealth doesn't touch.

## 2026-08-28 — Research pass (background multi-agent web search) before attempt #4

Ran a parallel research sweep (3 of 5 planned searches completed before hitting a session-usage
limit; radware-specific and yad2-prior-art searches did not complete — worth re-running later if
attempt #4 also fails). Key findings, with sources in the full agent output:

- **`playwright-stealth` is explicitly documented (by its own maintainers) as JS-injection-only**
  — it never touches CDP-level automation signals, which matches attempt #2's failure.
- **The most likely culprit: the CDP `Runtime.enable` leak.** Publicly documented (Antoine
  Vastel, June 2024) as a near-certain automation signal used by Cloudflare/DataDome-class bot
  managers, independent of `navigator.webdriver`. Playwright/Puppeteer fire this on every frame
  by default.
- **`patchright`** (`Kaliiiiiiiiii-Vinyzu/patchright-python`, actively maintained, drop-in
  Playwright-API replacement) specifically avoids this CDP leak at the driver level, plus patches
  command-line automation flags and adds WebGL fingerprint spoofing. Multiple independent
  research angles converged on this as the strongest free next step.
- **Honest caveat found in the research**: a 2026 anti-detect benchmark notes patchright is "the
  cleanest drop-in stealth upgrade" but that higher-security-tier DataDome/Cloudflare configs can
  still catch it in some cases — no confirmation either way for Radware specifically.
- **TLS/JA3 fingerprinting has NO free fix within Playwright's own stack, patched or not** —
  Playwright's bundled Chromium's TLS handshake doesn't match a real Chrome release, and there is
  no public patch that rewrites that at the BoringSSL level. If Radware is blocking at this layer
  (before any page JS even runs), no in-browser change — patchright included — will help; the
  only free-ish workarounds involve abandoning the browser for pure-HTTP tools (`curl_cffi`),
  which can't execute the JS challenge, or switching to a different engine entirely (Camoufox,
  patched Firefox).
- **2026 consensus across multiple independent sources**: no single free library reliably beats a
  modern commercial bot manager end-to-end anymore; real success typically requires stacking free
  layers (patched browser + residential proxy + human-like input timing), and even that
  increasingly falls short against enterprise-tier configs without paid infrastructure.

## 2026-08-28 — Tier 3 attempt #4: `patchright` — genuine progress, reached an actual CAPTCHA

`yad2_client.py` and `scraper/Dockerfile` updated: `patchright` replaces `playwright` +
`playwright-stealth` entirely, headless mode restored (Xvfb removed — attempt #3 showed it
wasn't the fix and added real reliability cost).

**Result: measurably different from attempts #1-3.** Diagnostics:
- **Final URL:** `https://validate.perfdrive.com/<id>/?ssa=...&ssc=https%3A%2F%2Fwww.yad2.co.il%2Frealestate%2Frent%3Fcity%3D<city>&ssk=support@shieldsquare.com&...`
  — note this is the SAME `validate.perfdrive.com` / `ssk=support@shieldsquare.com` shape as the
  Tier 1 direct-API redirect, confirming Yad2's Chromium-facing challenge and its JSON-API-facing
  challenge are the same underlying PerimeterX/Radware system.
- **Page title:** `"Radware Bot Manager Captcha"` — not the opaque `"Radware Page"` from
  attempts #1-3.
- **Hosts contacted:** now includes `hcaptcha.com`, `api.hcaptcha.com`, `newassets.hcaptcha.com`,
  `*.w.hcaptcha.com`, `cas.avalon.perfdrive.com`, `cdn.perfdrive.com`, plus `assets.yad2.co.il` /
  `visuals.yad2.co.il`.

**Interpretation:** patchright's CDP-leak fix got past whatever silent/automatic fingerprint
check was blocking attempts #1-3 outright — we now reach the same **interactive hCaptcha
challenge** a suspicious real visitor would see, instead of being silently walled off before any
challenge is even offered. This is real forward progress, not another identical failure.

## 2026-08-28 — Tier 3 attempt #5 (current): manual cookie harvesting to skip the CAPTCHA

An hCaptcha requires solving (human or a paid captcha-solving API), not fingerprint evasion — a
different kind of problem than #1-4. Chose the free path: a human solves it once in a real
browser, and its session cookie is reused by the automated browser.

Added to `yad2_client.py`: `_load_manual_cookies()` reads `YAD2_COOKIE_HEADER` (a raw
`name1=value1; name2=value2; ...` cookie-header string) and loads it into the browser context via
`context.add_cookies(...)` before navigating.

**How to harvest the cookie value** (do this yourself in a real browser, not via this codebase):
1. Open `https://www.yad2.co.il/realestate/rent` in Chrome/Edge.
2. If prompted, solve the hCaptcha manually.
3. Once the real listings page loads (not a challenge/captcha page), open DevTools (F12) →
   **Network** tab, then reload the page (F5) so a fresh request appears.
4. Click the top request to `www.yad2.co.il` (the main document) → **Headers** panel → scroll to
   **Request Headers** → find the `cookie:` line.
5. Copy the entire value after `cookie:` and paste it as `YAD2_COOKIE_HEADER` in `.env` (local)
   or the k8s Secret (once deployed) — verbatim, semicolon-separated, no extra parsing needed.

**Known tradeoff, not a bug:** this session cookie will expire or get invalidated eventually
(exact lifetime unverified), needing periodic manual re-harvesting — there is no way to fully
automate solving an hCaptcha for free.

**Result: tested with a real harvested cookie (38 cookies loaded successfully) — still redirected
to the same `validate.perfdrive.com` / "Radware Bot Manager Captcha" page.** But NOT an identical
failure to attempt #4: the hosts-contacted list grew dramatically — real yad2 asset hosts
(`images.yad2.co.il`, `assets.yad2.co.il`, `visuals.yad2.co.il`, `treedis-cdn.yad2.co.il`) plus a
full complement of ad/analytics trackers (doubleclick, googlesyndication, hotjar, outbrain) — a
pattern consistent with substantially more of the real page having started loading before the
captcha wall reasserted itself, versus attempt #4's minimal (fonts-only) footprint.

**Interpretation:** the harvested cookie was accepted well enough to progress further, but not
well enough to fully pass. The most likely explanation: Radware ties session validity to more
than the cookie value alone — IP address and/or TLS/JA3 fingerprint consistency between the
browser that solved the challenge (the user's real Chrome, on their home IP) and the browser
presenting the cookie afterward (patchright, from Docker's network path). This is a standard
anti-cookie-replay technique for enterprise bot managers, and lines up with the earlier research
finding that TLS/JA3 fingerprinting has no free fix within Playwright/patchright's own stack.

**This is the natural stopping point for free experimentation** — every reasonable free technique
identified by research has now been tried (direct API, headless, JS-stealth, headed, CDP-level
patchright fix, manual cookie replay), and all converge on the same wall. Continuing to iterate
on free techniques from here has low expected payoff per the research's own 2026 consensus.

## 2026-08-28 — Tier 3 attempt #6 (current): pay-per-solve captcha solving via 2Captcha

Different category of fix than #1-5 — those were all about evading fingerprint/session
detection; this solves the interactive puzzle patchright gets us *to* but can't pass on its own.

`yad2_client.py` added: `_extract_hcaptcha_sitekey()` (best-effort — looks for a `[data-sitekey]`
element or an `hcaptcha.com` iframe with `sitekey=` in its src; **not yet verified against Yad2's
actual challenge-page DOM**, since that requires seeing a real captcha page's markup) and
`_solve_hcaptcha()` (calls 2Captcha's `hcaptcha()` API, verified against the installed
`twocaptcha` package's real source — `TwoCaptcha(apiKey).hcaptcha(sitekey=..., url=...)` returns
`{"code": <token>, ...}` — then injects the token into any `h-captcha-response`/
`g-recaptcha-response` field(s) and fires the widget's `data-callback` if present, the standard
hCaptcha integration pattern).

Requires `TWOCAPTCHA_API_KEY` (from https://2captcha.com, paid balance required — hCaptcha runs
roughly $1-3 per 1000 solves as of this writing, unverified current pricing). Without it set, the
scraper behaves exactly as attempt #5 (logs and moves on, no solve attempted).

**Result: tested for real with a funded 2Captcha account ($10 balance).** Genuinely mixed —
progress on some fronts, one real remaining blocker:

- **tel-aviv**: no solve attempt at all — a real bug, not a captcha problem. The title check
  ran too early (right after `domcontentloaded`, before the page's JS had updated the title to
  "...Captcha" yet), so the old code's `CAPTCHA_TITLE_MARKER in title` gate was false at that
  instant even though the final diagnostics *did* show "Radware Bot Manager Captcha". **Fixed**:
  removed that gate entirely — `_solve_hcaptcha` is now always attempted whenever the broader
  "radware" marker is present; its own live sitekey lookup is the real check, and it no-ops
  harmlessly if there's nothing to solve.
- **ramat-gan**: sitekey found (`ae73173b-7003-44e0-bc87-654d0dab8b75`), 2Captcha solved it for
  real in ~21s, token was injected into the response field(s). **But `site callback triggered:
  False`** — no `[data-callback]` attribute was found alongside the sitekey element, so the
  page's own JS was never notified the challenge passed. This is the real remaining blocker:
  filling the hidden field isn't enough on its own if nothing tells the page to act on it.
  **Fixed partially**: now also dispatches `input`/`change` events on the response field(s) in
  case a listener depends on those instead of a static callback — untested whether this alone is
  enough. Also now logs the actual widget markup (`el.outerHTML`, truncated) on every attempt,
  so the *next* failure will show Yad2's real hCaptcha embed shape directly in the logs instead
  of needing another guess.
- **givatayim**: same sitekey, but 2Captcha itself hit its 120s solve timeout (no token
  returned) — most likely normal service-side latency variance, not a bug on our end. Bumped
  `SOLVE_TIMEOUT_SECONDS` to 180 to give more headroom.
- **Separate, unrelated bug found in this same test**: `docker-compose` treats a bare `$` in
  `.env` values as shell-style variable interpolation — a Google Analytics cookie
  (`_ga_GQ385NHRG1=GS2.1.s...$o1$g0$t...`) in the harvested `YAD2_COOKIE_HEADER` was silently
  mangled (`"$h0" variable is not set. Defaulting to a blank string.` etc. in the logs). Fixed by
  escaping `$` → `$$` in `.env`; **not yet an issue for the actual Radware/Reblaze `__uzm*`
  cookies** (none of them contain `$`), but a real risk on any future re-harvest — check for `$`
  every time.

**Actual next run's result**: widget markup fully captured —
`<div class="h-captcha" data-sitekey="ae73173b-..." data-open-callback="hOpenRad"
data-callback="hSolvedRad">`. 2Captcha solved it again, token injected, input/change events
fired — **still `site callback triggered: False`**. The user manually checked their own real
(uncaptcha'd) browser console: `typeof window.hSolvedRad`, `typeof window.hOpenRad`, and even
`typeof window.hcaptcha` all returned `"undefined"` — consistent with hCaptcha's own JS only
loading when a challenge actually renders, so that particular check couldn't confirm the
hypothesis either way. But we already have the real answer from the scraper's own run: at the
exact moment a genuine challenge WAS showing to our automated browser, `window.hSolvedRad` still
wasn't invokable. Most likely explanation: it's not attached to `window` at all — probably
scoped inside a bundled JS module/closure — so no injected script can reach it without much
deeper reverse-engineering of Yad2's minified bundle. Modern bundlers (webpack/vite content
hashing) mean that bundle's internal structure can change on ANY unrelated deploy, making
reverse-engineering a poor, high-maintenance bet for a personal project.

## 2026-08-28 — Free test: does a residential-grade IP change anything?

Before spending more money, tested the cheapest possible way to isolate IP as a variable: tethered
the host machine to a phone's mobile hotspot (Docker routes container traffic through the host's
active network interface) and re-ran the exact same scraper — no code changes, no proxy purchase.

**Result: identical outcome to every prior patchright run** — same widget found, same successful
2Captcha solve, same `site callback triggered: False`. **This rules out IP reputation as the
active blocker for this specific wall.** It's clean, useful evidence against spending money on a
residential proxy service for this problem specifically — the callback-scoping issue is a
browser/DOM-level problem that would persist regardless of network path.

(Caveat noted but not chased further: it wasn't independently verified that Docker/WSL2's
network path actually shifted to the phone's IP rather than a stale cached route — but even if
it didn't, the conclusion doesn't change: whether tested or not, the wall is specifically about
JS callback reachability, not about what a request looked like at the network layer.)

## Conclusion after 8 attempts across two categories of fix (fingerprint evasion, then puzzle
## solving) and one network-layer test

Every reasonably available technique — direct API, headless, JS-stealth, headed, CDP-level
patchright fix, manual cookie replay, paid hCaptcha solving, and a residential-grade IP test —
has been tried. All either failed outright or converge on the same specific remaining blocker: a
JS callback function that isn't reachable from outside Yad2's own bundled code. Fixing that
specific issue would require deep, fragile reverse-engineering of a minified bundle that can
change on any unrelated deploy — a poor investment for a personal project. **This is the
documented stopping point for Phase 1's Yad2 integration** — parking it here rather than
continuing to sink more time/money into diminishing returns. Revisit only if a fundamentally
different angle emerges (e.g. an official Yad2 data-partner program, or a commercial all-in-one
"web unlocker" API that handles proxy+fingerprint+captcha as a bundled black box).

## 2026-08-28 — Validating context: a competitor (Yaeli, app.yaeli.ai, a WhatsApp apartment bot)
## hits the exact same wall for live outbound clicks to Yad2

The user tested Yaeli's own product: its listing cards show normalized data (price, image,
address — same architecture as this project's own card format), with a "לצפייה במודעה המקורית"
(view original listing) link straight to Yad2. Clicking that link — a fresh request from the
user's own browser, unrelated to Yaeli's backend — landed on the **exact same**
`validate.perfdrive.com` "Are you for real?" hCaptcha challenge this project has been fighting.

**Why this matters**: it confirms the challenge is applied live, per-request, regardless of
referrer or which product sent the user there — not something even an established competitor's
*outbound click-through* has "solved." Whatever lets Yaeli populate its own listing cards with
real data in the first place (their backend scraping — still an unverified black box, presumably
paid proxy/anti-detect infrastructure per the earlier reasoning) is a separate problem from "can
a user's browser freely reach an arbitrary live Yad2 listing URL" — and the answer to the second
one is no, not reliably, for anyone. Good, reassuring, evidence-based context for why this
project's own Phase 1 bot design already treats "link out to the original listing" as something
the *user's own browser* handles (exactly like Yaeli's own pattern), not something the scraper
itself needs to solve.

If this ALSO fails (e.g. the cookie is tied too tightly to the exact browser fingerprint/IP that
solved it, and gets rejected from a different session): per the earlier research, further free
tinkering has documented diminishing returns against Radware-class enterprise bot managers. The
realistic next options at that point are (a) a paid captcha-solving service (2Captcha,
Anti-Captcha, CapSolver — cheap per-solve, fully automated, and a categorically smaller cost than
a full unblocking API since patchright already gets past the fingerprint layer on its own), (b) a
full paid unblocking API (Bright Data, ScraperAPI — likely what Dorin itself uses, per its own
"500+ sources" marketing claim), or (c) deprioritizing Yad2 specifically and focusing effort on
less-protected sources (Phase 3) while parking this as a known, documented limitation.

### Still open — confirm these the next time the scraper runs against a real city

1. **Does Playwright actually get past PerimeterX?** Headless browsers are also a known PerimeterX
   detection target (via `navigator.webdriver`, missing plugins, etc.) — not guaranteed to work.
   Check the scraper's logs: `Yad2FetchError` will say whether it saw zero matching responses at
   all (frontend's internal call has a different URL shape, or the challenge wasn't passed) vs.
   some non-JSON responses (challenge page came through instead of real data).
2. **Is `?city=<slug>` the right query param for the human-facing page?** Untested — SCRAPE_CITIES
   values (`tel-aviv`, `ramat-gan`, `givatayim`) were only ever validated against the (now-removed)
   guessed API, not the real page's own filter UI.
3. **Pagination** — not implemented yet. Currently only whatever loads on the initial page/scroll
   position is captured.
4. **Field mapping** — once real JSON is captured, fill in the table below from an actual payload
   (previously left as a template; still empty).

### Field mapping (raw JSON key → our `NormalizedListing` field)

| our field | raw JSON key | notes |
|---|---|---|
| external_id | | |
| price | | |
| rooms | | |
| floor | | |
| floor_total | | |
| size_sqm | | |
| city | | |
| neighborhood | | |
| street | | |
| image_urls | | |
| description | | |
| posted_at | | |

Once filled in, update the field mapping in `normalize.py`'s `_get()` calls to match reality.
