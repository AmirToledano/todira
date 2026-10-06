"""2026-10-06: ~270 Komo detail pages per run have no price (or fail to load) and were refetched EVERY run,
eating ~270 of the 300 new-detail slots. A failed id is now remembered and not retried for 24 h."""
from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"
_spec = importlib.util.spec_from_file_location("scraper_main_komo_failed", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)


@pytest.fixture
def komo(monkeypatch):
    saved = {}
    fetched = []
    state = {"failed": {}}

    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(
        scraper_main,
        "fetch_all_coordinate_ids",
        lambda **kw: [{"id": "1"}, {"id": "2"}, {"id": "3"}] if not kw else [],
    )
    monkeypatch.setattr(scraper_main, "_load_komo_failed_ids", lambda: dict(state["failed"]))
    monkeypatch.setattr(scraper_main, "_save_komo_failed_ids", lambda failed: saved.update(failed=dict(failed)))

    def _detail(modaa_num):
        fetched.append(modaa_num)
        if modaa_num == "2":
            return None  # a page with no price
        return {"id": modaa_num, "price": 5000, "city": "חיפה", "rooms": 3, "url": f"https://x/{modaa_num}"}

    monkeypatch.setattr(scraper_main, "fetch_komo_listing_detail", _detail)
    monkeypatch.setattr(
        scraper_main,
        "normalize",
        lambda detail, source, deal_type: type("N", (), {"external_id": detail["id"], "city": detail["city"]})(),
    )
    return SimpleNamespaceLike(saved=saved, fetched=fetched, state=state)


class SimpleNamespaceLike:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_a_failed_detail_is_remembered(komo):
    items, seen, fetched, errors, ok = scraper_main._scrape_komo()
    assert sorted(komo.fetched) == ["1", "2", "3"]
    assert errors == 1
    assert set(komo.saved["failed"]) == {"2"}


def test_a_recently_failed_id_is_not_fetched_again(komo):
    komo.state["failed"] = {"2": time.time() - 3600}  # failed an hour ago
    scraper_main._scrape_komo()
    assert sorted(komo.fetched) == ["1", "3"]  # the failing page was skipped, real new ones still fetched


def test_an_old_failure_is_retried_after_a_day(komo):
    komo.state["failed"] = {"2": time.time() - 25 * 3600}
    scraper_main._scrape_komo()
    assert "2" in komo.fetched


def test_forgotten_when_no_longer_on_komo(komo, monkeypatch):
    komo.state["failed"] = {"999": time.time() - 3600, "2": time.time() - 3600}  # 999 is gone from Komo
    scraper_main._scrape_komo()
    assert "999" not in komo.saved["failed"]
    assert "2" in komo.saved["failed"]
