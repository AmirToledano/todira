"""sent_notifications.listing_id index — 2026-10-14

Listings are now deleted a month after first being seen (scraper/main.py's _delete_expired_listings), and each deleted
listing cascades to its sent_notifications rows. The only index there led with user_id, so every deleted listing would
have scanned the whole table (~50,000 rows) to find its notifications. ~50k rows: built in well under a second.

Revision ID: 0027_sent_notif_listing_idx
Revises: 0026_drop_whatsapp
"""
from __future__ import annotations

from alembic import op

revision = "0027_sent_notif_listing_idx"
down_revision = "0026_drop_whatsapp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_sent_notifications_listing_id ON sent_notifications (listing_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sent_notifications_listing_id")
