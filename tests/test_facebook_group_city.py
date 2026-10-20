"""2026-10-20 (owner: "as many flats as possible, with great care"): a group post that names no city takes its group's
city, only when the group's earlier posts agree on one city."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"
_spec = importlib.util.spec_from_file_location("scraper_main_group_city", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)


def _url(group_id: str, post_id: int) -> str:
    return f"https://www.facebook.com/groups/{group_id}/posts/{post_id}/"


def test_a_group_whose_posts_agree_gives_its_city():
    rows = [(_url("111", n), "חיפה") for n in range(6)]
    assert scraper_main._dominant_group_cities(rows) == {"111": "חיפה"}


def test_a_mixed_group_gives_nothing():
    rows = [(_url("222", n), "תל אביב יפו") for n in range(5)] + [(_url("222", 9), "רמת גן"), (_url("222", 10), "גבעתיים")]
    assert scraper_main._dominant_group_cities(rows) == {}  # 5 of 7 is under 85%


def test_too_few_posts_give_nothing():
    rows = [(_url("333", n), "ירושלים") for n in range(5)]
    assert scraper_main._dominant_group_cities(rows) == {}


def test_one_odd_post_in_a_big_group_still_counts():
    rows = [(_url("444", n), "באר שבע") for n in range(12)] + [(_url("444", 99), "עומר")]
    assert scraper_main._dominant_group_cities(rows) == {"444": "באר שבע"}  # 12 of 13


def test_rows_without_a_group_link_or_city_are_ignored():
    rows = [("https://www.facebook.com/marketplace/item/1/", "חיפה"), (_url("555", 1), None), (None, "חיפה")]
    assert scraper_main._dominant_group_cities(rows) == {}


def test_the_feed_reads_deeper_now():
    values = (Path(__file__).resolve().parent.parent / "charts" / "todira" / "values.yaml").read_text()
    assert "    scrolls: 24\n" in values
