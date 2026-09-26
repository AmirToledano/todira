"""users.language — 2026-09-26

Real owner request: both bots (Telegram + WhatsApp) were Hebrew-only, including Gemini's own
generated replies, not just canned strings. See todira_common/language.py's own docstring for the
full reasoning (Telegram auto-detects from telegram.User.language_code; WhatsApp asks explicitly,
via a new language-picker flow in website/whatsapp_webhook.py).

Revision ID: 0016_user_language
Revises: 0015_google_email
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_user_language"
down_revision = "0015_google_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("language", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "language")
