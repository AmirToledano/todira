"""2026-10-14: /apartments and the bot match listings from light rows holding only MATCH_COLUMNS (listing_matches.py) —
measured live at 16-27 s per page when every candidate was loaded as a full ORM object. If matching.py starts reading a
listing attribute that isn't in MATCH_COLUMNS, every match would crash on the missing attribute; this keeps the two in
step."""
from __future__ import annotations

import re
from pathlib import Path

from todira_common.listing_matches import MATCH_COLUMNS

_MATCHING = Path(__file__).resolve().parent.parent / "common" / "todira_common" / "matching.py"


def _attributes_matching_reads() -> set[str]:
    source = _MATCHING.read_text(encoding="utf-8")
    direct = set(re.findall(r"listing_row\.([a-z_]+)", source))
    # boolean_pairs: ("require_x", "listing_attr", "label") read through getattr(listing_row, listing_attr)
    paired = set(re.findall(r'\(\s*"require_[a-z_]+",\s*"([a-z_]+)",\s*"[a-z_]+"\s*\)', source))
    return direct | paired


def test_every_listing_attribute_matching_reads_is_loaded_by_the_light_scan():
    loaded = {column.key for column in MATCH_COLUMNS}
    missing = _attributes_matching_reads() - loaded
    assert not missing, f"add these to listing_matches.MATCH_COLUMNS: {sorted(missing)}"


def test_the_light_scan_carries_what_its_callers_use():
    loaded = {column.key for column in MATCH_COLUMNS}
    assert {"id", "first_seen_at"} <= loaded
    assert "raw_payload" not in loaded and "image_urls" not in loaded  # the heavy columns stay out
