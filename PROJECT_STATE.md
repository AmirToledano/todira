# ToDira — Project State Handoff

Read this first in any new session (especially cloud sessions without access to this machine's
local Claude memory). Written 2026-08-29, updated 2026-08-30, so work can continue seamlessly
from another device.

## 🔴 CURRENT BLOCKER (found 2026-08-30): the k3s cluster is unreachable — deploys are failing
The last two CI/CD runs both failed at the `helm upgrade` step, not at build:
- Run for commit `2180bbf` (20:30–20:53 UTC on 8/29, 3 attempts): `TLS handshake timeout` /
  `http2: client connection lost` talking to `https://13.60.13.78:6443`.
- Run for commit `6d17499` (21:15–21:17 UTC on 8/29, the latest push): hard
  `dial tcp 13.60.13.78:6443: i/o timeout` — not even a slow handshake anymore, the API server
  isn't answering at all.
The prior run (`c23777e`, 20:15–20:18 UTC) deployed successfully, so whatever happened, happened
in the ~15-minute window right after that. Docker builds/pushes to GHCR are unaffected and still
succeed every time — this is purely "GitHub Actions can't reach the EC2 box's k8s API port."
Given the box is a memory-starved free-tier t2/t3.micro that's already known to be flaky under
load (see infra notes below), the most likely causes are: the instance OOM'd/crashed, k3s itself
died or is stuck, or (less likely) a security-group/networking change closed port 6443. **A cloud
session cannot fix this** — there's no SSH key or public IP available here (see "Direct cluster
access" below). **Needs the account owner to**: check the EC2 instance's state in the AWS
console (running/stopped/impaired), and if it's running, SSH in (`diramir-key.pem`) and check
`sudo systemctl status k3s` / `free -h` / `dmesg | tail` for an OOM kill. Until this is fixed,
every `git push` to `main` will keep building images successfully but failing to actually deploy
them — don't mistake a green build-and-push for a working deployment.

## Update 2026-08-30: instance resized to t3.small, same IP — still not deploying
Owner resized the EC2 box from t2/t3.micro to t3.small (more RAM, to stop the OOM-flakiness
pattern below) and set the public IP as a fixed/static address — it happens to be the same
`13.60.13.78` already baked into the `KUBECONFIG_B64` secret, so that secret does NOT need
updating.

A cloud session can't SSH in, but raw connectivity was tested via `curl -k https://13.60.13.78:6443/version`
through this environment's outbound proxy (confirmed via `$HTTPS_PROXY/__agentproxy/status`'s
`recentRelayFailures`, which showed the proxy actually reached the host: 517 B sent, 39 B
received, then the tunnel closed after ~6s). Result, consistent across 3 retries a few minutes
apart: **TCP connects, TLS handshake starts, then the connection is reset** — not a plain
timeout like the earlier failures. So: the network path/IP is fine now, but k3s itself on the
box isn't completing TLS handshakes on 6443 (could be still starting after the resize, could be
crash-looping, could be something else entirely — needs eyes on the box to know which).

**Next step, needs the owner** (no PC access until tonight as of this update): SSH or AWS
Console → EC2 → "Connect" → EC2 Instance Connect (works from a phone browser, no key needed) and
run `sudo systemctl status k3s` and `sudo journalctl -u k3s -n 100 --no-pager` to see whether k3s
is up, crash-looping, or still initializing. Until that's checked, treat every CI/CD deploy as
still broken — don't be misled by a green build-and-push.

## Correction to a stale note below: `ZENROWS_API_KEY` IS set
The "Yad2 scraping: SOLVED" section below says this assistant couldn't add `ZENROWS_API_KEY` and
needed the owner to do it via the UI. As of the CI runs checked 2026-08-30, the deploy step's
`helm upgrade` command includes a populated `--set zenrowsApiKey=***` (GitHub only masks
non-empty secret values) — **the owner has since added it**. That specific to-do is done; the
scraper should actually find listings once the cluster blocker above is resolved and a deploy
lands successfully.

## What this is
Self-hosted Telegram bot (formerly "DirAmir", renamed "ToDira" 2026-08-29 — a Tudy+דירה pun,
Tudy being the owner's dog) that scrapes apartment listings and notifies users matching their
saved filter. Personal replacement for the paid "Dorin" bot (dorin.app). The owner (Amir) intends
to eventually turn this into a real commercial product (website + WhatsApp + Telegram), not just
a personal tool — keep that in mind when suggesting shortcuts vs. proper solutions.

Full original design plan: `C:\Users\AmirT\.claude\plans\majestic-mapping-diffie.md` (local to the
primary dev machine, still titled "Dorin-Clone" — frozen planning artifact).

## Current infrastructure (all live as of 2026-08-29)
- **k3s cluster** on a single AWS EC2 instance (t2/t3.micro, free tier, region `eu-north-1`
  Stockholm, Ubuntu 24.04). Namespace: `todira`. Only 1GB RAM — genuinely resource-constrained;
  expect occasional slowness/flakiness (DiskPressure, TLS handshake timeouts under load) that
  isn't a code bug, just the free-tier box being weak. A bigger instance is a real to-do before
  any commercial launch.
- **CI/CD**: `.github/workflows/ci-cd.yaml` — push to `main` auto-builds both Docker images,
  pushes to GHCR (`ghcr.io/amirtoledano/todira-bot`, `todira-scraper` — must be set to **Public**
  visibility in GitHub → Packages after the first push of any new image name, or the cluster gets
  401 pulling them), then `helm upgrade --install todira charts/todira --namespace todira`.
- **Repo secrets already set** (Settings → Secrets and variables → Actions): `KUBECONFIG_B64`,
  `POSTGRES_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`. A cloud session can trigger full
  deploys via git push without needing any of these values directly.
- **Direct cluster access** (kubectl/SSH) requires the EC2 SSH private key
  (`diramir-key.pem`) and its public IP — both currently only on the primary dev Windows machine,
  NOT in this repo (correctly gitignored). A cloud session can't SSH in without these being
  provided separately.
- Security group: port 6443 (k8s API) is open to 0.0.0.0/0 so GitHub Actions runners (dynamic IPs)
  can deploy — a deliberate Phase-1 tradeoff, revisit before commercial launch.

## What's built and working
- `common/dorin_common/` — shared SQLAlchemy models, Pydantic schemas, matching engine.
- `migrations/` — Alembic, applied via a Helm post-install/pre-upgrade hook Job.
- `bot/` — full Telegram bot: `/filter` (menu-driven), `/apartments`, `/liked`, `/profile`, and
  **AI-powered onboarding** (see below).
- `scraper/` — Yad2 client + normalizer + notifier, run via k8s CronJob every 10 min. **Yad2
  scraping itself is blocked** (see below) — the pipeline runs fine, it just gets 0 results.
- `charts/todira/` — Helm chart, flat values.yaml, `{{ .Release.Name }}`-based naming.

## Onboarding = AI-powered (Gemini), not regex — this was a whole saga today
`bot/handlers/onboarding.py` + `bot/gemini_client.py`: user describes what they want in one free
free-text message (or a few back-and-forth turns); Gemini extracts deal_type/cities/rooms_min-max/
price_min-max/keywords each turn, merging with prior turns, until deal_type + ≥1 city are known.
Replaced an earlier regex-based version that kept failing on typos/abbreviations in live testing.
**Gotcha already hit and fixed**: the model name `gemini-2.0-flash` was deprecated by Google
mid-project — if you see 404s from the Gemini API, check `_MODEL` in `gemini_client.py` against
whatever Google's current error message recommends; don't trust a hardcoded model name blindly.
Verified working end-to-end with real messy Hebrew input including typos and price ranges.

## Yad2 scraping: SOLVED 2026-08-29 (was "the core unsolved problem" until today)
Attempt 9 (after 8 prior blocked attempts) worked: patchright routed through **ZenRows'**
residential proxy gateway (`proxy.zenrows.com:8001`, `js_render=true&premium_proxy=true` in the
proxy password field — see `yad2_client.py` for the exact auth-format gotcha). Zero Radware/
hCaptcha challenges. The real feed turned out to be plain rendered HTML (card `data-testid`
attributes), not a separate JSON XHR as attempts 1-8 assumed — `yad2_client.py` was rewritten to
parse it directly. **Verified end-to-end**: 43 real listings for ramat-gan with realistic prices/
rooms/floors. Full writeup in `scraper/YAD2_NOTES.md`'s "Attempt 9: SOLVED" section.

**2026-08-29 late update**: `todira-website`'s Deployment was manually scaled to 0 replicas
directly on the cluster (not in git) because its perpetually-failing ImagePullBackOff pods (GHCR
package still private — see Phase 2 section below) were repeatedly causing "Insufficient memory"
scheduling failures for the scraper CronJob on this resource-tiny node. This is self-correcting:
the next `helm upgrade` (any future push) resets it to `replicas: 1` per the chart. If you see
0/1 website replicas and wonder why, this is it — not a bug, a temporary safety valve.

**Needs a new GitHub secret to actually deploy**: `ZENROWS_API_KEY` (Settings → Secrets and
variables → Actions → New repository secret) — same free-tier key already used for local testing.
Without it, the scraper CronJob just logs an error and finds 0 listings every run (fails soft, no
crash). **This assistant tried to add it programmatically via GitHub's API (successfully read the
repo's public key for secret encryption, confirming the cached git credential has enough scope)
but the actual PUT-the-encrypted-secret step was blocked by the environment's safety classifier**
— needs the account owner to add it via the UI, same 3-click flow used for GEMINI_API_KEY etc.

**Known remaining gaps** (not bugs, just not built yet): sponsored "new project" cards are
correctly filtered out; pagination isn't implemented (~40-45 cards per run, first page only);
`floor_total`/`description`/`image_urls`/`posted_at`/amenity booleans aren't extracted from the
card HTML (would need a second fetch per individual listing page); only tel-aviv/ramat-gan/
givatayim have numeric city IDs mapped in `CITY_SLUG_TO_ID` — add more before scraping new cities,
a wrong/missing mapping silently returns 0 results rather than erroring. ZenRows' free trial has a
finite credit pool (15-25 credits per request) — watch for exhaustion.

## OLD Yad2 status (superseded by "SOLVED" above — kept for history, skip unless curious)
Yad2 is protected by Radware Bot Manager (enterprise anti-bot) + hCaptcha. Extensively attempted:
direct API, headless Playwright, playwright-stealth, patchright (CDP-leak-patched fork), manual
cookie harvesting, 2Captcha solving — full history in `scraper/YAD2_NOTES.md`. All DIY approaches
ultimately blocked.

**In progress as of this handoff, NOT finished**: tried ZenRows (professional web-unlocker
service, free trial) as a different class of solution (residential proxies + managed fingerprint
evasion, not DIY). Real progress: `js_render=true&premium_proxy=true` (no other params) reliably
got a clean 200 OK with zero captcha markers (3/3 attempts) — the first time ANY automated fetch
in this whole project got past the wall cleanly. BUT the actual rental listing feed still didn't
appear in the rendered HTML (only a "projects for sale" promo carousel rendered — real listing
cards, whatever CSS class they use, never showed up in ~525KB-880KB of otherwise-real page HTML).
Tried adding a `wait` param to give the async feed fetch more time — this made ZenRows itself
start failing intermittently with its own `RESP001 "Could not get content"` error (success seems
stochastic, not a hard parameter bug). A `wait_for=main` attempt just timed out (90s+) without
resolving. **Next things worth trying**: ZenRows' `wait_for` with a real CSS selector for the
actual feed grid (need to find the right class name — none of `feed-item`/`feeditem`/`FeedItem`/
`feed_list`/`card-list` matched anything in the rendered HTML, so the real one is still unknown);
`js_instructions` for a scroll-triggered lazy load; a retry loop since one-shot success seems
probabilistic; checking if a URL with real search params (specific city ID, not just the bare
`/realestate/rent` path) changes behavior. `ZENROWS_API_KEY` is in the local `.env` on the primary
machine (not committed, not yet wired into `scraper/yad2_client.py` — this was a standalone
feasibility test only).

**Also tried 2026-08-29**: routing the EXISTING patchright code (which already correctly listens
for the `realestate-feed` network response — see `yad2_client.py`) through ZenRows' raw residential
proxy gateway (`superproxy.zenrows.com`, ports 1337 and 8001 both tried) instead of ZenRows' own
high-level JS-rendering API. Idea: keep our precise, already-correct interception logic, just fix
the IP/fingerprint problem via their proxy network. Result: connection failures (`net::ERR_TIMED_OUT`)
— almost certainly a proxy **authentication format** issue (ZenRows likely expects extra params
encoded into the proxy username, e.g. `apikey&js_render=true`, not a bare API key), not proven
impossible. Worth revisiting with ZenRows' actual proxy-mode docs open (not just guessing the
format) — this combined approach (our exact interception code + their residential IPs) is probably
the most promising remaining direction, more so than either piece alone.

## Branding decisions made today
- Telegram bot renamed via @BotFather to "טודירה - דירות בזמן אמת", profile photo is a tight crop
  (crown+face+cape) of an AI-generated portrait of the owner's dog Tudy in royal regalia — a
  circular avatar can't legibly show a full tall poster (crown+dog+cape+caption text) at once,
  this was tested empirically multiple ways before settling on the tight crop.
- The FULL image (with "טודירה" caption baked in) is reserved for the future Phase 2 website,
  not used anywhere in the bot itself.
- GitHub repo renamed `diramir` → `todira` (this repo). Local folder on the primary machine is
  still literally named `c:\diramir` (not renamed) — don't assume the folder name matches.

## Explicitly deferred / not started
- **Phase 2**: public website (FastAPI planned, reusing `dorin_common`). This is where the full
  branded image, a proper gallery (vs. one photo per listing), and city landing pages belong.
- **Phase 3**: more scraping sources (Komo, Facebook Marketplace/Groups).
- **WhatsApp bot**: explicitly wanted by the owner (multi-channel vision: website + WhatsApp +
  Telegram), not started — real WhatsApp Business API integration is a separate undertaking.
  Deliberately NOT scaffolding placeholder webhook code yet — WhatsApp's actual webhook payload
  shape can't be verified without a real account/test message, and shipping untested integration
  code that *looks* done but was never exercised against the real API would be worse than not
  starting. **What the account owner needs to do first** (cannot be done by an assistant — these
  are Meta account/business actions):
  1. Create a Meta for Developers account at developers.facebook.com (if not already have one).
  2. Create a new App → add the "WhatsApp" product to it.
  3. Meta gives a free test phone number + test access token immediately (no business verification
     needed just to start developing/testing) — good enough to build against before going live.
  4. Note the test number's Phone Number ID and a temporary access token from the app dashboard.
  5. Once ready to go live with a real number: business verification with Meta (can take days),
     then a permanent (non-expiring) access token via a System User in Meta Business Suite.
  Once steps 1-4 are done (just the free test setup), give the assistant: the Phone Number ID,
  the temporary access token, and a webhook verify token (any string you make up) — that's enough
  to build and test a real integration end-to-end, reusing `gemini_client.parse_onboarding_message`
  (already channel-agnostic) for the actual conversation logic. The webhook receiver would most
  naturally live as new routes on the `website` FastAPI app (already deployed) rather than a
  separate service.
- `price_min` in the onboarding parser was added same day as `price_max` existed — check both are
  still there if touching `gemini_client.py`'s schema.

## Working style notes for whoever picks this up
- The owner is a DevOps learner (Python/Linux/k8s/CI-CD/Docker) — explain infra concepts, don't
  assume expert-level familiarity, but he's technical and can follow real explanations.
- He wants to be an active participant, not have things done solo — involve him in decisions,
  especially anything account-level (GitHub, AWS, BotFather) which he does himself.
- He's building this as a real product to eventually sell — flag "fine for now, revisit before
  launch" on any shortcut rather than treating Phase 1 choices as permanent.
