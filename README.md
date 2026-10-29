# Todira (טודירה)

Israeli apartment alerts. Users describe what they are looking for in their own words, in Telegram
([@AmirDirotBot](https://t.me/AmirDirotBot)) or on [todira.app](https://todira.app). Every new rental, sale or sublet that
matches is sent to their Telegram minutes after it goes up, and every match can be browsed on the site.

- `PROJECT_STATE.md`: decisions, history and what is open. Read its top section first.
- `RUNBOOK.md`: what to do when something is down.
- `docs/`: plans for features that are approved but not built yet.

## How it fits together

| Part | Where | What it does |
| --- | --- | --- |
| Shared package | `common/todira_common/` | DB models, filter matching, bot texts, cards, access and trial rules, shared helpers |
| Migrations | `migrations/` | Alembic migrations for the shared Postgres schema |
| Scraper | `scraper/` | CronJob, every 30 minutes from 09:00 to 22:30: fetches listings, links duplicates and reposts, sends alerts |
| Facebook scraper | `scraper/` (`Dockerfile.facebook`) | CronJob at :24, 08:00 to 22:00: reads Facebook groups in a headless browser; stops after 11 minutes |
| Bot | `bot/` | Telegram bot (polling): onboarding from free text or voice, /filter, /apartments, /liked, /hidden, /profile, /support |
| Website | `website/` | FastAPI + Jinja (`main.py`, `i18n.py` with 5 languages) plus React pages in `website/landing-react/` |
| Deploy | `charts/todira/` | Helm chart: Postgres, bot, website, Caddy (HTTPS), CronJobs (scrapers, backup, morning summary, health check) |
| CI/CD | `.github/workflows/ci-cd.yaml` | tests, per-service import check, image build to GHCR, `helm upgrade` on every push to `main` that touches app code |
| Diagnostics | `.github/workflows/diagnose-*.yaml` | read-only checks against the live cluster; print counts only, never user details |

Everything runs on a single k3s node (AWS t3.small, 2 GB). Memory is the tightest resource, so the two scrapers never run
at the same time.

Payments go through Takbull, a hosted payment page, and a webhook. A user buys a one-time pass of 7, 14 or 30 days.
There is no auto-renewal.

## Working on it

```bash
pip install -r requirements-test.txt
python -m pytest -q tests          # the full suite, no database needed
ruff check .
python .github/scripts/check_service_imports.py <service folder laid out like its Dockerfile>
```

Local run with Docker (bot and scraper):

```bash
cp .env.example .env   # fill in a test bot token
docker compose up -d postgres
docker compose run --rm migrate
docker compose up bot
docker compose run --rm scraper
```

Website on its own against a local Postgres:

```bash
alembic -c migrations/alembic.ini upgrade head
cd website && PYTHONPATH=../common uvicorn main:app --port 8000
```

After editing `website/i18n.py`, regenerate the React content with the command in `website/landing-react/README.md`,
then run `npm run build` there.

## House rules

- Merge to `main` only between scraper runs: around :46, or after 22:54. Every app-code merge deploys.
- Nothing user-facing names where listings come from.
- No secrets and no personal details in the repo, commit messages or Actions logs.
- New bot texts that users see are approved by the owner before they go live.
