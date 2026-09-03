"""add users.google_sub — links an existing Telegram/WhatsApp user to a Google account for a
persistent website login (see website/main.py's /auth/google/callback)

Revision ID: 0005_google_sub
Revises: 0004_contact_message_source
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_google_sub"
down_revision = "0004_contact_message_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_sub", sa.Text(), nullable=True))
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_column("users", "google_sub")
