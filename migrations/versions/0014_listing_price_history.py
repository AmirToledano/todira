"""listing price-change tracking for the /apartments card's price-drop/increase badge — 2026-09-24

Real owner request, comparing directly against dorin.app's own card (a struck-through previous
price + a colored percentage badge next to the current one). scraper/main.py's _upsert_listings
already DETECTS a price change on every scrape run (price_change_events, feeding the Telegram
re-notification) but never persisted the old value anywhere — it was simply overwritten by the
UPDATE in the same statement, so there was nothing left to show on the website after the fact.
previous_price/price_changed_at are set (see _upsert_listings' own updated docstring) at the same
moment a price change is detected, so this is the LAST price change only, not a full history table
— enough for a "-5%" badge, not a full price-history chart (nothing in this project asks for one).

Revision ID: 0014_listing_price_history
Revises: 0013_listing_coords
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_listing_price_history"
down_revision = "0013_listing_coords"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("previous_price", sa.Integer(), nullable=True))
    op.add_column(
        "listings", sa.Column("price_changed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("listings", "price_changed_at")
    op.drop_column("listings", "previous_price")
