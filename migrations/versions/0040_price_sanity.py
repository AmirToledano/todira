"""Ads whose price fits the other deal type, or no monthly rent: fix the stored ones — 2026-11-01

The same rules todira_common/price_sanity.py applies to every ad from now on (see its docstring for what was measured),
applied once to the ads already stored. Data only; nothing to undo on downgrade (the next scrape of a still-live ad would
apply the rules again anyway).

Revision ID: 0040_price_sanity
Revises: 0039_referrals
"""
from __future__ import annotations

from alembic import op

revision = "0040_price_sanity"
down_revision = "0039_referrals"
branch_labels = None
depends_on = None

_TEXT = "('facebook_groups', 'facebook_marketplace')"


def upgrade() -> None:
    op.execute("UPDATE listings SET deal_type = 'sale' WHERE deal_type = 'rent' AND price >= 200000")
    op.execute(f"UPDATE listings SET price = NULL WHERE deal_type = 'rent' AND source IN {_TEXT} AND price > 40000")
    op.execute("UPDATE listings SET price = NULL WHERE deal_type = 'rent' AND price < 300")
    op.execute(
        f"UPDATE listings SET deal_type = 'rent' WHERE deal_type = 'sale' AND source IN {_TEXT}"
        " AND price >= 1000 AND price < 30000"
    )
    op.execute("UPDATE listings SET price = NULL WHERE deal_type = 'sale' AND price < 20000")


def downgrade() -> None:
    pass
