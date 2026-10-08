"""2026-10-08: the Yad2 tile sweep (yad2_client.fetch_region_tiles) and the one-time seed policy in scraper/main.py.

Why it exists: Yad2's map API caps a response at 200 markers, our scraper asked each district once, and a live probe showed a
5x5 grid saw 963 ads where the single request saw 200 (and for Mevaseret Zion 6 of 71). These tests pin the behaviour that
keeps the sweep safe: it splits only full pieces, spends a bounded number of requests, stops after repeated failures,
never needs the paid route, and never makes a failed sweep look like a complete one.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import yad2_client as yc

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"
_spec = importlib.util.spec_from_file_location("scraper_main_tile_sweep", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)


def _marker(token: str) -> dict:
    return {"token": token, "price": 5000, "address": {}, "additionalDetails": {}, "metaData": {}}


def _no_sleep(_seconds: float) -> None:
    return None


def _patch_fetch(monkeypatch, responses):
    """responses: callable(url) -> list | None; also records every requested url."""
    seen: list[str] = []

    def fake(url):
        seen.append(url)
        return responses(url)

    monkeypatch.setattr(yc, "_fetch_tile_markers", fake)
    return seen


def test_split_bbox_returns_four_quadrants_that_cover_the_box():
    boxes = yc._split_bbox("31.0,34.0,32.0,35.0")
    assert boxes == [
        "31.000000,34.000000,31.500000,34.500000",
        "31.000000,34.500000,31.500000,35.000000",
        "31.500000,34.000000,32.000000,34.500000",
        "31.500000,34.500000,32.000000,35.000000",
    ]


def test_a_small_region_is_one_request(monkeypatch):
    seen = _patch_fetch(monkeypatch, lambda url: [_marker("a"), _marker("b")])
    stats = yc.TileSweepStats()
    items = list(yc._sweep_tile("31,34,32,35", area=None, region=6, zoom=10, depth=0, host=None, stats=stats, sleep=_no_sleep))
    assert [i["id"] for i in items] == ["a", "b"]
    assert len(seen) == 1 and stats.requests == 1 and not stats.incomplete


def test_a_full_piece_is_split_and_zoom_grows_one_level_per_depth(monkeypatch):
    full = [_marker(f"x{i}") for i in range(yc.TILE_MARKER_CAP)]

    def responses(url):
        return full if "zoom=10" in url else [_marker(f"c{abs(hash(url)) % 10_000}")]

    seen = _patch_fetch(monkeypatch, responses)
    stats = yc.TileSweepStats()
    items = list(yc._sweep_tile("31,34,32,35", area=None, region=6, zoom=10, depth=0, host=None, stats=stats, sleep=_no_sleep))
    assert len(seen) == 5  # the root, then its four quarters
    assert sum("zoom=11" in u for u in seen) == 4
    assert len(items) == 4  # the full root's own markers are dropped in favour of the finer pieces
    assert not stats.incomplete


def test_the_request_budget_stops_the_sweep_and_marks_it_incomplete(monkeypatch):
    full = [_marker(f"x{i}") for i in range(yc.TILE_MARKER_CAP)]
    seen = _patch_fetch(monkeypatch, lambda url: full)
    stats = yc.TileSweepStats(max_requests=3)
    list(yc._sweep_tile("31,34,32,35", area=None, region=6, zoom=10, depth=0, host=None, stats=stats, sleep=_no_sleep))
    assert len(seen) == 3 and stats.budget_hit and stats.incomplete


def test_repeated_failures_abort_instead_of_hammering_the_site(monkeypatch):
    root = [_marker(f"r{i}") for i in range(yc.TILE_MARKER_CAP)]
    first_quarter = [_marker(f"q{i}") for i in range(yc.TILE_MARKER_CAP)]  # full, but different ads, so it splits further
    calls = {"n": 0}

    def responses(url):  # the root and its first quarter answer, then the site starts blocking
        calls["n"] += 1
        return root if calls["n"] == 1 else first_quarter if calls["n"] == 2 else None

    seen = _patch_fetch(monkeypatch, responses)
    stats = yc.TileSweepStats(max_requests=500)
    list(yc._sweep_tile("31,34,32,35", area=None, region=6, zoom=10, depth=0, host=None, stats=stats, sleep=_no_sleep))
    assert stats.aborted and stats.incomplete
    assert stats.failed_tiles == yc._TILE_MAX_CONSECUTIVE_FAILURES
    assert len(seen) < 20


def test_a_single_failed_tile_is_retried_once(monkeypatch):
    calls = {"n": 0}

    def responses(url):
        calls["n"] += 1
        return None if calls["n"] == 1 else [_marker("ok")]

    _patch_fetch(monkeypatch, responses)
    stats = yc.TileSweepStats()
    items = list(yc._sweep_tile("31,34,32,35", area=None, region=6, zoom=10, depth=0, host=None, stats=stats, sleep=_no_sleep))
    assert [i["id"] for i in items] == ["ok"] and stats.failed_tiles == 0 and not stats.incomplete


def test_tile_sweep_needs_both_switches(monkeypatch):
    monkeypatch.delenv("YAD2_TILE_SWEEP", raising=False)
    monkeypatch.setenv("YAD2_FREE_MAP_FETCH", "true")
    assert yc.tile_sweep_enabled() is False
    monkeypatch.setenv("YAD2_TILE_SWEEP", "true")
    assert yc.tile_sweep_enabled() is True
    monkeypatch.setenv("YAD2_FREE_MAP_FETCH", "false")  # the sweep never uses the paid route
    assert yc.tile_sweep_enabled() is False


def test_fetch_region_tiles_uses_the_regions_own_host_and_zoom(monkeypatch):
    seen = _patch_fetch(monkeypatch, lambda url: [_marker("e")])
    stats = yc.TileSweepStats()
    list(yc.fetch_region_tiles("partnership/east", stats, sleep=_no_sleep))
    assert "gw.yad-il.co.il" in seen[0] and "zoom=7" in seen[0]


def test_seed_backlog_is_only_the_ads_the_sweep_alone_found():
    rows = [(1, "a"), (2, "b"), (3, "c")]
    assert scraper_main._split_seed_backlog(rows, {"b", "c", "zzz"}) == {2, 3}
    assert scraper_main._split_seed_backlog(rows, set()) == set()


def test_a_box_the_api_ignores_stops_after_one_split_instead_of_burning_the_budget(monkeypatch):
    same = [_marker(f"x{i}") for i in range(yc.TILE_MARKER_CAP)]
    seen = _patch_fetch(monkeypatch, lambda url: same)  # every piece answers with the SAME full set
    stats = yc.TileSweepStats(max_requests=500)
    list(yc._sweep_tile("31,34,32,35", area=None, region=6, zoom=10, depth=0, host=None, stats=stats, sleep=_no_sleep))
    assert len(seen) == 5  # the root and its four quarters, then it stops
    assert stats.bbox_ignored == 4 and not stats.budget_hit


def test_the_wall_clock_cap_ends_the_sweep_as_incomplete(monkeypatch):
    full = [_marker(f"x{i}") for i in range(yc.TILE_MARKER_CAP)]
    ticks = iter(range(0, 10_000, 100))
    _patch_fetch(monkeypatch, lambda url: full)
    stats = yc.TileSweepStats(max_requests=500, max_seconds=250)
    list(yc._sweep_tile("31,34,32,35", area=None, region=6, zoom=10, depth=0, host=None, stats=stats,
                        sleep=_no_sleep, clock=lambda: next(ticks)))
    assert stats.budget_hit and stats.incomplete


def test_tiles_never_send_the_area_parameter(monkeypatch):
    seen = _patch_fetch(monkeypatch, lambda url: [_marker("e")])
    stats = yc.TileSweepStats()
    list(yc.fetch_region_tiles("tel-aviv-area", stats, sleep=_no_sleep))
    assert "area=" not in seen[0] and "region=3" in seen[0]


def test_forsale_tiles_use_the_forsale_map_and_the_same_boxes(monkeypatch):
    seen = _patch_fetch(monkeypatch, lambda url: [_marker("s1")])
    stats = yc.TileSweepStats()
    items = list(yc.fetch_region_tiles("jerusalem-area", stats, sleep=_no_sleep, kind="forsale"))
    assert [i["id"] for i in items] == ["s1"]
    assert seen and all("/realestate-feed/forsale/map?" in url for url in seen)
    assert "area=" not in seen[0]
    assert "bBox=31.549448,34.818058,31.938335,35.272844" in seen[0]


def test_rent_stays_the_default_map(monkeypatch):
    seen = _patch_fetch(monkeypatch, lambda url: [_marker("r1")])
    list(yc.fetch_region_tiles("jerusalem-area", yc.TileSweepStats(), sleep=_no_sleep))
    assert all("/realestate-feed/rent/map?" in url for url in seen)


def test_the_east_district_keeps_its_own_host_for_forsale_too(monkeypatch):
    seen = _patch_fetch(monkeypatch, lambda url: [_marker("e1")])
    list(yc.fetch_region_tiles("partnership/east", yc.TileSweepStats(), sleep=_no_sleep, kind="forsale"))
    assert seen[0].startswith("https://gw.yad-il.co.il/realestate-feed/forsale/map?")


def test_unknown_map_kind_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        yc._build_map_url("1,2,3,4", area=None, region=1, zoom=10, kind="sublet")


def test_sale_sweep_needs_its_own_switch_on_top_of_the_rent_ones(monkeypatch):
    for name in ("YAD2_TILE_SWEEP", "YAD2_FREE_MAP_FETCH", "YAD2_SALE_TILE_SWEEP"):
        monkeypatch.delenv(name, raising=False)
    assert not yc.sale_tile_sweep_enabled()
    monkeypatch.setenv("YAD2_SALE_TILE_SWEEP", "true")
    assert not yc.sale_tile_sweep_enabled()  # the rent switches are off
    monkeypatch.setenv("YAD2_TILE_SWEEP", "true")
    monkeypatch.setenv("YAD2_FREE_MAP_FETCH", "true")
    assert yc.sale_tile_sweep_enabled()
    monkeypatch.setenv("YAD2_SALE_TILE_SWEEP", "false")
    assert not yc.sale_tile_sweep_enabled() and yc.tile_sweep_enabled()


class _FakeSession:
    """Just enough of a SQLAlchemy session for _apply_tile_seed_policy: remembers flags, rows and updates."""

    def __init__(self, rows):
        self.rows = rows
        self.updated = []

    def execute(self, statement):
        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        if statement.__class__.__name__ == "Update":
            self.updated.append(statement)
            return _Result([])
        return _Result(self.rows)

    def commit(self):
        return None


def _reset_tile_state():
    for kind in scraper_main._YAD2_TILE_KINDS:
        scraper_main._YAD2_TILE_ONLY_IDS[kind].clear()
        scraper_main._YAD2_TILE_STATE[kind].update(ran=False, complete=False)


def test_each_map_seeds_on_its_own_flag(monkeypatch):
    _reset_tile_state()
    flags: dict[str, str] = {}
    monkeypatch.setattr(scraper_main.whatsapp_guard, "get_flag", lambda session, name: flags.get(name))
    monkeypatch.setattr(scraper_main.whatsapp_guard, "set_flag", lambda session, name, value: flags.__setitem__(name, value))
    # rent already seeded earlier; for-sale never swept yet
    flags["yad2_tiles_seeded"] = "done"
    scraper_main._YAD2_TILE_STATE["rent"].update(ran=True, complete=True)
    scraper_main._YAD2_TILE_ONLY_IDS["rent"].update({"r-tile"})
    scraper_main._YAD2_TILE_STATE["forsale"].update(ran=True, complete=True)
    scraper_main._YAD2_TILE_ONLY_IDS["forsale"].update({"s-tile"})
    session = _FakeSession([(1, "r-tile"), (2, "s-tile"), (3, "s-plain")])

    announced = scraper_main._apply_tile_seed_policy(session, [1, 2, 3])

    assert announced == [1, 3]  # the new rent ad is announced, the for-sale backlog ad (2) is stored quietly
    assert len(session.updated) == 1
    assert flags.get("yad2_sale_tiles_seeded") and flags["yad2_tiles_seeded"] == "done"
    _reset_tile_state()


def test_an_incomplete_sale_sweep_does_not_mark_the_sale_seed_done(monkeypatch):
    _reset_tile_state()
    flags: dict[str, str] = {}
    monkeypatch.setattr(scraper_main.whatsapp_guard, "get_flag", lambda session, name: flags.get(name))
    monkeypatch.setattr(scraper_main.whatsapp_guard, "set_flag", lambda session, name, value: flags.__setitem__(name, value))
    scraper_main._YAD2_TILE_STATE["forsale"].update(ran=True, complete=False)
    scraper_main._YAD2_TILE_ONLY_IDS["forsale"].update({"s-tile"})
    session = _FakeSession([(5, "s-tile")])

    announced = scraper_main._apply_tile_seed_policy(session, [5])

    assert announced == []  # still quiet: the backlog must not be announced later either
    assert "yad2_sale_tiles_seeded" not in flags
    _reset_tile_state()
