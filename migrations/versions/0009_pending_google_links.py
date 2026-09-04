"""add pending_google_links table — 2026-09-05 cross-browser-context Google linking

Lets a pending Google sign-in (one with no home yet — no google_sub match, no ?uid= in flight, no
active session) complete the link entirely server-side the moment the visitor does /start with a
matching token, instead of relying on a session cookie surviving the round-trip through Telegram's
own in-app browser — a separate cookie jar from whatever browser/app the sign-in started in. See
common/dorin_common/models.py's PendingGoogleLink docstring and google_link.py for the mechanism.

Revision ID: 0009_pending_google_links
Revises: 0008_payments
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_pending_google_links"
down_revision = "0008_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_google_links",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("google_sub", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_pending_google_links_token", "pending_google_links", ["token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_pending_google_links_token", table_name="pending_google_links")
    op.drop_table("pending_google_links")
