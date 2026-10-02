"""users.whatsapp_last_inbound_at / whatsapp_checkin_sent_at — 2026-10-02

Zero-cost WhatsApp: free-form messages are free only inside 24h of the user's last inbound message,
so the bot has to know when that was. Both columns are nullable with no backfill: NULL means "window
closed", which is the correct, conservative state for every existing row (nothing is sent until the
user next writes or taps a button).

Revision ID: 0019_whatsapp_window
Revises: 0018_listing_first_seen_at
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_whatsapp_window"
down_revision = "0018_listing_first_seen_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("whatsapp_last_inbound_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("whatsapp_checkin_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "whatsapp_checkin_sent_at")
    op.drop_column("users", "whatsapp_last_inbound_at")
