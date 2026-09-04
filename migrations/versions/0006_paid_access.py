"""add users.trial_ends_at / paid_until / free_access_granted — 2026-09-04 pricing decision

trial_ends_at gets a real, non-default backfill for every row that already existed when this
migration runs: NOW() + 3 days, the SAME 3-day grace a brand-new signup gets going forward (via
the column's own server_default) — not an instant cutoff for existing users. New rows created
after this migration get the same 3-day-from-creation value automatically via server_default.

Revision ID: 0006_paid_access
Revises: 0005_google_sub
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_paid_access"
down_revision = "0005_google_sub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "trial_ends_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now() + interval '3 days'"),
            nullable=False,
        ),
    )
    # Explicit backfill, not left to the server_default above: every row that already existed
    # gets exactly "3 days from right now" too — the server_default only fires for rows inserted
    # AFTER this migration runs, and ADD COLUMN with a server_default backfills existing rows with
    # that same computed value at migration time anyway (Postgres evaluates it once), so this
    # UPDATE is technically redundant here — kept explicit for clarity and to not depend on that
    # Postgres behavior being obvious to a future reader.
    op.execute("UPDATE users SET trial_ends_at = now() + interval '3 days'")

    op.add_column("users", sa.Column("paid_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("free_access_granted", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "free_access_granted")
    op.drop_column("users", "paid_until")
    op.drop_column("users", "trial_ends_at")
