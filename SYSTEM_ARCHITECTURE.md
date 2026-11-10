# Todira: system architecture

Written 2026-11-10 from the code on `main` (commit `5978eb3`), for an outside project manager.
Every statement here was read from the repository. Where something could only be measured on the
live system, the date of the measurement is given.

**What is deliberately not in this file:** secret values, the server's IP address, the AWS account
number, and the owner's personal details. They are not needed to understand the system, and the
project rule (`CLAUDE.md`) is that they never appear in code, commits or logs. Section 9 lists where
each secret lives.

Related documents: `README.md` (short overview), `RUNBOOK.md` (what to do when the server is down),
`PROJECT_STATE.md` (the running history and the waiting list, newest first), `DESIGN.md` (the design
language), `CLAUDE.md` (the rules for the AI assistant that works on this repository).

---

## 1. What the product is

Todira is an Israeli apartment-alert service. A person describes the flat they want in a Telegram
bot (free text, a voice message or a menu). From then on, every new matching listing, and every
price change on one, is sent to them on Telegram. The website `todira.app` shows the same matches
with a map, a filter, saved flats, payment and an admin area. Bot and site share one account and
one saved search per person.

Access: a 10-day free trial, then a one-time pass with no auto-renewal: 7 days for ₪19.90, 14 days
for ₪29.90, 30 days for ₪49.90 (`common/todira_common/access.py`, Takbull hosted payment page).

Listings come from five sources, plus owners who post directly on the site:

| Source (`listings.source`) | What it is |
| --- | --- |
| `yad2` | Yad2 rentals and sales |
| `komo` | Komo rentals and sales |
| `homeless` | Homeless rentals and sales |
| `facebook_groups` | Posts in the Facebook groups a dedicated account has joined |
| `facebook_marketplace` | Facebook Marketplace property rentals |
| `owner` | A flat an owner posted on `todira.app/post`, after the owner of Todira approves it |

Rule from `CLAUDE.md`: nothing a user reads (site, bot, channel, Instagram) names these sources.

---

## 2. The big picture

```
                    GitHub (code, Actions, container registry ghcr.io)
                          │  push to main: test → build 4 images → helm upgrade
                          ▼
   Porkbun DNS  ──A record──►  one AWS EC2 server (t3.small, 2 GB, eu-north-1, Elastic IP)
   todira.app                  └─ k3s (single-node Kubernetes), namespace "todira", Helm release "todira"
                                   ├─ Caddy        ports 80/443 on the host, TLS, → website:8000
                                   ├─ website      FastAPI + Jinja (+ a few React pages)
                                   ├─ bot          python-telegram-bot, long polling
                                   ├─ postgres     PostgreSQL 16, 2 Gi volume on the server's disk
                                   └─ CronJobs     scraper, facebook scraper, backup, healthcheck,
                                                   daily summary, subscription housekeeping
                          ▲                                   │
   visitors (browser) ────┘                                   ├─► Telegram Bot API (alerts, owner messages)
   Telegram users ──► Telegram ──(bot polls)                  ├─► listing sources (section 5)
                                                              ├─► S3 (nightly backup)
                                                              └─► Gemini, Resend, Takbull, Google OAuth
```

There is one environment: production. There is no staging server.

---

## 3. AWS

Everything Todira uses in AWS (`PROJECT_STATE.md`, `RUNBOOK.md`, `charts/todira/values.yaml`):

| Resource | Details |
| --- | --- |
| EC2 instance | One `t3.small` (2 vCPU, 2 GB RAM), region `eu-north-1` (Stockholm). Runs k3s and every workload. |
| EBS volume | 20 GB, the instance's only disk. Postgres data, the bot's state file and Caddy's certificates live on it. |
| Elastic IP | One, associated with the instance. `todira.app`'s A record and the kubeconfig used by CI/CD both point at it. |
| S3 bucket | Nightly database backups (`backup.s3Bucket` in `values.yaml`, same region). |
| IAM user | `todira-backup-bot`, S3 only. Its key is what the backup job uses. The root access key is deactivated. |
| Access to the server | AWS Systems Manager Session Manager (and CloudShell). The Kubernetes API (port 6443) is open for GitHub's deploys and protected by client certificate. Closing SSH port 22 is on the waiting list. |

Not used: load balancer, RDS, NAT gateway, auto scaling, CloudFront, Route 53, a second server.
Cost per `PROJECT_STATE.md`: about $20 to $22 a month, currently covered by Free Tier credit.
The owner's Terraform studies use a different region (`eu-west-1`) and are not part of Todira
(`docs/aws-terraform-user.md`).

**DNS and TLS.** The domain is registered at Porkbun. One A record points `todira.app` straight at
the Elastic IP. No Cloudflare or other proxy in front. Caddy obtains and renews the Let's Encrypt
certificate itself.

**If the IP ever changes**, three things must be updated (done once already, `PROJECT_STATE.md`):
the Porkbun A record, the `KUBECONFIG_B64` GitHub secret, and `tls-san` in
`/etc/rancher/k3s/config.yaml` followed by a k3s restart. The Telegram bot is unaffected (it polls).

**Known limits of this setup.** One server is a single point of failure: if it stops, the site, the
bot, the database and the scrapers all stop. Memory is the tightest resource (section 4.4).

---

## 4. Kubernetes and Helm

One Helm chart, `charts/todira/` (chart version 0.1.0), installed as release `todira` in namespace
`todira`. `values.yaml` holds every non-secret setting with the reasoning behind it in comments.

### 4.1 Long-running workloads

| Workload | Image | Replicas / strategy | Network | Storage | Health |
| --- | --- | --- | --- | --- | --- |
| `todira-postgres` (Deployment) | `postgres:16-alpine` | 1, `Recreate` | ClusterIP service, port 5432 | PVC 2 Gi at `/var/lib/postgresql/data` | `pg_isready` liveness and readiness |
| `todira-bot` (Deployment) | `todira-bot` | 1, `Recreate`. Must stay 1: Telegram rejects two pollers on one token. | Outbound only (long polling) | PVC 50 Mi at `/data` (conversation state, `PicklePersistence`) | exec liveness probe |
| `todira-website` (Deployment) | `todira-website` | 1 | NodePort service 8000 → node port 30080 (direct fallback) | none | `GET /healthz` liveness and readiness |
| `todira-caddy` (Deployment) | `caddy:2.8-alpine` | 1, `Recreate`, `hostNetwork: true` | Binds host ports 80 and 443 | PVC 100 Mi at `/data` (certificates), ConfigMap with the Caddyfile | liveness on port 80 |

Caddy (`caddy-configmap.yaml`): serves `todira.app`, compresses (zstd, gzip), sets HSTS, caches
versioned static files for a year and other static files for a day, and reverse-proxies everything
to `todira-website:8000`. There is no Kubernetes Ingress resource.

### 4.2 Scheduled jobs (CronJobs)

All use `concurrencyPolicy: Forbid`. Times are Israel time (`timeZone: Asia/Jerusalem`) unless noted.

| CronJob | Schedule | What it runs | Notes |
| --- | --- | --- | --- |
| `todira-scraper` | `0,30 9-22 * * *` (every 30 min, 09:00 to 22:30) | `scraper/main.py`, sources Yad2, Komo, Homeless | `backoffLimit: 0`, `restartPolicy: Never`: a crash fails visibly instead of silently re-running and re-billing paid requests. Each run waits a random 0 to 8 minutes before starting. |
| `todira-facebook-scraper` | `24 8-22 * * *` (hourly at :24) | Same `scraper/main.py` with `SCRAPE_SOURCES=facebook_marketplace,facebook_groups` | Uses the `todira-facebook` image (adds Playwright + Chromium). Deadline 17 minutes. Gives up its turn if the main scraper holds the run lock. |
| `todira-backup` | `0 3 * * *` | `pg_dump` (init container) then `aws s3 cp` | Deadline 10 minutes. Telegram alert to the owner on failure. |
| `todira-healthcheck` | `*/15 * * * *` (UTC, no timeZone set) | `curl $WEBSITE_URL/healthz` | Telegram alert to the owner on failure. |
| `todira-daily-summary` | `52 8 * * *` | `website/daily_summary.py` | Morning summary to the owner's Telegram group. |
| `todira-subscription-housekeeping` | `0 4 * * *` | `website/subscription_housekeeping.py` | Stops Takbull recurring billing for cancelled users. |

One Helm hook: `todira-migrations` (Job, `post-install,pre-upgrade`) runs
`alembic upgrade head` from the bot image, retrying up to 30 times while Postgres starts.

The two scrapers never run at the same time: both take one Postgres advisory lock
(`_RUN_LOCK_KEY` in `scraper/main.py`). The main run waits up to 10 minutes for it; the Facebook
run skips its turn instead.

### 4.3 Images

Built by CI/CD and pushed to GitHub Container Registry as `ghcr.io/<owner>/todira-<service>`,
tagged with the commit SHA and `latest`. All are `python:3.12-slim` with
`common/todira_common` copied in and `PYTHONPATH=/app`.

| Image | Dockerfile | Entry point |
| --- | --- | --- |
| `todira-bot` | `bot/Dockerfile` | `python main.py` (also carries `migrations/`) |
| `todira-scraper` | `scraper/Dockerfile` | `python -u main.py` |
| `todira-facebook` | `scraper/Dockerfile.facebook` | same, plus Playwright 1.48 and Chromium |
| `todira-website` | `website/Dockerfile` | `uvicorn main:app --host 0.0.0.0 --port 8000` |

### 4.4 Resource limits (`values.yaml`, `resources`)

| Workload | Memory request / limit | CPU request / limit |
| --- | --- | --- |
| postgres | 256 Mi / 512 Mi | 100m / 500m |
| website | 256 Mi / 768 Mi | 100m / 500m |
| bot | 128 Mi / 256 Mi | 50m / 250m |
| scraper (both) | 256 Mi / 1536 Mi | 100m / 500m |
| caddy | 32 Mi / 96 Mi | 25m / 250m |
| backup | 64 Mi / 256 Mi | 50m / 250m |
| daily summary, housekeeping | 64 Mi / 128 Mi | 25m / 100m |
| healthcheck | 16 Mi / 32 Mi | 10m / 50m |

The limits add up to more than the server's 2 GB on purpose (they are ceilings, not reservations).
The node has gone `NotReady` in the past when two scrapers ran together, which is why the run lock
and the :24 offset exist.

### 4.5 Secrets and configuration in the cluster

- `todira-postgres-secret`: the database password and the full `DATABASE_URL`.
- `todira-bot-secret`: every other secret, rendered by Helm from values that CI/CD passes in
  (section 9). A few keys are **not** in the chart and are added to the same secret by manual
  workflows: `bright-data-isp-host/-user/-pass`, `rotating-proxy-url`, the Facebook cookies, and
  optional Takbull / Bright Data keys. All are referenced with `optional: true`, so a missing key
  never stops a pod from starting.
- Feature settings (schedules, per-run caps, on/off switches) are plain values in `values.yaml`.
- Runtime switches the owner flips from the site's admin page are rows in the `app_flags` table
  (`common/todira_common/switches.py`), not Kubernetes objects.

---

## 5. Database (PostgreSQL 16)

One database, `todira`, in the `todira-postgres` pod. Schema is managed by Alembic: 40 migrations
in `migrations/versions/` (`0001_initial_schema` to `0040_price_sanity`), applied automatically
before every deploy. ORM models: `common/todira_common/models.py`. No extensions beyond the default.

### 5.1 Tables

| Table | Columns | What it holds |
| --- | --- | --- |
| `users` | 27 | One row per person: Telegram id and name, Google id and email, language, trial end, paid-until, alert hours and weekend setting, invite (referral) fields, reminder timestamps. |
| `filters` | 42 | One saved search per user (one-to-one): deal type, property types, cities, neighbourhoods and streets to include or exclude, price, rooms, floor, minimum size, required amenities, safe-room and furniture preference, keywords, move-in dates, map region, "no brokers", "flexible match". |
| `listings` | 41 | Every ad: source and its id there, URL, deal type, price, rooms, floor, size, city, neighbourhood, street, coordinates, amenities, description, image URLs, raw payload, first seen / last seen, delisted flag, previous price, duplicate link, parsing timestamps. |
| `sent_notifications` | 5 | Which listing was sent to which user and why (`new`, `price_drop`, `price_increase`). Prevents repeats. |
| `held_alerts` | 3 | Matches that arrived outside a person's alert hours, waiting to be sent. |
| `user_listing_actions` | 5 | Liked, hidden, "found my flat". |
| `payments` | 11 | Purchases: plan, amount, status, gateway transaction id. |
| `owner_posts`, `owner_post_photos` | 17, 4 | Flats owners post on the site, their photos, review status, manage token. |
| `contact_messages` | 8 | Contact form and site feedback. |
| `pending_google_links` | 5 | Short-lived tokens that link a Google sign-in to a Telegram account. |
| `app_flags` | 3 | Key/value: admin switches, scraper cursors and one-time markers, "already sent" markers for periodic messages. |
| `activity_days` | 4 | Daily usage counters (counts only, never message text). |
| `alembic_version` | 1 | Current migration. |

### 5.2 Relations and indexes

- `filters`, `payments`, `sent_notifications`, `held_alerts`, `user_listing_actions` reference
  `users` with `ON DELETE CASCADE`. The last three also reference `listings` with cascade.
- `listings.duplicate_of_id` → `listings` (the same flat on two sources is stored twice and shown
  once), `owner_posts.listing_id` → `listings`, `users.referred_by_user_id` → `users`: all
  `ON DELETE SET NULL`.
- Unique: `listings(source, external_id)`, `sent_notifications(user, listing, reason)`,
  `user_listing_actions`, `owner_posts.manage_token`.
- Indexes on `listings`: city, deal type, source, first seen, last seen, duplicate link, and a
  partial index for unparsed text. `filters.cities` has a GIN index.

### 5.3 Size and retention

- A listing is deleted once it is older than 30 days and no longer published on its source (delisted for a week, or
  not seen for a month). A still-published ad is kept (`LISTING_RETENTION`, `_delete_expired_listings`).
- Owner posts expire after 30 days; a poster's details are deleted within 60 days.
- Measured 2026-11-09: 42,863 live rental listings matched an unrestricted search.

### 5.4 Backups

| Copy | When | Where | How |
| --- | --- | --- | --- |
| Nightly | 03:00 Israel | S3 bucket, same AWS account | `todira-backup` CronJob: `pg_dump` gzip → `aws s3 cp`. |
| Off-site | 00:40 UTC daily | The owner's Google Drive | GitHub workflow `offsite-backup-gdrive.yaml`: encrypted (7-Zip AES-256), 30 nights kept, plus a weekly bundle of the code. Per `PROJECT_STATE.md` this is waiting for the owner's keys. See `docs/offsite-backup.md`. |

Restore steps are in `RUNBOOK.md`.

---

## 6. The scraper: how listings get in and alerts go out

Entry point: `scraper/main.py`. Each CronJob run starts one process that does one cycle and exits.

### 6.1 One run, step by step (`run_once`)

1. **Start.** Random delay of 0 to 8 minutes (`SCRAPER_START_JITTER_MAX_SECONDS`), then take the run
   lock. A run has a 22-minute budget for catch-up work so it ends before the next slot.
2. **Scrape** the active sources concurrently (section 6.2). Each returns normalized listings, the
   ids it saw, and whether everything succeeded.
3. **Upsert** into `listings` (new rows, price changes).
4. **Enrich new Yad2 listings** with their details (section 6.4).
5. **Homeless descriptions** for new and backlog listings.
6. **Delisting.** Per source, mark ads no longer seen. For Yad2, an ad unseen for a day is checked
   against Yad2's own per-ad endpoint before it is hidden; if part of a run failed, only ads Yad2
   confirms are gone are hidden.
7. **Clean-up of data:** city names, cross-source duplicates and reposts (`scraper/dedup.py`).
8. **Alerts** (`scraper/notifier.py`): match new and price-changed listings against every active
   user's filter (`common/todira_common/matching.py`), respect access, alert hours and weekend
   setting (out-of-hours matches go to `held_alerts`), send Telegram cards, record
   `sent_notifications`.
9. **Catch-up within the budget:** Yad2 details backfill, text features (floor, amenities, entry
   date read from the ad's own text).
10. **Main run only, mornings 09:00 to 12:00 where a message is involved:** access-ending reminders,
    "is your search still right?" check-ins, posts to the public Telegram channel, win-back
    messages, the Sunday report, occasional messages (nudges), the morning email, the source-drop
    warning, the weekly Instagram kit for the owner, owner-post expiry, deletion of expired listings.

A second process, the Facebook run, executes the same code for the two Facebook sources and also
forwards "someone is looking for a flat" posts to the owner (`scraper/seeker_leads.py`).

### 6.2 How each source is fetched

| Source | Module | Route | Paid service involved |
| --- | --- | --- | --- |
| Komo | `scraper/komo_client.py` | Plain direct requests (`httpx`), no proxy. One nationwide id list each for rent and sale, then a detail page per new id (up to 800 a run, 5 at a time). 200 known ads are re-read each run for price changes. | None |
| Homeless | `scraper/homeless_client.py` | Free route: a request with a browser TLS fingerprint (`curl_cffi`). Rolling pagination, 6 pages a run. | ZenRows as fallback, capped at 10 requests a run |
| Facebook groups | `scraper/facebook_browser/feed.py` | One headless Chromium session per run, signed in with the dedicated account's cookies, scrolling the groups feed 24 times. A login or checkpoint page pauses the source for 24 hours and tells the owner. | None |
| Facebook Marketplace | `scraper/facebook_client.py` | Requests with the same cookies, only in the runs of the 08, 14 and 20 o'clock hours. | None |
| Yad2 | `scraper/yad2_client.py`, `common/todira_common/yad2_item_api.py` | See 6.3 | Bright Data Web Unlocker as fallback |
| Owner posts | `website/owner_posts.py` | Form on the site, approved by the owner in `/admin/posts`. | None |

Facebook never runs unless `SCRAPE_SOURCES` names it, so deploying code alone cannot start
requests on the dedicated account.

### 6.3 Yad2 routes: free route, Webshare proxy pool, Web Unlocker fallback

Yad2 is reached through two JSON endpoints: the **map** (which ads exist in a rectangle, at most
200 per answer) and the **item** endpoint (one ad's details). The country is split into 7 regions
(`REGIONS_ON_MAP_API`).

**The three ways a request can leave the server**

| Route | Code | What it is |
| --- | --- | --- |
| Free route | `_fetch_json_with_browser_tls` (map), `yad2_item_api._request_once` (item) | A direct request with a Chrome TLS fingerprint (`curl_cffi`, `impersonate="chrome"`). Enabled by `YAD2_FREE_MAP_FETCH` / `YAD2_ITEM_API`. |
| Free route through the proxy pool | same two functions | Since the owner's commits `a26f42b` and `f6706b5` (2026-11-10), when `ROTATING_PROXY_URL` is set each of these requests goes out through one randomly chosen proxy from that list (the Webshare pool, stored as `rotating-proxy-url` on the bot secret). With the variable empty they go direct, as before. |
| Web Unlocker (paid) | `_fetch_direct` → `bright_data_client.fetch_via_web_unlocker` | Bright Data's Web Unlocker API (zone `web_unlocker1` unless `BRIGHT_DATA_WEB_UNLOCKER_ZONE` says otherwise). Billed per request. |

**Which route each kind of request uses**

| Request | First try | Fallback | If both fail |
| --- | --- | --- | --- |
| Rent, one map request per region (7 a run) | Free route (via the proxy pool when set) | Web Unlocker | Up to 3 attempts 5 seconds apart, then the region is skipped for this run |
| Rent, map sweep in smaller rectangles (`YAD2_TILE_SWEEP`) | Free route (via the proxy pool when set) | **None**: the sweep never uses the paid route | A failed rectangle is counted; 5 in a row stop the sweep. Limits: 1,500 requests and 25 minutes a run, 0.4 s between requests. |
| For sale (`YAD2_SALE_TILE_SWEEP`) | Same sweep, for-sale map | None | Same as above. The older for-sale search-page route (Web Unlocker only) is skipped while this sweep is on. |
| One ad's details, and "is this ad still published?" | Item endpoint, free route (via the proxy pool when set) | Gemini URL reading, currently off (`yad2DetailViaGemini: false`) | Left for the next run. The item route pauses itself after repeated failures. |
| Legacy search pages (`fetch_region_pages`) | ZenRows, sent through `StealthHTTPClient` | None | Only used for a region missing from `REGIONS_ON_MAP_API`; today all 7 are there, so this path is idle. |

`scraper/utils/stealth_http.py` (`StealthHTTPClient`) is the helper that reads
`ROTATING_PROXY_URL` and picks a proxy. The map route uses only that proxy picker. For requests
sent through the client itself (the idle ZenRows path) it also rotates browser-like headers, waits
a random 3 to 7 seconds, and on a 403/429 or network error retries on a different proxy.

**What was measured.** On 2026-11-09 21:35, before a proxy pool was in use, the last three main
runs each logged 27 free-route map requests answered with HTTP 302 (blocked) and 27 Web Unlocker
calls; Yad2 still brought 2,178 new listings that day, through the fallback. Whether the proxy pool
changes this has not been measured since. The same check can be re-run with the workflow
`diagnose-owner-filter-volume.yaml`.

**Ownership of this part.** The owner wrote and maintains the proxy routing in the two free
routes, and decided on 2026-11-09 to keep Yad2, Bright Data and ZenRows as they are. The AI
assistant does not build or extend ways around Yad2's blocking (`PROJECT_STATE.md`, 2026-11-08 to
10), so changes here go through the owner.

### 6.4 Listing details and text

- Yad2 details: `todira_common/yad2_detail.py` chooses the route (item endpoint, then Gemini if
  enabled). Used when a listing is new, in the backfill, just before an alert, and when a visitor
  opens a listing that still lacks details (`listing_enrichment.py`).
- Bright Data's Data Collector (`bright_data_client.fetch_listing_description`) exists for
  on-demand descriptions; its keys are optional.
- `todira_common/text_features.py` reads floor, amenities, property type and entry date out of an
  ad's own free text, for every source.
- `todira_common/non_home.py` and `price_sanity.py` keep parking spaces, storage rooms and
  mis-filed prices out of matches.

### 6.5 Safety switches

`scraper.suspended`, `scraper.facebook.suspended`, `notificationsSuspended`,
`brightDataEnrichmentSuspended` in `values.yaml`; per-run caps for every paid or heavy step; the
workflow `emergency-stop-scraper.yaml` kills a running scraper job; `source_watch.py` warns the
owner the same day a source brings far fewer flats than usual.

---

## 7. The website and the bot

### 7.1 Website (`website/`)

- FastAPI, server-rendered Jinja2 templates (47 in `website/templates/`), one stylesheet
  (`static/style.css`, design tokens per `DESIGN.md`). `website/main.py` has 82 routes.
- A few pages are React islands built with Vite from `website/landing-react/` into
  `static/landing/` (login, contact, account, about, terms, privacy, accessibility, classic home).
  The built files are committed; there is no Node step in CI.
- Sign-in: Telegram Login Widget, Google OAuth, and signed, time-limited links from the bot
  (`uid_token.py`). Sessions are a signed cookie (`SESSION_SECRET_KEY`).
- Main areas: public pages and city pages for search engines, `/search` (preview without an
  account), `/apartments` (matches with map and filter), `/liked`, `/hidden`, `/filter`,
  `/account`, `/upgrade` and payment, `/post` (owners), `/reviews`, guides and a rent calculator,
  `/admin` (dashboard, users, messages, posts, switches), the site assistant (`assistant.py`,
  Gemini, its own API key and daily caps), `/healthz`.
- Payments: Takbull hosted page; `POST /webhooks/takbull/<secret>` confirms a payment
  (`takbull_client.py`).
- 11 languages: Hebrew, English, Russian, French, Arabic inline in `i18n.py`; Spanish, Portuguese,
  Hindi, Filipino, Thai, Chinese as files in `i18n_langs/`.
- Installable to a phone's home screen (`static/pwa.js`, `/sw.js`, web manifest).

### 7.2 Bot (`bot/`)

- `python-telegram-bot`, long polling (no webhook, no public port). Conversation state is kept in
  a file on the bot's volume.
- Handlers (`bot/handlers/`): start and deep links, onboarding from free text or voice, the
  `/filter` menu, `/apartments`, `/liked` and `/hidden`, `/profile`, `/language`, `/invite`,
  `/support`, alert-hours menu, check-in answers, testimonials, the "fewer messages" button, the
  owner's inbox groups, a catch-all for free text, usage counting.
- Gemini is a helper for understanding free text (`gemini_client.py`, gated by `ai_gate.py`); the
  bot works without it using rule-based parsing (`search_text.py`).

### 7.3 Shared code (`common/todira_common/`)

Copied into every image. The core: `models.py`, `db.py`, `enums.py`, `schemas.py`,
`matching.py` (pure matching logic), `listing_matches.py` (the "which listings match" query),
`cards.py` (Telegram card rendering), `access.py`, `alert_hours.py`, `referrals.py`,
`area_price.py`, `email_client.py` and `email_digest.py`, `owner_inbox.py` and `owner_alert.py`,
`activity.py`, `app_flags.py`, `switches.py`, `bot_strings.py` and `bot_langs/`, `cities.py` and
`localities_data.py` (generated by `scripts/build_localities.py`), plus the Yad2 and Bright Data
clients named in section 6.

---

## 8. CI/CD and GitHub

### 8.1 Branches and merging

- Work happens on a `claude/...` branch. A pull request is opened as an audit trail and merged
  into `main`. There is no required review and no CI on pull requests.
- `main` is production: a push to it that touches code, tests, migrations, the chart, a
  requirements file, a Dockerfile or the workflow itself starts a deploy. A change to
  documentation only does not.
- Owner's rule: merge between scraper runs (the main scraper starts at :00 and :30 and takes
  20 to 25 minutes; a migration that lands mid-run once hung a deploy).

### 8.2 The pipeline (`.github/workflows/ci-cd.yaml`)

```
push to main
  ├─ test            Python 3.11, pip install -r requirements-test.txt, python -m pytest tests/ -v
  ├─ import-check    bot, scraper, website: each laid out like its image with only its own
  │                  requirements, every module imported (.github/scripts/check_service_imports.py)
  ├─ build-and-push  (needs both) 4 images → ghcr.io, tagged <commit sha> and latest
  └─ deploy          (needs build) helm upgrade --install todira charts/todira
                       with the image tags and every secret passed by --set,
                       then prints pod status and logs of bot, website, Caddy and backup
```

- The migrations hook runs inside `helm upgrade`, before the new pods start.
- A failed test stops the pipeline before anything is built or deployed.
- Deploy takes about 4 minutes end to end. Bot, Postgres and Caddy restart with a short gap
  (`Recreate`); the website rolls.
- Rollback: revert the commit on `main` (a new deploy), or `helm rollback` from a machine with the
  kubeconfig.

### 8.3 Tests and lint

- `tests/`: 163 test files, 2,184 tests passing and 12 skipped on 2026-11-10. They run without a
  database (fake sessions and compiled-SQL checks).
- `ruff check .` is a local check, not a CI gate. The repository carries a baseline of 561
  findings; the working rule is that a change must not add to it.

### 8.4 The other workflows (222 files in `.github/workflows/`)

All but two are started by hand (`workflow_dispatch`) and reach the cluster with `KUBECONFIG_B64`.

| Group | Count | Purpose |
| --- | --- | --- |
| `diagnose-*` | 176 | Read-only questions to production: database counts, pod logs, a source's behaviour. Results are read from the run's log. This is how production is inspected, since nobody works on the server directly. |
| `check-*` | 14 | Spot checks (site pages, job status, notifications). |
| `fix-*`, `cleanup-*`, `rename-*` | 8 | One-off data repairs. |
| `set-*` | 5 | Put a secret into the cluster from a form, masked in the log (Bright Data API key and ISP proxy, Facebook cookies, rotating proxy pool, Takbull API key). |
| `emergency-*` | 2 | Stop a running scraper; deploy skipping hooks. |
| `watchdog-external` | 1 | **Scheduled hourly at :25.** Checks the site, bot and scraper from outside the server. |
| `offsite-backup-gdrive` | 1 | **Scheduled nightly.** Section 5.4. |
| others | 15 | Announcements, probes, a safe single test run, listing Facebook groups, and similar. |

---

## 9. Secrets and where they live

| Secret | GitHub Actions secret | In the cluster | Used by |
| --- | --- | --- | --- |
| Kubeconfig for deploys and diagnostics | `KUBECONFIG_B64` | not stored | every workflow that touches the cluster |
| Database password | `POSTGRES_PASSWORD` | `todira-postgres-secret` | all pods |
| Telegram bot token | `TELEGRAM_BOT_TOKEN` | `todira-bot-secret` | bot, scraper, website, alerts from jobs |
| Owner's Telegram id | `OWNER_TELEGRAM_USER_ID` | same | owner alerts, owner-only access |
| Session signing key | `SESSION_SECRET_KEY` | same | website, signed links from bot and scraper |
| Gemini keys | `GEMINI_API_KEY`, `GEMINI_SITE_API_KEY` | same | bot and scraper; the site assistant |
| Google sign-in | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | same | website |
| Takbull | `TAKBULL_WEBHOOK_SECRET`, `TAKBULL_API_KEY`, `TAKBULL_API_SECRET` | same | website, housekeeping job |
| Resend (email) | `RESEND_API_KEY` | same | website, scraper. Not set yet, so the morning email is off. |
| ZenRows | `ZENROWS_API_KEY` | same | scraper |
| Bright Data | `BRIGHT_DATA_API_KEY`, `BRIGHT_DATA_COLLECTOR_ID`, `BRIGHT_DATA_DESCRIPTION_FIELD` | same | scraper, website |
| AWS backup key | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | same | backup job |
| Bright Data ISP proxy | `BRIGHT_DATA_ISP_HOST/USER/PASS` (diagnostics) | added by `set-bright-data-isp-secret.yaml` | scraper |
| Rotating proxy pool | not stored | `rotating-proxy-url`, added by `set-rotating-proxy-secret.yaml` | scraper |
| Facebook cookies | not stored | added by `set-facebook-cookies-secret.yaml` | Facebook scraper |
| Off-site backup | `GDRIVE_TOKEN`, `BACKUP_PASSWORD` | not stored | off-site backup workflow |

Local development uses `.env` (template: `.env.example`) with `docker-compose.yml` (Postgres,
migrate, bot, scraper).

---

## 10. Outside services the system depends on

| Service | For | If it is down |
| --- | --- | --- |
| Telegram Bot API | The bot, every alert, messages to the owner | No alerts, no bot |
| GitHub (Actions, ghcr.io) | Deploys, diagnostics, off-site backup, watchdog | No deploys; the running system is unaffected |
| Let's Encrypt (through Caddy) | TLS certificate | Site fails once the certificate expires |
| Porkbun | DNS | Site unreachable by name |
| Google Gemini | Free-text understanding in the bot, the site assistant | Bot falls back to rules; assistant shows "not available" |
| Google OAuth | Sign-in with Google | Telegram sign-in still works |
| Takbull (and UPAY) | Payments | No new purchases |
| Resend | Email | No email (currently off anyway) |
| Bright Data | Yad2 fallback route, optional descriptions | Yad2 depends on the free route alone |
| ZenRows | Homeless fallback | Homeless depends on its free route alone |
| Webshare | Proxy pool for the Yad2 free routes | Those requests go direct |
| AWS S3 | Nightly backup | Backup fails and the owner is alerted |
| jsDelivr, Esri map tiles | The map on `/apartments` | Map shows a fallback message |

---

## 11. Things a project manager should know

1. **One server, no staging.** Every merge to `main` goes straight to users. The safety nets are
   the test suite, the import check, the migrations hook and the watchdog.
2. **Memory is tight** (2 GB for database, site, bot and a scraper that can use 1.5 GB). Most
   production incidents in `PROJECT_STATE.md` trace back to this.
3. **Yad2 is the largest source and the most fragile.** It blocks the server's address on the free
   route, so volume depends on a paid fallback and on the proxy pool (section 6.3). Roughly three
   quarters of new listings on 2026-11-09 came from Yad2.
4. **Facebook relies on one dedicated account.** Its cookies expire and the account can be
   restricted; the code pauses itself for 24 hours when it sees a login page.
5. **Production is inspected through GitHub workflows**, not by logging in. That is why there are
   176 diagnostic workflows.
6. **Text rules** apply to anything users read: no long dashes, no source names, no bot @name,
   user messages only between 09:00 and 12:00 Israel time, new bot wording approved by the owner
   first (`CLAUDE.md`).
7. **Waiting list** (owner's actions, decisions and third parties) is at the top of
   `PROJECT_STATE.md` and is the place to track open work.
