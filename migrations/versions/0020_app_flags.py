"""app_flags — 2026-10-02

A tiny key/value table for process-wide switches shared by the website and scraper pods. First use:
the "whatsapp_paused" circuit breaker (todira_common/whatsapp_guard.py) that stops every proactive
WhatsApp send as soon as Meta reports anything billable.

Revision ID: 0020_app_flags
Revises: 0019_whatsapp_window
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_app_flags"
down_revision = "0019_whatsapp_window"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_flags",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("app_flags")
