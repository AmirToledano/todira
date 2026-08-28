# DirAmir

A self-hosted Telegram bot that scrapes apartment listings (starting with Yad2) and notifies you
when one matches your saved filter — a personal replacement for the paid "Dorin" bot (dorin.app).

Full design/roadmap: see the plan at
`C:\Users\AmirT\.claude\plans\majestic-mapping-diffie.md` (Phase 1 = this repo's current scope:
scraper + bot + k8s deploy, Telegram-only, Yad2-only. Phase 2 = public website. Phase 3 = more
scraping sources.)

## Project layout

- `common/dorin_common/` — shared package: DB models, Pydantic schemas, enums, and the pure
  filter-matching function. Imported by both `scraper` and `bot`.
- `migrations/` — Alembic migrations for the shared Postgres schema.
- `scraper/` — one-shot job: fetch Yad2 listings, upsert into Postgres, match against active
  filters, send Telegram notifications for new matches. Run periodically via a k8s CronJob.
- `bot/` — long-running Telegram bot (polling mode): `/start`, `/filter`, `/apartments`,
  `/liked`, `/profile`.
- `charts/diramir/` — Helm chart deploying Postgres, the bot, and the scraper CronJob.
- `.github/workflows/` — CI/CD: build+push images to GHCR, `helm upgrade` to the cluster.

## Local development

```bash
cp .env.example .env   # then fill in TELEGRAM_BOT_TOKEN with a real test bot token
docker compose up -d postgres
docker compose run --rm migrate
docker compose up bot
docker compose run --rm scraper   # on demand — no built-in scheduler in compose
```

See the plan's Section 9 for the full manual verification checklist.
