"""Tests for the 2026-09-13 credit-budget safety mechanisms in scraper/main.py — added the same
night a real ZenRows dashboard check found only 7,218 credits left on a plan renewing in ~18 days,
while the schedule/sources active at the time would have burned that in ~3.5 days (see
_KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR's own module-level comment in main.py for the full math).
Three independent, all-optional/temporary env-var-gated mechanisms:

- KOMO_MAX_NEW_DETAIL_FETCHES_PER_RUN: caps how many NEW Komo listings get a paid detail fetch in
  one run (Komo's first-ever production run would otherwise treat every currently-active listing
  nationwide as "new").
- YAD2_MAX_PAGES_PER_REGION: overrides fetch_region_pages' own built-in max_pages, so a long-
  paused resume's catch-up cost can be capped tighter than the general-purpose default.
- NOTIFICATIONS_SUSPENDED: skips the final run_notifications call (scrape/upsert/delist still run
  in full) so a resume's catch-up backlog doesn't fire a notification burst to real users.

Same importlib-loading approach as every other scraper/main.py test in this suite.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"

_spec = importlib.util.spec_from_file_location("scraper_main_credit_safety", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)


# --- env var parsing helpers ---------------------------------------------------------------------


def test_komo_cap_defaults_when_env_var_unset(monkeypatch):
    monkeypatch.delenv(scraper_main._KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR, raising=False)
    assert (
        scraper_main._komo_max_new_detail_fetches_per_run()
        == scraper_main._DEFAULT_KOMO_MAX_NEW_DETAIL_FETCHES_PER_RUN
    )


def test_komo_cap_respects_valid_override(monkeypatch):
    monkeypatch.setenv(scraper_main._KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "42")
    assert scraper_main._komo_max_new_detail_fetches_per_run() == 42


def test_komo_cap_falls_back_to_default_on_invalid_value(monkeypatch):
    monkeypatch.setenv(scraper_main._KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "not-a-number")
    assert (
        scraper_main._komo_max_new_detail_fetches_per_run()
        == scraper_main._DEFAULT_KOMO_MAX_NEW_DETAIL_FETCHES_PER_RUN
    )


def test_yad2_max_pages_override_defaults_to_none_when_unset(monkeypatch):
    monkeypatch.delenv(scraper_main._YAD2_MAX_PAGES_ENV_VAR, raising=False)
    assert scraper_main._yad2_max_pages_per_region_override() is None


def test_yad2_max_pages_override_respects_valid_value(monkeypatch):
    monkeypatch.setenv(scraper_main._YAD2_MAX_PAGES_ENV_VAR, "5")
    assert scraper_main._yad2_max_pages_per_region_override() == 5


def test_yad2_max_pages_override_falls_back_to_none_on_invalid_value(monkeypatch):
    monkeypatch.setenv(scraper_main._YAD2_MAX_PAGES_ENV_VAR, "not-a-number")
    assert scraper_main._yad2_max_pages_per_region_override() is None


def test_notifications_suspended_false_when_unset(monkeypatch):
    monkeypatch.delenv(scraper_main._NOTIFICATIONS_SUSPENDED_ENV_VAR, raising=False)
    assert scraper_main._notifications_suspended() is False


def test_notifications_suspended_true_for_common_truthy_spellings(monkeypatch):
    for value in ("1", "true", "True", "yes", "YES"):
        monkeypatch.setenv(scraper_main._NOTIFICATIONS_SUSPENDED_ENV_VAR, value)
        assert scraper_main._notifications_suspended() is True, f"expected True for {value!r}"


def test_notifications_suspended_false_for_other_values(monkeypatch):
    monkeypatch.setenv(scraper_main._NOTIFICATIONS_SUSPENDED_ENV_VAR, "0")
    assert scraper_main._notifications_suspended() is False


# --- _scrape_komo cap enforcement -----------------------------------------------------------------


def test_scrape_komo_stops_new_detail_fetches_at_the_cap(monkeypatch):
    """3 never-before-seen listings (all from ONE fetch_all_coordinate_ids call — confirmed
    nationwide, see komo_client.py), cap=2: the 3rd listing's detail should never be fetched, but
    ALL THREE ids must still land in seen_external_ids (so delisting stays correct even for the
    capped-out one)."""
    monkeypatch.setenv(scraper_main._KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "2")
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(
        scraper_main,
        "fetch_all_coordinate_ids",
        lambda: [{"id": "1"}, {"id": "2"}, {"id": "3"}],
    )

    fetched_detail_ids = []

    def _fake_fetch_detail(modaa_num):
        fetched_detail_ids.append(modaa_num)
        return {"id": modaa_num, "url": f"https://komo.co.il/{modaa_num}", "price": 4000}

    monkeypatch.setattr(scraper_main, "fetch_komo_listing_detail", _fake_fetch_detail)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_komo()

    assert len(fetched_detail_ids) == 2  # capped at 2, never fetched the 3rd
    assert seen_external_ids == {"1", "2", "3"}  # all three still counted as "seen" for delisting
    assert all_succeeded is True
    assert len(normalized_items) == 2


def test_scrape_komo_never_caps_when_no_new_listings_exist(monkeypatch):
    """Every id already known -> the cap should never even matter (0 new detail fetches either
    way) — a regression guard against the cap accidentally blocking already-known listings."""
    monkeypatch.setenv(scraper_main._KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "0")
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: {"1"})
    monkeypatch.setattr(scraper_main, "fetch_all_coordinate_ids", lambda: [{"id": "1"}])

    def _fail_if_called(modaa_num):
        raise AssertionError("should never fetch an already-known listing's detail")

    monkeypatch.setattr(scraper_main, "fetch_komo_listing_detail", _fail_if_called)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_komo()

    assert seen_external_ids == {"1"}
    assert normalized_items == []
    assert fetched == 0


def test_scrape_komo_fails_gracefully_when_the_one_discovery_call_fails(monkeypatch):
    """2026-09-13: fetch_all_coordinate_ids is now ONE call, not one per city — a failure there
    means Komo has nothing to report this run at all (not a partial per-city failure anymore).
    Must return the same 5-tuple shape (never raise) with all_succeeded=False, so run_once() skips
    delisting for Komo this run instead of mistaking an empty seen_external_ids for "everything
    delisted"."""
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())

    def _fail(*, _err=scraper_main.KomoFetchError):
        raise _err("simulated discovery failure")

    monkeypatch.setattr(scraper_main, "fetch_all_coordinate_ids", _fail)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_komo()

    assert normalized_items == []
    assert seen_external_ids == set()
    assert fetched == 0
    assert errors == 1
    assert all_succeeded is False
