"""listings.reposted_from_at — 2026-10-27

The "posted again" tag: when the same flat was first seen in an earlier, removed ad of the same site
(scraper/dedup.py mark_reposts). A nullable column with no default: instant on any table size.

Revision ID: 0035_listing_reposted_from_at
Revises: 0034_filter_missing_details
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_listing_reposted_from_at"
down_revision = "0034_filter_missing_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("reposted_from_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "reposted_from_at")
