"""add duplicate_of_id to listings — cross-source dedup (2026-09-13)

The same real-world apartment posted on more than one source (Yad2 + Komo, say) used to create a
fully separate `listings` row per source, each independently matched/notified. This column lets
scraper/dedup.find_duplicate_listing flag a newly-inserted row as a duplicate of an existing
OTHER-source row — see common/dorin_common/models.py's Listing.duplicate_of_id docstring for the
full reasoning, matching heuristic pointer, and the one known gap this doesn't solve (a duplicate
row isn't promoted back to canonical if its canonical sibling later gets delisted).

Self-referential FK (listings.id -> listings.id) with ondelete="SET NULL" — deleting a canonical
row (this project never actually deletes listings today, only soft-deletes via is_delisted, but
the FK should still degrade safely rather than block/cascade-delete every duplicate if that ever
changes) just clears the pointer rather than taking the duplicate row down with it.

Revision ID: 0011_listing_dedup
Revises: 0010_whatsapp_notif_optin
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_listing_dedup"
down_revision = "0010_whatsapp_notif_optin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "listings",
        sa.Column(
            "duplicate_of_id",
            sa.BigInteger(),
            sa.ForeignKey("listings.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_listings_duplicate_of_id", "listings", ["duplicate_of_id"])


def downgrade() -> None:
    op.drop_index("ix_listings_duplicate_of_id", table_name="listings")
    op.drop_column("listings", "duplicate_of_id")
