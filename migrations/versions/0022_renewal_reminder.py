"""users.renewal_reminder_for — 2026-10-05

The paid_until value a "your access ends soon" reminder was already sent for, so each paid period is
reminded about exactly once and a renewal (new paid_until) re-arms it. Nullable, no backfill.

Revision ID: 0022_renewal_reminder
Revises: 0021_listing_move_in_note
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_renewal_reminder"
down_revision = "0021_listing_move_in_note"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("renewal_reminder_for", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "renewal_reminder_for")
