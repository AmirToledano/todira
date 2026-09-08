"""add whatsapp_notifications_opted_in to users — 2026-09-08 proactive WhatsApp notification
feature

Explicit opt-in for proactive WhatsApp Message Template pushes, separate from the existing
(Telegram-only) notifications_enabled column. Defaults to False for every existing row — see
common/dorin_common/models.py's User.whatsapp_notifications_opted_in docstring for why this can't
just reuse notifications_enabled or default to True.

Revision ID: 0010_whatsapp_notifications_optin
Revises: 0009_pending_google_links
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_whatsapp_notifications_optin"
down_revision = "0009_pending_google_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "whatsapp_notifications_opted_in",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "whatsapp_notifications_opted_in")
