"""add users.channel_link_code / channel_link_code_expires_at — 2026-09-05 channel unification

Backs the cross-channel account-linking flow: a short code generated on the website for an
already-logged-in user, then sent from a NEW channel (WhatsApp text message, or a Telegram
/start deep-link payload) to attach that channel to the SAME row instead of creating a new one.
See common/dorin_common/channel_link.py.

Revision ID: 0007_channel_link_code
Revises: 0006_paid_access
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_channel_link_code"
down_revision = "0006_paid_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("channel_link_code", sa.Text(), nullable=True))
    op.create_index(
        "ix_users_channel_link_code", "users", ["channel_link_code"], unique=True
    )
    op.add_column(
        "users",
        sa.Column("channel_link_code_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "channel_link_code_expires_at")
    op.drop_index("ix_users_channel_link_code", table_name="users")
    op.drop_column("users", "channel_link_code")
