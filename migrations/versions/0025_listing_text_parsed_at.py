"""listings.text_parsed_at — 2026-10-09

When the listing's description text was last read for floors, amenities, property type and entry date
(todira_common/text_features.py). NULL = not read yet. Lets the catch-up at the end of each scraper run pick only
listings it has not read, instead of reading the same 100,000 descriptions every hour.

Revision ID: 0025_listing_text_parsed_at
Revises: 0024_reset_empty_detail_reads
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_listing_text_parsed_at"
down_revision = "0024_reset_empty_detail_reads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("text_parsed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "text_parsed_at")
