"""activity_days — 2026-10-21

How much people use the bot and the site, one row per (Israel day, kind, person) with a hit count (see
todira_common/activity.py). A new, empty table: instant, and it touches no existing table.

Revision ID: 0033_activity_days
Revises: 0032_trial_gift_emailed_at
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_activity_days"
down_revision = "0032_trial_gift_emailed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_days",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("kind", sa.Text(), primary_key=True),
        sa.Column("who", sa.Text(), primary_key=True),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_table("activity_days")
