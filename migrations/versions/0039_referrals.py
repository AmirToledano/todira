"""Invite a friend: who invited whom, and the free days they earned — 2026-10-31

users.referred_by_user_id: the user whose invite link brought this one (todira_common/referrals.py). users.
referral_rewarded_at: when this user and their inviter got their free days. users.referral_days_unannounced: free days
an inviter earned that the morning message has not told them about yet. Nullable columns or a constant default: instant.

Revision ID: 0039_referrals
Revises: 0038_owner_posts
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039_referrals"
down_revision = "0038_owner_posts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("referred_by_user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_users_referred_by_user_id", "users", ["referred_by_user_id"])
    op.add_column("users", sa.Column("referral_rewarded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users", sa.Column("referral_days_unannounced", sa.Integer(), nullable=False, server_default=sa.text("0"))
    )


def downgrade() -> None:
    op.drop_column("users", "referral_days_unannounced")
    op.drop_column("users", "referral_rewarded_at")
    op.drop_index("ix_users_referred_by_user_id", table_name="users")
    op.drop_column("users", "referred_by_user_id")
