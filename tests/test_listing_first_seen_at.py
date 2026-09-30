"""listings.first_seen_at (migration 0018): the column exists with a server default, and the
migration backfills existing rows OUTSIDE the 7-day retry window so it cannot cause a flood of old
listings on the next scraper run."""
from __future__ import annotations

import re
from pathlib import Path

from todira_common.models import Listing

_MIGRATION = Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0018_listing_first_seen_at.py"


def test_model_column_is_not_null_with_a_server_default_and_an_index():
    column = Listing.__table__.c.first_seen_at
    assert column.nullable is False
    assert column.server_default is not None
    assert column.index is True


def test_migration_backfills_existing_rows_outside_the_seven_day_retry_window():
    source = _MIGRATION.read_text()
    match = re.search(r"now\(\) - interval '(\d+) days'", source)
    assert match is not None
    assert int(match.group(1)) > 7


def test_migration_chains_onto_the_previous_revision():
    source = _MIGRATION.read_text()
    assert 'down_revision = "0017_filter_map_region"' in source
    assert 'revision = "0018_listing_first_seen_at"' in source
