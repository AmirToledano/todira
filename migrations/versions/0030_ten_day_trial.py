"""Ten-day free trial — 2026-10-18

Owner decision: the free trial goes from 3 days to 10. New users get 10 days from sign-up (the column default), and
everyone already registered gets 7 more days on top of the trial they had, whether it is still running or already
ended (except the owner's payment-test account). The one "your trial ends tomorrow" reminder (scraper/renewal_reminder.py) is cleared for everyone whose trial
is running again, so it is sent before the new end date instead of having been spent on the old one.
Instant on any table size: a default change and two UPDATEs on users.

Revision ID: 0030_ten_day_trial
Revises: 0029_reset_auto_language
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_ten_day_trial"
down_revision = "0029_reset_auto_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "trial_ends_at", server_default=sa.text("now() + interval '10 days'"))
    # The owner's payment-test account (it holds a NIS 1 test pass, plan "pass_test") had its access ended on purpose
    # for the next payment test; it is left as it is.
    op.execute(
        "UPDATE users SET trial_ends_at = trial_ends_at + interval '7 days' "
        "WHERE trial_ends_at IS NOT NULL AND id NOT IN (SELECT user_id FROM payments WHERE plan = 'pass_test')"
    )
    op.execute("UPDATE users SET trial_reminder_sent_at = NULL WHERE trial_ends_at > now()")


def downgrade() -> None:
    op.alter_column("users", "trial_ends_at", server_default=sa.text("now() + interval '3 days'"))
