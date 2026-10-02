"""listings.move_in_note — 2026-10-02

Komo gives move-in as free text ("מיידית" = immediate, "גמיש" = flexible), never a date, so those
listings had no move-in information at all. The note is shown on the card only when move_in_date is
unset and is never used for filtering. Nullable, no backfill.

Revision ID: 0021_listing_move_in_note
Revises: 0020_app_flags
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_listing_move_in_note"
down_revision = "0020_app_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("move_in_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "move_in_note")
