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


def _rent_coordinates_only(items: list):
    """2026-09-22: _scrape_komo now calls fetch_all_coordinate_ids twice — once for rent (no
    kwargs, unchanged) and once for sale (iska="2", search_page_url=SALE_SEARCH_PAGE_URL). These
    existing tests only care about the rent call's own behavior, so the sale call is a real,
    separate call that must be handled (not just ignored), but returns nothing — every assertion
    below about counts/caps stays exactly as it was pre-sale-loop."""
    def _fake(*, iska: str = "1", search_page_url: str | None = None):
        return items if iska == "1" else []
    return _fake


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
        _rent_coordinates_only([{"id": "1"}, {"id": "2"}, {"id": "3"}]),
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


def test_scrape_komo_attaches_real_coords_from_the_coordinates_list(monkeypatch):
    """2026-09-24: lat/lng ride along for free on the SAME coordinates-list response already
    fetched (confirmed nationwide, see komo_client.py) — a genuinely new listing's normalized
    item must carry them, no separate fetch."""
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(
        scraper_main,
        "fetch_all_coordinate_ids",
        _rent_coordinates_only([{"id": "1", "lat": 32.05, "lng": 34.77}]),
    )
    monkeypatch.setattr(
        scraper_main,
        "fetch_komo_listing_detail",
        lambda modaa_num: {"id": modaa_num, "url": f"https://komo.co.il/{modaa_num}", "price": 4000},
    )

    normalized_items, *_ = scraper_main._scrape_komo()

    assert len(normalized_items) == 1
    assert normalized_items[0].latitude == 32.05
    assert normalized_items[0].longitude == 34.77


def test_scrape_komo_never_caps_when_no_new_listings_exist(monkeypatch):
    """Every id already known -> the cap should never even matter (0 new detail fetches either
    way) — a regression guard against the cap accidentally blocking already-known listings."""
    monkeypatch.setenv(scraper_main._KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "0")
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: {"1"})
    monkeypatch.setattr(scraper_main, "fetch_all_coordinate_ids", _rent_coordinates_only([{"id": "1"}]))

    def _fail_if_called(modaa_num):
        raise AssertionError("should never fetch an already-known listing's detail")

    monkeypatch.setattr(scraper_main, "fetch_komo_listing_detail", _fail_if_called)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_komo()

    assert seen_external_ids == {"1"}
    assert normalized_items == []
    assert fetched == 0


def test_homeless_cap_defaults_when_env_var_unset(monkeypatch):
    monkeypatch.delenv(scraper_main._HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_ENV_VAR, raising=False)
    assert (
        scraper_main._homeless_max_new_description_fetches_per_run()
        == scraper_main._DEFAULT_HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_PER_RUN
    )


def test_homeless_cap_respects_valid_override(monkeypatch):
    monkeypatch.setenv(scraper_main._HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_ENV_VAR, "7")
    assert scraper_main._homeless_max_new_description_fetches_per_run() == 7


def test_homeless_cap_falls_back_to_default_on_invalid_value(monkeypatch):
    monkeypatch.setenv(scraper_main._HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_ENV_VAR, "not-a-number")
    assert (
        scraper_main._homeless_max_new_description_fetches_per_run()
        == scraper_main._DEFAULT_HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_PER_RUN
    )


def test_bright_data_enrich_cap_defaults_when_env_var_unset(monkeypatch):
    monkeypatch.delenv(scraper_main._BRIGHT_DATA_ENRICH_MAX_PER_RUN_ENV_VAR, raising=False)
    assert (
        scraper_main._bright_data_enrich_max_per_run()
        == scraper_main._DEFAULT_BRIGHT_DATA_ENRICH_MAX_PER_RUN
    )


def test_bright_data_enrich_cap_respects_valid_override(monkeypatch):
    monkeypatch.setenv(scraper_main._BRIGHT_DATA_ENRICH_MAX_PER_RUN_ENV_VAR, "3")
    assert scraper_main._bright_data_enrich_max_per_run() == 3


def test_bright_data_enrich_cap_falls_back_to_default_on_invalid_value(monkeypatch):
    monkeypatch.setenv(scraper_main._BRIGHT_DATA_ENRICH_MAX_PER_RUN_ENV_VAR, "not-a-number")
    assert (
        scraper_main._bright_data_enrich_max_per_run()
        == scraper_main._DEFAULT_BRIGHT_DATA_ENRICH_MAX_PER_RUN
    )


# --- _scrape_homeless: description fetch only for genuinely-new listings, capped ------------------


def _fake_homeless_item(external_id: str) -> dict:
    return {
        "id": external_id,
        "url": f"https://www.homeless.co.il/rent/viewad,{external_id}.aspx",
        "price": 3000,
        "rooms": 3.0,
        "floor": 1,
        "square_meters": None,
        "street": "רחוב כלשהו",
        "neighborhood": None,
        "city": "תל אביב",
    }


def _homeless_rent_only(items: list):
    """2026-09-24: _scrape_homeless now calls fetch_homeless_results once per category (rent +
    sale, see homeless_client.SEARCH_PAGE_URL/SALE_SEARCH_PAGE_URL) — these existing tests only
    care about the rent path's own behavior, so the sale call is a real, separate call that must
    be handled (not just ignored), but returns nothing, keeping every assertion below unchanged."""
    def _fake(url):
        return iter(items) if url == scraper_main.homeless_client.SEARCH_PAGE_URL else iter([])
    return _fake


def test_scrape_homeless_fetches_description_only_for_genuinely_new_listings(monkeypatch):
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: {"1"})
    monkeypatch.setattr(
        scraper_main,
        "fetch_homeless_results",
        _homeless_rent_only([_fake_homeless_item("1"), _fake_homeless_item("2")]),
    )

    description_calls = []

    # 2026-09-13: scraper/main.py now passes the listing's own real url (raw_item["url"]), not
    # the bare external_id — a bare id can no longer be reconstructed into the right detail-page
    # URL (brokered "Tivuch" listings use a different path prefix). See homeless_client.py's own
    # module docstring and _ROW_RE's comment for the real bug this fixed.
    def _fake_fetch_description(url):
        description_calls.append(url)
        return "תיאור אמיתי"

    monkeypatch.setattr(scraper_main, "fetch_homeless_description", _fake_fetch_description)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_homeless()
    )

    # only the genuinely-new one's URL, never the already-known "1"'s
    assert description_calls == ["https://www.homeless.co.il/rent/viewad,2.aspx"]
    assert seen_external_ids == {"1", "2"}
    assert fetched == 2
    assert all_succeeded is True
    new_item = next(item for item in normalized_items if item.external_id == "2")
    assert new_item.description == "תיאור אמיתי"


def test_scrape_homeless_stops_new_description_fetches_at_the_cap(monkeypatch):
    """3 never-before-seen listings, cap=2: the 3rd should get no description fetch, but ALL THREE
    ids must still land in seen_external_ids (so delisting stays correct) and all three must still
    be upserted (only the EXTRA description fetch is skipped, never the listing itself)."""
    monkeypatch.setenv(scraper_main._HOMELESS_MAX_NEW_DESCRIPTION_FETCHES_ENV_VAR, "2")
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(
        scraper_main,
        "fetch_homeless_results",
        _homeless_rent_only(
            [_fake_homeless_item("1"), _fake_homeless_item("2"), _fake_homeless_item("3")]
        ),
    )

    description_calls = []

    def _fake_fetch_description(url):
        description_calls.append(url)
        return "תיאור אמיתי"

    monkeypatch.setattr(scraper_main, "fetch_homeless_description", _fake_fetch_description)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_homeless()
    )

    # capped at 2, never fetched the 3rd — order-insensitive since 2026-09-15's concurrent
    # fetching (bounded by _HOMELESS_DESCRIPTION_FETCH_CONCURRENCY) doesn't guarantee which of the
    # two in-flight calls' side effects land first, only that both (and only those two) happen.
    assert sorted(description_calls) == [
        "https://www.homeless.co.il/rent/viewad,1.aspx",
        "https://www.homeless.co.il/rent/viewad,2.aspx",
    ]
    assert seen_external_ids == {"1", "2", "3"}
    assert len(normalized_items) == 3
    assert all_succeeded is True


# --- _scrape_homeless: sale category (2026-09-24, task #5/#6) ------------------------------------


def test_scrape_homeless_upserts_a_new_sale_listing_with_sale_deal_type(monkeypatch):
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())

    def _fake_results(url):
        if url == scraper_main.homeless_client.SALE_SEARCH_PAGE_URL:
            return iter([_fake_homeless_item("sale-1")])
        return iter([])

    monkeypatch.setattr(scraper_main, "fetch_homeless_results", _fake_results)
    monkeypatch.setattr(scraper_main, "fetch_homeless_description", lambda url: None)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_homeless()
    )

    assert len(normalized_items) == 1
    assert normalized_items[0].deal_type == scraper_main.DealType.SALE
    assert seen_external_ids == {"sale-1"}
    assert all_succeeded is True


def test_scrape_homeless_sale_failure_does_not_discard_the_rent_results(monkeypatch):
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())

    def _fake_results(url):
        if url == scraper_main.homeless_client.SALE_SEARCH_PAGE_URL:
            raise scraper_main.HomelessFetchError("simulated sale discovery failure")
        return iter([_fake_homeless_item("rent-1")])

    monkeypatch.setattr(scraper_main, "fetch_homeless_results", _fake_results)
    monkeypatch.setattr(scraper_main, "fetch_homeless_description", lambda url: None)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_homeless()
    )

    assert seen_external_ids == {"rent-1"}
    assert len(normalized_items) == 1
    assert normalized_items[0].deal_type == scraper_main.DealType.RENT
    assert all_succeeded is False
    assert errors == 1


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


# --- _scrape_komo: sale coordinate loop, via iska=2/SALE_SEARCH_PAGE_URL (2026-09-22, task #3/#4) --


def test_scrape_komo_upserts_a_new_sale_listing_with_sale_deal_type(monkeypatch):
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())

    def _fake_coordinates(*, iska: str = "1", search_page_url=None):
        return [{"id": "sale-1"}] if iska == "2" else []

    monkeypatch.setattr(scraper_main, "fetch_all_coordinate_ids", _fake_coordinates)
    monkeypatch.setattr(
        scraper_main,
        "fetch_komo_listing_detail",
        lambda modaa_num: {"id": modaa_num, "url": f"https://komo.co.il/{modaa_num}", "price": 2500000},
    )

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_komo()

    assert len(normalized_items) == 1
    assert normalized_items[0].deal_type == scraper_main.DealType.SALE
    assert seen_external_ids == {"sale-1"}
    assert all_succeeded is True


def test_scrape_komo_sale_failure_does_not_discard_the_rent_loops_own_result(monkeypatch):
    """A broken sale coordinate fetch must not lose or corrupt what the rent fetch already found."""
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())

    def _fake_coordinates(*, iska: str = "1", search_page_url=None):
        if iska == "2":
            raise scraper_main.KomoFetchError("simulated sale discovery failure")
        return [{"id": "rent-1"}]

    monkeypatch.setattr(scraper_main, "fetch_all_coordinate_ids", _fake_coordinates)
    monkeypatch.setattr(
        scraper_main,
        "fetch_komo_listing_detail",
        lambda modaa_num: {"id": modaa_num, "url": f"https://komo.co.il/{modaa_num}", "price": 4000},
    )

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_komo()

    assert seen_external_ids == {"rent-1"}
    assert len(normalized_items) == 1
    assert normalized_items[0].deal_type == scraper_main.DealType.RENT
    assert all_succeeded is False  # the sale fetch genuinely failed, must surface as such
    assert errors == 1


def test_scrape_komo_shares_one_detail_fetch_cap_across_rent_and_sale(monkeypatch):
    monkeypatch.setenv(scraper_main._KOMO_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "1")
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())

    def _fake_coordinates(*, iska: str = "1", search_page_url=None):
        return [{"id": "rent-1"}] if iska == "1" else [{"id": "sale-1"}]

    monkeypatch.setattr(scraper_main, "fetch_all_coordinate_ids", _fake_coordinates)
    detail_calls = []

    def _fake_detail(modaa_num):
        detail_calls.append(modaa_num)
        return {"id": modaa_num, "url": f"https://komo.co.il/{modaa_num}", "price": 4000}

    monkeypatch.setattr(scraper_main, "fetch_komo_listing_detail", _fake_detail)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_komo()

    assert detail_calls == ["rent-1"]  # cap=1, spent on the rent id (fetched first)
    assert seen_external_ids == {"rent-1", "sale-1"}
    assert len(normalized_items) == 1


# --- _scrape_yad2: a failing region gets ONE retry before delisting is skipped (2026-09-14) -------


def _fake_yad2_item(external_id: str) -> dict:
    return {
        "id": external_id,
        "price": 5000,
        "rooms": 2.0,
        "floor": 1,
        "square_meters": 60,
        "street": "רחוב כלשהו",
        "neighborhood": None,
        "city": "תל אביב",
    }


def test_scrape_yad2_retries_once_on_transient_failure_and_succeeds(monkeypatch):
    monkeypatch.setattr(scraper_main, "REGION_SLUGS", ["tel-aviv-area"])
    # tel-aviv-area is a real REGIONS_ON_MAP_API entry (2026-09-14) — cleared here so this test
    # exercises the generic ZenRows/fetch_region_pages retry path it was written for, independent
    # of which specific region happens to be on the map API today (see the dedicated
    # test_scrape_yad2_uses_the_map_api_for_regions_on_it below for that routing itself).
    monkeypatch.setattr(scraper_main, "REGIONS_ON_MAP_API", {})
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_REGION_RETRY_DELAY_SECONDS", 0)
    # 2026-09-22: _scrape_yad2 now also runs a forsale loop after the rent loop (task #1/#2) — a
    # clean no-op default so these existing rent-only tests' assertions are unaffected; pacing
    # zeroed so the forsale loop's own per-region sleep doesn't slow every test down.
    monkeypatch.setattr(scraper_main, "fetch_forsale_region", lambda region: iter([]))
    monkeypatch.setattr(scraper_main, "_MAP_API_REGION_PACING_SECONDS", 0)
    calls = []

    def _fake_fetch_region_pages(region, known_ids, **kwargs):
        calls.append(region)
        if len(calls) == 1:
            raise scraper_main.Yad2FetchError("ZenRows Fetch API request failed: transient")
        yield _fake_yad2_item("1")

    monkeypatch.setattr(scraper_main, "fetch_region_pages", _fake_fetch_region_pages)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_yad2()

    assert len(calls) == 2  # a real retry happened
    assert all_succeeded is True  # the retry succeeded, so delisting is NOT skipped
    assert seen_external_ids == {"1"}
    assert errors == 0


def test_scrape_yad2_gives_up_after_retry_also_fails(monkeypatch):
    monkeypatch.setattr(scraper_main, "REGION_SLUGS", ["tel-aviv-area"])
    monkeypatch.setattr(scraper_main, "REGIONS_ON_MAP_API", {})  # see comment above, same reason
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_REGION_RETRY_DELAY_SECONDS", 0)
    # 2026-09-22: _scrape_yad2 now also runs a forsale loop after the rent loop (task #1/#2) — a
    # clean no-op default so these existing rent-only tests' assertions are unaffected; pacing
    # zeroed so the forsale loop's own per-region sleep doesn't slow every test down.
    monkeypatch.setattr(scraper_main, "fetch_forsale_region", lambda region: iter([]))
    monkeypatch.setattr(scraper_main, "_MAP_API_REGION_PACING_SECONDS", 0)
    calls = []

    def _fake_fetch_region_pages(region, known_ids, **kwargs):
        calls.append(region)
        raise scraper_main.Yad2FetchError("Yad2's own bot-challenge page came back")
        yield  # pragma: no cover - makes this a generator, never reached

    monkeypatch.setattr(scraper_main, "fetch_region_pages", _fake_fetch_region_pages)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_yad2()

    assert len(calls) == 3  # the original attempt AND both retries were genuinely made
    assert all_succeeded is False
    assert errors == 1


def test_scrape_yad2_does_not_retry_on_auth004_quota_error(monkeypatch):
    # A quota error can't be fixed by waiting a few seconds - retrying it just burns another call
    # for nothing, so this must give up after exactly one attempt, not two.
    monkeypatch.setattr(scraper_main, "REGION_SLUGS", ["tel-aviv-area"])
    monkeypatch.setattr(scraper_main, "REGIONS_ON_MAP_API", {})  # see comment above, same reason
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_REGION_RETRY_DELAY_SECONDS", 0)
    # 2026-09-22: _scrape_yad2 now also runs a forsale loop after the rent loop (task #1/#2) — a
    # clean no-op default so these existing rent-only tests' assertions are unaffected; pacing
    # zeroed so the forsale loop's own per-region sleep doesn't slow every test down.
    monkeypatch.setattr(scraper_main, "fetch_forsale_region", lambda region: iter([]))
    monkeypatch.setattr(scraper_main, "_MAP_API_REGION_PACING_SECONDS", 0)
    calls = []

    def _fake_fetch_region_pages(region, known_ids, **kwargs):
        calls.append(region)
        raise scraper_main.Yad2FetchError(
            "ZenRows returned an error instead of the Yad2 page for city='tel-aviv': "
            "http_status=401 code='AUTH004' title='Usage exceeded (AUTH004)'"
        )
        yield  # pragma: no cover - makes this a generator, never reached

    monkeypatch.setattr(scraper_main, "fetch_region_pages", _fake_fetch_region_pages)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_yad2()

    assert len(calls) == 1  # never retried
    assert all_succeeded is False
    assert errors == 1


def test_scrape_yad2_multiple_regions_each_get_their_own_independent_retry(monkeypatch):
    """One region failing (and recovering on retry) must not affect a different region's own
    fetch — each region's retry state is independent."""
    monkeypatch.setattr(scraper_main, "REGION_SLUGS", ["tel-aviv-area", "jerusalem-area"])
    monkeypatch.setattr(scraper_main, "REGIONS_ON_MAP_API", {})  # see comment above, same reason
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_REGION_RETRY_DELAY_SECONDS", 0)
    # 2026-09-22: _scrape_yad2 now also runs a forsale loop after the rent loop (task #1/#2) — a
    # clean no-op default so these existing rent-only tests' assertions are unaffected; pacing
    # zeroed so the forsale loop's own per-region sleep doesn't slow every test down.
    monkeypatch.setattr(scraper_main, "fetch_forsale_region", lambda region: iter([]))
    monkeypatch.setattr(scraper_main, "_MAP_API_REGION_PACING_SECONDS", 0)
    calls_per_region: dict[str, int] = {}

    def _fake_fetch_region_pages(region, known_ids, **kwargs):
        calls_per_region[region] = calls_per_region.get(region, 0) + 1
        if region == "tel-aviv-area" and calls_per_region[region] == 1:
            raise scraper_main.Yad2FetchError("transient network error")
        yield _fake_yad2_item(f"{region}-1")

    monkeypatch.setattr(scraper_main, "fetch_region_pages", _fake_fetch_region_pages)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_yad2()

    assert calls_per_region == {"tel-aviv-area": 2, "jerusalem-area": 1}
    assert all_succeeded is True
    assert seen_external_ids == {"tel-aviv-area-1", "jerusalem-area-1"}


# --- _scrape_yad2: forsale loop, via fetch_forsale_region (2026-09-22, task #1/#2) ---------------


def test_scrape_yad2_forsale_upserts_with_sale_deal_type(monkeypatch):
    monkeypatch.setattr(scraper_main, "REGION_SLUGS", ["tel-aviv-area"])
    monkeypatch.setattr(scraper_main, "REGIONS_ON_MAP_API", {})
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_REGION_RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(scraper_main, "_MAP_API_REGION_PACING_SECONDS", 0)
    monkeypatch.setattr(scraper_main, "fetch_region_pages", lambda region, known_ids, **kw: iter([]))
    monkeypatch.setattr(
        scraper_main, "fetch_forsale_region", lambda region: iter([_fake_yad2_item("sale-1")])
    )

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_yad2()

    assert len(normalized_items) == 1
    assert normalized_items[0].deal_type == scraper_main.DealType.SALE
    assert seen_external_ids == {"sale-1"}
    assert all_succeeded is True


def test_scrape_yad2_forsale_retries_once_on_transient_failure(monkeypatch):
    monkeypatch.setattr(scraper_main, "REGION_SLUGS", ["tel-aviv-area"])
    monkeypatch.setattr(scraper_main, "REGIONS_ON_MAP_API", {})
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_REGION_RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(scraper_main, "_MAP_API_REGION_PACING_SECONDS", 0)
    monkeypatch.setattr(scraper_main, "fetch_region_pages", lambda region, known_ids, **kw: iter([]))
    calls = []

    def _fake_fetch_forsale_region(region):
        calls.append(region)
        if len(calls) == 1:
            raise scraper_main.Yad2MapFetchError("Web Unlocker failed: transient")
        yield _fake_yad2_item("sale-1")

    monkeypatch.setattr(scraper_main, "fetch_forsale_region", _fake_fetch_forsale_region)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_yad2()

    assert len(calls) == 2  # a real retry happened
    assert all_succeeded is True
    assert seen_external_ids == {"sale-1"}


def test_scrape_yad2_forsale_failure_does_not_affect_the_rent_loops_own_result(monkeypatch):
    """A broken forsale region must not lose or corrupt what the rent loop already found."""
    monkeypatch.setattr(scraper_main, "REGION_SLUGS", ["tel-aviv-area"])
    monkeypatch.setattr(scraper_main, "REGIONS_ON_MAP_API", {})
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_REGION_RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(scraper_main, "_MAP_API_REGION_PACING_SECONDS", 0)
    monkeypatch.setattr(
        scraper_main, "fetch_region_pages", lambda region, known_ids, **kw: iter([_fake_yad2_item("rent-1")])
    )

    def _fail(region):
        raise scraper_main.Yad2MapFetchError("Web Unlocker failed: persistent")
        yield  # pragma: no cover - makes this a generator, never reached

    monkeypatch.setattr(scraper_main, "fetch_forsale_region", _fail)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_yad2()

    assert seen_external_ids == {"rent-1"}
    assert any(item.deal_type == scraper_main.DealType.RENT for item in normalized_items)
    assert all_succeeded is False  # the forsale region genuinely failed, must surface as such
    assert errors == 1


# --- _scrape_yad2: regions on REGIONS_ON_MAP_API use the Bright Data map API, not ZenRows -------
# (2026-09-14 — the real, partial migration; see yad2_client.REGIONS_ON_MAP_API's own comment)


def test_scrape_yad2_uses_the_map_api_for_regions_on_it(monkeypatch):
    monkeypatch.setattr(scraper_main, "REGION_SLUGS", ["tel-aviv-area", "jerusalem-area"])
    monkeypatch.setattr(scraper_main, "REGIONS_ON_MAP_API", {"tel-aviv-area": {}})
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_REGION_RETRY_DELAY_SECONDS", 0)
    # 2026-09-22: _scrape_yad2 now also runs a forsale loop after the rent loop (task #1/#2) — a
    # clean no-op default so these existing rent-only tests' assertions are unaffected; pacing
    # zeroed so the forsale loop's own per-region sleep doesn't slow every test down.
    monkeypatch.setattr(scraper_main, "fetch_forsale_region", lambda region: iter([]))
    monkeypatch.setattr(scraper_main, "_MAP_API_REGION_PACING_SECONDS", 0)
    map_calls = []
    zenrows_calls = []

    def _fake_fetch_region_via_map_api(region):
        map_calls.append(region)
        yield _fake_yad2_item(f"{region}-map")

    def _fake_fetch_region_pages(region, known_ids, **kwargs):
        zenrows_calls.append(region)
        yield _fake_yad2_item(f"{region}-zenrows")

    monkeypatch.setattr(scraper_main, "fetch_region_via_map_api", _fake_fetch_region_via_map_api)
    monkeypatch.setattr(scraper_main, "fetch_region_pages", _fake_fetch_region_pages)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_yad2()

    assert map_calls == ["tel-aviv-area"]  # went through the map API, not ZenRows
    assert zenrows_calls == ["jerusalem-area"]  # unaffected region still uses fetch_region_pages
    assert all_succeeded is True
    assert seen_external_ids == {"tel-aviv-area-map", "jerusalem-area-zenrows"}


# --- _scrape_facebook: account-safety cap + required city enrichment (2026-09-15) ----------------


def _rent_only(items: list):
    """2026-09-22: _scrape_facebook now calls fetch_facebook_results once per category (rent +
    forsale, see _FACEBOOK_MARKETPLACE_CATEGORIES) sharing one cap/pacing budget — these existing
    tests only care about the rent path's own behavior, so the forsale call is a real, separate
    call that must be handled (not just ignored), but returns nothing, keeping every assertion
    below about counts/caps exactly as it was pre-category-loop."""
    def _fake(url_path):
        return iter(items) if url_path == scraper_main.facebook_client.DEFAULT_URL_PATH else iter([])
    return _fake


def _fake_facebook_item(external_id: str) -> dict:
    return {
        "id": external_id,
        "url": f"https://www.facebook.com/marketplace/item/{external_id}/",
        "price": 3000,
        "images": [],
        "rooms": None,
        "floor": None,
        "square_meters": None,
        "city": None,
        "neighborhood": None,
        "street": None,
    }


def test_facebook_cap_defaults_when_env_var_unset(monkeypatch):
    monkeypatch.delenv(scraper_main._FACEBOOK_MAX_NEW_DETAIL_FETCHES_ENV_VAR, raising=False)
    assert (
        scraper_main._facebook_max_new_detail_fetches_per_run()
        == scraper_main._DEFAULT_FACEBOOK_MAX_NEW_DETAIL_FETCHES_PER_RUN
    )


def test_facebook_cap_respects_valid_override(monkeypatch):
    monkeypatch.setenv(scraper_main._FACEBOOK_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "5")
    assert scraper_main._facebook_max_new_detail_fetches_per_run() == 5


def test_facebook_cap_falls_back_to_default_on_invalid_value(monkeypatch):
    monkeypatch.setenv(scraper_main._FACEBOOK_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "not-a-number")
    assert (
        scraper_main._facebook_max_new_detail_fetches_per_run()
        == scraper_main._DEFAULT_FACEBOOK_MAX_NEW_DETAIL_FETCHES_PER_RUN
    )


def test_scrape_facebook_skips_already_known_listings_entirely(monkeypatch):
    """Unlike Homeless, a known Facebook listing is never re-upserted at all — re-normalizing it
    here (city=None at discovery) would clobber its already-good city on the UPDATE path."""
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: {"1"})
    monkeypatch.setattr(
        scraper_main, "fetch_facebook_results", _rent_only([_fake_facebook_item("1")])
    )

    def _fail_if_called(item_id):
        raise AssertionError("should never fetch an already-known listing's detail page")

    monkeypatch.setattr(scraper_main, "fetch_facebook_listing_detail", _fail_if_called)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook()
    )

    assert seen_external_ids == {"1"}
    assert normalized_items == []
    assert fetched == 1
    assert all_succeeded is True


def test_scrape_facebook_upserts_a_new_listing_with_its_real_detail_city(monkeypatch):
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_FACEBOOK_DETAIL_FETCH_PACING_SECONDS_RANGE", (0, 0))
    monkeypatch.setattr(
        scraper_main, "fetch_facebook_results", _rent_only([_fake_facebook_item("1")])
    )
    monkeypatch.setattr(
        scraper_main,
        "fetch_facebook_listing_detail",
        lambda item_id: {"city": "הרצליה", "description": "תיאור אמיתי"},
    )

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook()
    )

    assert len(normalized_items) == 1
    assert normalized_items[0].city == "הרצליה"
    assert normalized_items[0].description == "תיאור אמיתי"
    assert errors == 0


def test_scrape_facebook_skips_a_new_listing_with_no_confirmed_city(monkeypatch):
    """No safe fallback for an unknown city — the listing is skipped entirely (not upserted with
    city=None), and stays out of known_ids so a later run retries it."""
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_FACEBOOK_DETAIL_FETCH_PACING_SECONDS_RANGE", (0, 0))
    monkeypatch.setattr(
        scraper_main, "fetch_facebook_results", _rent_only([_fake_facebook_item("1")])
    )
    monkeypatch.setattr(
        scraper_main,
        "fetch_facebook_listing_detail",
        lambda item_id: {"city": None, "description": "יש תיאור אבל אין עיר"},
    )

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook()
    )

    assert normalized_items == []
    assert errors == 1
    assert seen_external_ids == {"1"}  # still counted as seen, for delisting purposes


def test_scrape_facebook_returns_none_detail_gracefully(monkeypatch):
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_FACEBOOK_DETAIL_FETCH_PACING_SECONDS_RANGE", (0, 0))
    monkeypatch.setattr(
        scraper_main, "fetch_facebook_results", _rent_only([_fake_facebook_item("1")])
    )
    monkeypatch.setattr(scraper_main, "fetch_facebook_listing_detail", lambda item_id: None)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook()
    )

    assert normalized_items == []
    assert errors == 1


def test_scrape_facebook_stops_new_detail_fetches_at_the_cap(monkeypatch):
    monkeypatch.setenv(scraper_main._FACEBOOK_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "2")
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_FACEBOOK_DETAIL_FETCH_PACING_SECONDS_RANGE", (0, 0))
    monkeypatch.setattr(
        scraper_main,
        "fetch_facebook_results",
        _rent_only([_fake_facebook_item("1"), _fake_facebook_item("2"), _fake_facebook_item("3")]),
    )

    detail_calls = []

    def _fake_detail(item_id):
        detail_calls.append(item_id)
        return {"city": "הרצליה", "description": None}

    monkeypatch.setattr(scraper_main, "fetch_facebook_listing_detail", _fake_detail)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook()
    )

    assert detail_calls == ["1", "2"]  # capped at 2, never fetched the 3rd
    assert seen_external_ids == {"1", "2", "3"}
    assert len(normalized_items) == 2
    assert all_succeeded is True


def test_scrape_facebook_fails_gracefully_when_discovery_fails(monkeypatch):
    """2026-09-22: _scrape_facebook now tries BOTH categories (rent + forsale) — a broken
    account/cookie fails discovery for both, so this simulates that (not just one), and errors
    reflects both failed categories."""
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())

    def _fail(url_path):
        raise scraper_main.FacebookFetchError("simulated discovery failure")
        yield  # pragma: no cover - makes this a generator, never reached

    monkeypatch.setattr(scraper_main, "fetch_facebook_results", _fail)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook()
    )

    assert normalized_items == []
    assert seen_external_ids == set()
    assert errors == 2  # both categories failed
    assert all_succeeded is False


# --- _scrape_facebook: forsale category (2026-09-22) -----------------------------------------


def test_scrape_facebook_upserts_a_new_forsale_listing_with_sale_deal_type(monkeypatch):
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_FACEBOOK_DETAIL_FETCH_PACING_SECONDS_RANGE", (0, 0))

    def _fake_results(url_path):
        if url_path == "category/propertyforsale/":
            return iter([_fake_facebook_item("sale-1")])
        return iter([])

    monkeypatch.setattr(scraper_main, "fetch_facebook_results", _fake_results)
    monkeypatch.setattr(
        scraper_main,
        "fetch_facebook_listing_detail",
        lambda item_id: {"city": "הרצליה", "description": "דירה למכירה"},
    )

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook()
    )

    assert len(normalized_items) == 1
    assert normalized_items[0].deal_type == scraper_main.DealType.SALE
    assert seen_external_ids == {"sale-1"}
    assert errors == 0
    assert all_succeeded is True


def test_scrape_facebook_shares_one_detail_fetch_cap_across_both_categories(monkeypatch):
    """The account-safety cap is on TOTAL new-detail-fetches this run, not per category — two
    categories must not double the real request budget against the live account."""
    monkeypatch.setenv(scraper_main._FACEBOOK_MAX_NEW_DETAIL_FETCHES_ENV_VAR, "1")
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_FACEBOOK_DETAIL_FETCH_PACING_SECONDS_RANGE", (0, 0))

    def _fake_results(url_path):
        if url_path == scraper_main.facebook_client.DEFAULT_URL_PATH:
            return iter([_fake_facebook_item("rent-1")])
        return iter([_fake_facebook_item("sale-1")])

    monkeypatch.setattr(scraper_main, "fetch_facebook_results", _fake_results)
    detail_calls = []

    def _fake_detail(item_id):
        detail_calls.append(item_id)
        return {"city": "הרצליה", "description": None}

    monkeypatch.setattr(scraper_main, "fetch_facebook_listing_detail", _fake_detail)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = (
        scraper_main._scrape_facebook()
    )

    assert detail_calls == ["rent-1"]  # cap=1, spent on the first (rent) category entirely
    assert seen_external_ids == {"rent-1", "sale-1"}
    assert len(normalized_items) == 1
    assert fetched == 2


# --- _active_source_scrapers: Facebook is opt-in only, a real kill-switch (2026-09-15) ------------


def test_active_source_scrapers_excludes_facebook_by_default(monkeypatch):
    monkeypatch.delenv(scraper_main._SCRAPE_SOURCES_ENV_VAR, raising=False)

    sources = [source for source, _fn in scraper_main._active_source_scrapers()]

    assert scraper_main.Source.FACEBOOK_MARKETPLACE not in sources
    assert sources == [scraper_main.Source.YAD2, scraper_main.Source.KOMO, scraper_main.Source.HOMELESS]


def test_active_source_scrapers_includes_only_facebook_when_explicitly_opted_in(monkeypatch):
    monkeypatch.setenv(scraper_main._SCRAPE_SOURCES_ENV_VAR, "facebook_marketplace")

    sources = [source for source, _fn in scraper_main._active_source_scrapers()]

    assert sources == [scraper_main.Source.FACEBOOK_MARKETPLACE]


def test_active_source_scrapers_respects_a_multi_source_list(monkeypatch):
    monkeypatch.setenv(scraper_main._SCRAPE_SOURCES_ENV_VAR, "yad2,facebook_marketplace")

    sources = [source for source, _fn in scraper_main._active_source_scrapers()]

    assert sources == [scraper_main.Source.YAD2, scraper_main.Source.FACEBOOK_MARKETPLACE]


def test_scrape_yad2_map_api_region_retries_on_yad2_map_fetch_error(monkeypatch):
    monkeypatch.setattr(scraper_main, "REGION_SLUGS", ["tel-aviv-area"])
    monkeypatch.setattr(scraper_main, "REGIONS_ON_MAP_API", {"tel-aviv-area": {}})
    monkeypatch.setattr(scraper_main, "_fetch_known_external_ids", lambda source: set())
    monkeypatch.setattr(scraper_main, "_REGION_RETRY_DELAY_SECONDS", 0)
    # 2026-09-22: _scrape_yad2 now also runs a forsale loop after the rent loop (task #1/#2) — a
    # clean no-op default so these existing rent-only tests' assertions are unaffected; pacing
    # zeroed so the forsale loop's own per-region sleep doesn't slow every test down.
    monkeypatch.setattr(scraper_main, "fetch_forsale_region", lambda region: iter([]))
    monkeypatch.setattr(scraper_main, "_MAP_API_REGION_PACING_SECONDS", 0)
    calls = []

    def _fake_fetch_region_via_map_api(region):
        calls.append(region)
        if len(calls) == 1:
            raise scraper_main.Yad2MapFetchError("Bright Data ISP proxy failed: transient")
        yield _fake_yad2_item("1")

    monkeypatch.setattr(scraper_main, "fetch_region_via_map_api", _fake_fetch_region_via_map_api)

    normalized_items, seen_external_ids, fetched, errors, all_succeeded = scraper_main._scrape_yad2()

    assert len(calls) == 2  # a real retry happened, same as the ZenRows path
    assert all_succeeded is True
    assert seen_external_ids == {"1"}
    assert errors == 0
