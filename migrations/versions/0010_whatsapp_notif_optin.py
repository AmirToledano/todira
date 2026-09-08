"""add whatsapp_notifications_opted_in to users — 2026-09-08 proactive WhatsApp notification
feature

Explicit opt-in for proactive WhatsApp Message Template pushes, separate from the existing
(Telegram-only) notifications_enabled column. Defaults to False for every existing row — see
common/dorin_common/models.py's User.whatsapp_notifications_opted_in docstring for why this can't
just reuse notifications_enabled or default to True.

Revision id kept short deliberately (25 chars, not the full field name) — found live, the hard
way, 2026-09-08: alembic's own bookkeeping table (`alembic_version.version_num`) is a plain
VARCHAR(32), and the original id here ("0010_whatsapp_notifications_optin", 33 chars) overflowed
it — DataError: value too long for type character varying(32). Every one of this project's prior
revision ids happens to fit under 32 chars, so this had never come up before; it's worth staying
under that limit for every future one too.

Revision ID: 0010_whatsapp_notif_optin
Revises: 0009_pending_google_links
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_whatsapp_notif_optin"
down_revision = "0009_pending_google_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "whatsapp_notifications_opted_in",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "whatsapp_notifications_opted_in")
