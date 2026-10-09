"""listings.details_fetched_at — 2026-10-09

When a listing's full detail record (description, total floors, entrance date, amenities) was last read from its source.
NULL = never. Lets the Yad2 backfill pick only listings that still need a fetch and stop re-asking about ones that were
already answered (including ads Yad2 says are gone or that state nothing). Yad2 rows that already carry a description
got their details earlier (Gemini / Bright Data), so they are marked as fetched here.

Revision ID: 0023_listing_details_fetched_at
Revises: 0022_renewal_reminder
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_listing_details_fetched_at"
down_revision = "0022_renewal_reminder"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("details_fetched_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE listings SET details_fetched_at = now() WHERE source = 'yad2' AND description IS NOT NULL")


def downgrade() -> None:
    op.drop_column("listings", "details_fetched_at")
