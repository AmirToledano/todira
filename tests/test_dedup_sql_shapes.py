"""2026-10-29: a code-review edit replaced the same-site duplicate SQL with the "posted again" UPDATE (both names end in
_REPOSTS_SQL), so linking duplicates failed on every run. Each statement must keep its own shape."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("dedup_sql_shapes", Path(__file__).resolve().parent.parent / "scraper" / "dedup.py")
dedup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dedup)


def test_same_site_duplicates_is_a_select_of_pairs():
    sql = dedup._SAME_SITE_REPOSTS_SQL
    assert "SELECT id, root_id FROM g" in sql and "UPDATE" not in sql


def test_posted_again_is_an_update_of_recent_ads_only():
    sql = dedup._REPOSTS_SQL
    assert sql.strip().startswith("WITH n AS") and "UPDATE listings l SET reposted_from_at" in sql
    assert "interval '3 days'" in sql
