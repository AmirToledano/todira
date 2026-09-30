"""listings.first_seen_at — 2026-10-01

scraped_at is refreshed on every re-scrape (a deliberate 2026-09-25 fix so the delisting grace
period measures "last confirmed still active"), which left the schema with NO "when did we first see
this listing" timestamp. Two things quietly depended on scraped_at meaning that:

- scraper/main.py's _find_unnotified_recent_listings — the "never notified, last 7 days" retry net —
  silently widened to every still-active listing, so a filter edit that recorded no SentNotification
  rows could trigger cards for months-old listings on the next run.
- every "newest first" ordering (bot /apartments, website /apartments, onboarding matches) sorted by
  it, and every listing seen in the same run shares one identical timestamp, so that order was
  effectively arbitrary.

first_seen_at is set once, on INSERT (server default now()), and never updated.

Backfill: the true first-seen time of an existing row is unknowable (scraped_at is refreshed,
posted_at is often NULL), so existing rows get LEAST(COALESCE(posted_at, scraped_at), now() - 8 days)
— deliberately OUTSIDE the 7-day retry window, so this migration can never cause a flood of old
listings on the next run. The cost: a listing that really was first seen in the last 7 days and whose
first send failed loses its retry safety net once. Ties among backfilled rows are broken by id (ids
are sequential, so id order is insertion order).

Revision ID: 0018_listing_first_seen_at
Revises: 0017_filter_map_region
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_listing_first_seen_at"
down_revision = "0017_filter_map_region"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE listings SET first_seen_at = "
        "LEAST(COALESCE(posted_at, scraped_at), now() - interval '8 days')"
    )
    op.alter_column(
        "listings", "first_seen_at", nullable=False, server_default=sa.text("now()")
    )
    op.create_index("ix_listings_first_seen_at", "listings", ["first_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_listings_first_seen_at", table_name="listings")
    op.drop_column("listings", "first_seen_at")
