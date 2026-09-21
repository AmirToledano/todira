"""recurring subscription billing — 2026-09-21

Adds what's needed for the ₪49.90/month auto-renewing subscription (replacing the earlier
weekly/biweekly/monthly one-time plans, see common/todira_common/access.py's PLAN_PRICES_ILS):

- users.cancel_at_period_end: the user asked to stop auto-renewing, but keeps access until
  paid_until (already-charged time isn't clawed back) — same semantics as any standard SaaS
  cancellation. Checked by scraper's daily housekeeping alongside has_full_access.
- users.takbull_subscription_uniqid: Takbull's own uniqId for this user's active recurring order
  (returned when the subscription is created, DealType=4 — see website/takbull_client.py) — needed
  to call Takbull's CancelSubscription API when the user cancels.
- payments.subscription_uniqid: mirrors the same uniqId onto every Payment row belonging to that
  subscription (the initial charge AND each renewal) — lets the webhook recognize a RENEWAL charge
  (IsSubscriptionPayment=true, order_reference pointing at an already-"paid" row) as legitimate
  rather than an attempted double-credit, since Payment's existing gateway_transaction_id
  uniqueness constraint alone can't distinguish "new renewal cycle" from "same request replayed"
  without also knowing which subscription it belongs to.
- payments.amount_ils: Integer -> Numeric(10, 2). Every plan priced so far has been a whole number
  of shekels (₪1/₪15/₪25/₪40) but ₪49.90 isn't — see website/main.py's Takbull-webhook amount
  cross-check, updated in the same change to parse OrderTotalSum as Decimal instead of int()
  (int("49.90") raises ValueError, which the existing code already treats as "leave pending", so
  every real recurring charge would have silently gone uncredited under the old Integer column).

Revision ID: 0012_subscription_billing
Revises: 0011_listing_dedup
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_subscription_billing"
down_revision = "0011_listing_dedup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "cancel_at_period_end", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.add_column("users", sa.Column("takbull_subscription_uniqid", sa.Text(), nullable=True))
    op.add_column("payments", sa.Column("subscription_uniqid", sa.Text(), nullable=True))
    op.alter_column(
        "payments",
        "amount_ils",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        postgresql_using="amount_ils::numeric(10,2)",
    )


def downgrade() -> None:
    op.alter_column(
        "payments",
        "amount_ils",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        postgresql_using="round(amount_ils)::integer",
    )
    op.drop_column("payments", "subscription_uniqid")
    op.drop_column("users", "takbull_subscription_uniqid")
    op.drop_column("users", "cancel_at_period_end")
