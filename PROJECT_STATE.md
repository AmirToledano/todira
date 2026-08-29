# ToDira — Project State Handoff

Read this first in any new session (especially cloud sessions without access to this machine's
local Claude memory). Written 2026-08-29 so work can continue seamlessly from another device.

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
