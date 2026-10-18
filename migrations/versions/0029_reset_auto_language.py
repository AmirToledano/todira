"""Everyone back to Hebrew — 2026-10-18

Until now users.language was set automatically from the phone's language when a Telegram user first wrote to the
bot, and there was no way to change it (owner report: a friend's bot opened in English and stayed that way). Nobody
ever chose these values, so they are all reset to NULL (= Hebrew); /language now lets anyone pick a language.
A one-time UPDATE on a small table, no schema change.

Revision ID: 0029_reset_auto_language
Revises: 0028_trial_reminder_sent_at
"""
from __future__ import annotations

from alembic import op

revision = "0029_reset_auto_language"
down_revision = "0028_trial_reminder_sent_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET language = NULL WHERE language IS NOT NULL")


def downgrade() -> None:
    # The phone languages are not kept anywhere, so there is nothing to restore.
    pass
