"""filters.include_missing_details — 2026-10-27

"Show also listings without rooms / size" on the site's filter: an unknown room count or size passes a rooms range or a
minimum size. A boolean with a constant default: instant on any table size.

Revision ID: 0034_filter_missing_details
Revises: 0033_activity_days
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_filter_missing_details"
down_revision = "0033_activity_days"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "filters",
        sa.Column("include_missing_details", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("filters", "include_missing_details")
