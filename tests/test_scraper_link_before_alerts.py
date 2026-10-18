"""2026-10-18 (owner: the bot sent the same apartments many times). Measured live: most repeats were the same Yad2 ad
posted again under a new id, or a flat already sent from another site - linked as duplicates only after the alerts went
out. run_once now links them first, and only rows that are still nobody's duplicate are sent as new."""
from __future__ import annotations

import importlib.util
import inspect
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"
_spec = importlib.util.spec_from_file_location("scraper_main_link_first", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)


def test_duplicates_are_linked_before_the_alerts_and_linked_rows_are_not_sent():
    source = inspect.getsource(scraper_main.run_once)
    first_link = source.index("link_same_site_reposts(session)")
    assert source.index("link_missed_duplicates(session)") < first_link
    assert first_link < source.index("new_listings = (")
    assert first_link < source.index("run_notifications(")
    query = source[source.index("new_listings = ("):source.index("retry_listings = ")]
    assert "duplicate_of_id.is_(None)" in query
