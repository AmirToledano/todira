"""users.trial_reminder_sent_at — 2026-10-16

The "your free trial ends tomorrow" reminder (scraper/renewal_reminder.py) is sent once per user; this records when.
A nullable column with no default: adding it is instant on any table size.

Revision ID: 0028_trial_reminder_sent_at
Revises: 0027_sent_notif_listing_idx
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_trial_reminder_sent_at"
down_revision = "0027_sent_notif_listing_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("trial_reminder_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "trial_reminder_sent_at")
