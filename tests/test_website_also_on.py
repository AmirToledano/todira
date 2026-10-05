"""2026-10-05: the listing detail view says where ELSE the same apartment was posted (main.py's
_attach_also_on), from the cross-source duplicate links the scraper already records."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
sys.path.insert(0, str(_WEBSITE_DIR))
_spec = importlib.util.spec_from_file_location("website_main_also_on", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _query):
        return SimpleNamespace(all=lambda: self._rows)


def _listing(listing_id, source, duplicate_of_id=None):
    return SimpleNamespace(id=listing_id, source=source, duplicate_of_id=duplicate_of_id)


def test_canonical_listing_lists_its_duplicates_as_other_sites():
    canonical = _listing(1, "yad2")
    session = _FakeSession([(1, "yad2", None), (7, "komo", 1), (9, "homeless", 1)])
    website_main._attach_also_on(session, [canonical], "he")
    assert canonical.also_on == [{"n": "קומו", "u": "/go/7"}, {"n": "הומלס", "u": "/go/9"}]


def test_a_duplicate_row_points_at_the_canonical_and_its_siblings_not_itself():
    dup = _listing(7, "komo", duplicate_of_id=1)
    session = _FakeSession([(1, "yad2", None), (7, "komo", 1), (9, "homeless", 1)])
    website_main._attach_also_on(session, [dup], "en")
    assert dup.also_on == [{"n": "Yad2", "u": "/go/1"}, {"n": "Homeless", "u": "/go/9"}]


def test_unique_listing_and_missing_listing_get_nothing():
    solo = _listing(5, "yad2")
    session = _FakeSession([(5, "yad2", None)])
    website_main._attach_also_on(session, [solo, None], "he")
    assert solo.also_on == []


def test_one_entry_per_other_source():
    canonical = _listing(1, "yad2")
    session = _FakeSession([(1, "yad2", None), (7, "komo", 1), (8, "komo", 1)])
    website_main._attach_also_on(session, [canonical], "he")
    assert canonical.also_on == [{"n": "קומו", "u": "/go/7"}]
