"""reset the 'details read' marker on Yad2 ads read WITHOUT a record since the item-JSON fetcher went live — 2026-10-09

Between the first deploy of the item-JSON fetcher (about 12:00 UTC on 2026-10-09) and the fix that stops it fetching for ads that match
nobody, the notifier read ~700 Yad2 ads that nobody was going to be sent, and about one in six (and nearly all of the older sale ads)
came back as 'not the ad' — a definitive empty result that set details_fetched_at but stored no description. Those rows were read
under a busy fetcher, so they are put back to 'never read': the catch-up asks again, and an ad that really has no record is simply
marked read again. Bounded to ads read since that deploy and still without a description; nothing else is touched.

Revision ID: 0024_reset_empty_detail_reads
Revises: 0023_listing_details_fetched_at
"""
from __future__ import annotations

from alembic import op

revision = "0024_reset_empty_detail_reads"
down_revision = "0023_listing_details_fetched_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE listings SET details_fetched_at = NULL "
        "WHERE source = 'yad2' AND description IS NULL AND details_fetched_at >= TIMESTAMPTZ '2026-10-09 11:00:00+00'"
    )


def downgrade() -> None:
    pass
