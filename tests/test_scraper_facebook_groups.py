"""Tests for _scrape_facebook_groups and its config helpers in scraper/main.py — wiring
facebook_groups_client.py (built + tested separately in test_facebook_groups_client.py) into the
real scrape loop, 2026-09-22. Same importlib-loading approach as every other scraper/main.py test
in this suite, same mocking boundary as _scrape_facebook's own tests
(test_scraper_credit_safety.py): mock the client functions main.py calls, never the network.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"

_spec = importlib.util.spec_from_file_location("scraper_main_facebook_groups", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)


def _fake_group_post_detail(post_id: str, *, description: str = "תיאור אמיתי") -> dict:
    return {
        "id": post_id,
        "url": f"https://www.facebook.com/groups/1/posts/{post_id}/",
        "description": description,
        "dateAdded": None,
        "price": None,
        "rooms": None,
        "floor": None,
        "square_meters": None,
        "city": None,
        "neighborhood": None,
        "street": None,
        "images": [],
    }


# --- config helpers ---------------------------------------------------------------------


def test_facebook_groups_tracked_ids_empty_when_unset(monkeypatch):
    monkeypatch.delenv(scraper_main._FACEBOOK_GROUPS_TRACKED_IDS_ENV_VAR, raising=False)
    assert scraper_main._facebook_groups_tracked_ids() == set()


def test_facebook_groups_tracked_ids_parses_comma_separated(monkeypatch):
    monkeypatch.setenv(scraper_main._FACEBOOK_GROUPS_TRACKED_IDS_ENV_VAR, "111, 222,333")
    assert scraper_main._facebook_groups_tracked_ids() == {"111", "222", "333"}


def test_facebook_groups_cap_defaults_when_env_var_unset(monkeypatch):
    monkeypatch.delenv(scraper_main._FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_ENV_VAR, raising=False)
    assert (
        scraper_main._facebook_groups_max_new_detail_fetches_per_run()
        == scraper_main._DEFAULT_FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_PER_RUN
    )


# --- _scrape_facebook_groups ---------------------------------------------------------------------


def test_scrape_facebook_groups_is_noop_when_no_tracked_ids(monkeypatch):
    monkeypatch.delenv(scraper_main._FACEBOOK_GROUPS_TRACKED_IDS_ENV_VAR, raising=False)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook_groups()
    )

    assert normalized_items == []
    assert seen_external_ids == set()
    assert fetched == 0
    assert errors == 0
    assert all_succeeded is True


def test_scrape_facebook_groups_upserts_a_new_post(monkeypatch):
    monkeypatch.setenv(scraper_main._FACEBOOK_GROUPS_TRACKED_IDS_ENV_VAR, "1665476640352771")
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_FACEBOOK_DETAIL_FETCH_PACING_SECONDS_RANGE", (0, 0))
    monkeypatch.setattr(
        scraper_main,
        "fetch_home_feed_post_ids",
        lambda tracked_ids: [("1665476640352771", "999")],
    )
    monkeypatch.setattr(
        scraper_main,
        "fetch_facebook_group_post_detail",
        lambda group_id, post_id: _fake_group_post_detail(post_id),
    )

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook_groups()
    )

    assert fetched == 1
    assert seen_external_ids == {"999"}
    assert len(normalized_items) == 1
    assert normalized_items[0].external_id == "999"
    assert normalized_items[0].description == "תיאור אמיתי"
    assert normalized_items[0].price is None
    assert errors == 0
    assert all_succeeded is True


def test_scrape_facebook_groups_skips_an_already_known_post(monkeypatch):
    monkeypatch.setenv(scraper_main._FACEBOOK_GROUPS_TRACKED_IDS_ENV_VAR, "1665476640352771")
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: {"999"})
    monkeypatch.setattr(
        scraper_main,
        "fetch_home_feed_post_ids",
        lambda tracked_ids: [("1665476640352771", "999")],
    )
    detail_calls = []
    monkeypatch.setattr(
        scraper_main,
        "fetch_facebook_group_post_detail",
        lambda group_id, post_id: detail_calls.append(post_id),
    )

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook_groups()
    )

    assert detail_calls == []  # never fetched — already known
    assert normalized_items == []
    assert seen_external_ids == {"999"}  # still counted as seen, for delisting purposes
    assert fetched == 1


def test_scrape_facebook_groups_counts_a_failed_detail_fetch_as_an_error(monkeypatch):
    monkeypatch.setenv(scraper_main._FACEBOOK_GROUPS_TRACKED_IDS_ENV_VAR, "1665476640352771")
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_FACEBOOK_DETAIL_FETCH_PACING_SECONDS_RANGE", (0, 0))
    monkeypatch.setattr(
        scraper_main,
        "fetch_home_feed_post_ids",
        lambda tracked_ids: [("1665476640352771", "999")],
    )
    monkeypatch.setattr(
        scraper_main, "fetch_facebook_group_post_detail", lambda group_id, post_id: None
    )

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook_groups()
    )

    assert normalized_items == []
    assert errors == 1
    assert all_succeeded is True  # a per-post failure isn't a whole-source failure


def test_scrape_facebook_groups_respects_the_per_run_cap(monkeypatch):
    monkeypatch.setenv(scraper_main._FACEBOOK_GROUPS_TRACKED_IDS_ENV_VAR, "1")
    monkeypatch.setenv(scraper_main._FACEBOOK_GROUPS_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "1")
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_FACEBOOK_DETAIL_FETCH_PACING_SECONDS_RANGE", (0, 0))
    monkeypatch.setattr(
        scraper_main,
        "fetch_home_feed_post_ids",
        lambda tracked_ids: [("1", "100"), ("1", "200")],
    )
    detail_calls = []

    def _fake_detail(group_id, post_id):
        detail_calls.append(post_id)
        return _fake_group_post_detail(post_id)

    monkeypatch.setattr(scraper_main, "fetch_facebook_group_post_detail", _fake_detail)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook_groups()
    )

    assert detail_calls == ["100"]  # only the first, cap=1
    assert len(normalized_items) == 1
    assert seen_external_ids == {"100", "200"}  # both still "seen" for delisting purposes
    assert fetched == 2


def test_scrape_facebook_groups_handles_home_feed_fetch_failure(monkeypatch):
    monkeypatch.setenv(scraper_main._FACEBOOK_GROUPS_TRACKED_IDS_ENV_VAR, "1")
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())

    def _boom(tracked_ids):
        raise scraper_main.FacebookGroupsFetchError("no cookie")

    monkeypatch.setattr(scraper_main, "fetch_home_feed_post_ids", _boom)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook_groups()
    )

    assert normalized_items == []
    assert errors == 1
    assert all_succeeded is False


# --- kill-switch (_active_source_scrapers) ---------------------------------------------------------


def test_active_source_scrapers_excludes_both_facebook_sources_by_default(monkeypatch):
    monkeypatch.delenv(scraper_main._SCRAPE_SOURCES_ENV_VAR, raising=False)
    active = dict(scraper_main._active_source_scrapers())
    assert scraper_main.Source.FACEBOOK_MARKETPLACE not in active
    assert scraper_main.Source.FACEBOOK_GROUPS not in active
    assert scraper_main.Source.YAD2 in active


def test_active_source_scrapers_includes_facebook_groups_when_opted_in(monkeypatch):
    monkeypatch.setenv(scraper_main._SCRAPE_SOURCES_ENV_VAR, "facebook_groups")
    active = dict(scraper_main._active_source_scrapers())
    assert scraper_main.Source.FACEBOOK_GROUPS in active
    assert scraper_main.Source.FACEBOOK_MARKETPLACE not in active
    assert scraper_main.Source.YAD2 not in active
