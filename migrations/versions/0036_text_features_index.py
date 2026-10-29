"""Partial index for the scraper's text-features step — 2026-10-29

Measured live: the step's query ("live ads with a description not read yet, newest first") walked the whole first_seen_at
index backwards, filtering out ~190,000 rows and reading ~1 GB from disk, 39 s each run, to find a handful of rows. This
index holds only the unread ones, so the query reads just those. Its condition is written exactly as SQLAlchemy writes
the query's ("is_delisted IS false"): Postgres uses a partial index only when it can match the two. Built CONCURRENTLY: the
scrapers keep writing meanwhile.

Revision ID: 0036_text_features_index
Revises: 0035_listing_reposted_from_at
"""
from __future__ import annotations

from alembic import op

revision = "0036_text_features_index"
down_revision = "0035_listing_reposted_from_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_listings_text_unparsed ON listings (first_seen_at) "
            "WHERE text_parsed_at IS NULL AND description IS NOT NULL AND is_delisted IS false AND duplicate_of_id IS NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_listings_text_unparsed")
