"""Alert hours and days per person, alerts held outside them, and the morning check-in — 2026-10-31

users.alert_from_hour / alert_to_hour: the hours a person wants alerts in (Israel time, from inclusive, to exclusive);
NULL = every hour we scan. users.alerts_on_weekend: false = no alerts on Friday and Saturday. held_alerts: matches that
came while a person's hours were closed, sent when they open (scraper/notifier.py). users.checkin_sent_at: when the
"is the search still right?" message last went out (scraper/checkin.py). Nullable columns or a constant default: instant.

Revision ID: 0037_alert_hours_and_checkin
Revises: 0036_text_features_index
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037_alert_hours_and_checkin"
down_revision = "0036_text_features_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("alert_from_hour", sa.SmallInteger(), nullable=True))
    op.add_column("users", sa.Column("alert_to_hour", sa.SmallInteger(), nullable=True))
    op.add_column(
        "users", sa.Column("alerts_on_weekend", sa.Boolean(), nullable=False, server_default=sa.text("true"))
    )
    op.add_column("users", sa.Column("checkin_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "held_alerts",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("listing_id", sa.BigInteger(), sa.ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_held_alerts_listing_id", "held_alerts", ["listing_id"])


def downgrade() -> None:
    op.drop_index("ix_held_alerts_listing_id", table_name="held_alerts")
    op.drop_table("held_alerts")
    op.drop_column("users", "checkin_sent_at")
    op.drop_column("users", "alerts_on_weekend")
    op.drop_column("users", "alert_to_hour")
    op.drop_column("users", "alert_from_hour")
