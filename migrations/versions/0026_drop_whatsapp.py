"""Drop the WhatsApp channel's data — 2026-10-13

The owner removed WhatsApp from the project entirely (only Telegram and the website remain); the code stopped using
these columns in the previous deploy, so dropping them now can't break a running pod. Checked live first
(diagnose-all-users-overview, counts only): every user row has Telegram, so no account is left without a way in. The
downgrade restores the columns empty — the phone numbers themselves are gone.

Revision ID: 0026_drop_whatsapp
Revises: 0025_listing_text_parsed_at
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026_drop_whatsapp"
down_revision = "0025_listing_text_parsed_at"
branch_labels = None
depends_on = None

_COLUMNS = (
    "whatsapp_phone_number",  # its unique index goes with it
    "whatsapp_notifications_opted_in",
    "whatsapp_last_inbound_at",
    "whatsapp_checkin_sent_at",
    "pending_onboarding_state",
)


def upgrade() -> None:
    for column in _COLUMNS:
        op.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {column}")
    op.execute("DELETE FROM app_flags WHERE key LIKE 'whatsapp%'")


def downgrade() -> None:
    op.add_column("users", sa.Column("pending_onboarding_state", postgresql.JSONB(), nullable=True))
    op.add_column("users", sa.Column("whatsapp_checkin_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("whatsapp_last_inbound_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("whatsapp_notifications_opted_in", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("users", sa.Column("whatsapp_phone_number", sa.Text(), nullable=True))
    op.create_index("ix_users_whatsapp_phone_number", "users", ["whatsapp_phone_number"], unique=True)
