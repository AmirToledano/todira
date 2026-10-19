"""users.trial_gift_emailed_at — 2026-10-19

When the one "7 more days" email (website/announce_trial_extension_email.py) reached a Google-only user, so a second
run never emails anyone twice. A nullable column with no default: instant on any table size.

Revision ID: 0032_trial_gift_emailed_at
Revises: 0031_trial_until_26_10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_trial_gift_emailed_at"
down_revision = "0031_trial_until_26_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("trial_gift_emailed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "trial_gift_emailed_at")
