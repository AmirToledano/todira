"""Everyone registered before the change: free access until 26.10 at 10:00 — 2026-10-19

Owner clarification of 0030: rather than "+7 days on whatever each trial was", every account that existed before the
change gets 7 days counted from the morning the announcement goes out (19.10 10:00 Israel time), i.e. until 26.10
10:00 Israel time (07:00 UTC) - including people whose 3-day trial had already ended. New accounts keep the 10-day
default from 0030. A trial already running later than that is never shortened, and the owner's payment-test account
is left as it is (as in 0030). The trial-ends-tomorrow reminder is cleared again so it comes before the new date.

Revision ID: 0031_trial_until_26_10
Revises: 0030_ten_day_trial
"""
from __future__ import annotations

from alembic import op

revision = "0031_trial_until_26_10"
down_revision = "0030_ten_day_trial"
branch_labels = None
depends_on = None

NEW_END = "TIMESTAMPTZ '2026-10-26 07:00:00+00'"


def upgrade() -> None:
    op.execute(
        f"UPDATE users SET trial_ends_at = {NEW_END}, trial_reminder_sent_at = NULL "
        "WHERE created_at < TIMESTAMPTZ '2026-10-19 00:00:00+00' "
        f"AND (trial_ends_at IS NULL OR trial_ends_at < {NEW_END}) "
        "AND id NOT IN (SELECT user_id FROM payments WHERE plan = 'pass_test')"
    )


def downgrade() -> None:
    pass
