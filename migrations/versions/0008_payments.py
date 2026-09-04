"""add payments table — 2026-09-05 real payment-gateway readiness

Tracks a real payment attempt through a gateway (Grow/Meshulam) end to end: created "pending" the
moment a user picks a plan, flipped to "paid" only by the gateway's own webhook confirming a real
charge. Also doubles as the record for the earlier informal click-trust model (gateway=NULL) when
Grow isn't configured yet — see common/dorin_common/models.py's Payment docstring and
website/main.py's /upgrade for how the two coexist.

Revision ID: 0008_payments
Revises: 0007_channel_link_code
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_payments"
down_revision = "0007_channel_link_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("amount_ils", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("gateway", sa.Text(), nullable=True),
        sa.Column("gateway_transaction_id", sa.Text(), nullable=True),
        sa.Column("webhook_token", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index(
        "ix_payments_gateway_transaction_id",
        "payments",
        ["gateway_transaction_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_payments_gateway_transaction_id", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_table("payments")
