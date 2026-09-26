"""users.google_email — 2026-09-26

Real owner request: /account shows which channels (Telegram/WhatsApp/Google) are linked, but not
WHICH identity for each — a user with several channels linked couldn't tell them apart. google_sub
is an opaque OIDC subject id, not human-readable, so this is a new column rather than reusing it;
whatsapp_phone_number/telegram_username already exist and needed no schema change.

Revision ID: 0015_google_email
Revises: 0014_listing_price_history
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_google_email"
down_revision = "0014_listing_price_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_email", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "google_email")
