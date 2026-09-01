"""add contact_messages.source (distinguishes website /contact from the bot's contact fallback)

Revision ID: 0004_contact_message_source
Revises: 0003_whatsapp_users
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_contact_message_source"
down_revision = "0003_whatsapp_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contact_messages", sa.Column("source", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("contact_messages", "source")
