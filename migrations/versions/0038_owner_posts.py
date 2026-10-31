"""owner_posts and owner_post_photos: flats owners post for free on the site — 2026-10-31

The owner approved free posting for owners: a form on the site, every ad checked by the owner before it goes up, and the
poster's phone shown only to people with access (website/owner_posts.py). An approved post becomes a Listing with
source "owner"; its photos are kept here, already resized, and served by the site.

Revision ID: 0038_owner_posts
Revises: 0037_alert_hours_and_checkin
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038_owner_posts"
down_revision = "0037_alert_hours_and_checkin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owner_posts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("street", sa.Text(), nullable=True),
        sa.Column("rooms", sa.Numeric(3, 1), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("size_sqm", sa.Integer(), nullable=True),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("move_in_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("contact_name", sa.Text(), nullable=False),
        sa.Column("contact_phone", sa.Text(), nullable=False),
        sa.Column("manage_token", sa.Text(), nullable=False, unique=True),
        sa.Column("visitor", sa.Text(), nullable=True),
        sa.Column("listing_id", sa.BigInteger(), sa.ForeignKey("listings.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_owner_posts_status", "owner_posts", ["status"])
    op.create_table(
        "owner_post_photos",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("post_id", sa.BigInteger(), sa.ForeignKey("owner_posts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("jpeg", sa.LargeBinary(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("owner_post_photos")
    op.drop_index("ix_owner_posts_status", table_name="owner_posts")
    op.drop_table("owner_posts")
