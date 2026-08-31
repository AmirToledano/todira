"""add whatsapp support to users: whatsapp_phone_number, pending_onboarding_state; telegram_user_id
now optional

Users were hard-wired to Telegram (telegram_user_id NOT NULL UNIQUE) — a WhatsApp-onboarded
user has no Telegram ID at all, so that column has to become optional. whatsapp_phone_number
mirrors it: unique, nullable (a Telegram-only user has none). Deliberately no CHECK constraint
requiring at least one of the two — application code (dorin_common/users.py) is the single place
that creates User rows and always sets exactly one, keeping the schema simple.

pending_onboarding_state (JSONB, nullable) persists an in-progress free-text onboarding
conversation's collected fields (deal_type/cities/rooms/price/keywords so far) across webhook
calls — website/whatsapp_webhook.py is stateless between requests (unlike the Telegram bot's
long-lived process with PicklePersistence-backed context.user_data), so a multi-turn
onboarding needs *some* place to remember what was already said. Cleared once a Filter is
created. Only WhatsApp uses this for now; the Telegram bot keeps its existing mechanism.

Revision ID: 0003_whatsapp_users
Revises: 0002_add_contact_messages
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_whatsapp_users"
down_revision = "0002_add_contact_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "telegram_user_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column("users", sa.Column("whatsapp_phone_number", sa.Text(), nullable=True))
    op.create_index(
        "ix_users_whatsapp_phone_number", "users", ["whatsapp_phone_number"], unique=True
    )
    op.add_column(
        "users", sa.Column("pending_onboarding_state", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "pending_onboarding_state")
    op.drop_index("ix_users_whatsapp_phone_number", table_name="users")
    op.drop_column("users", "whatsapp_phone_number")
    op.alter_column("users", "telegram_user_id", existing_type=sa.BigInteger(), nullable=False)
