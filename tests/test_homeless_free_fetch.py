"""2026-10-09: scraper/homeless_client.py fetches Homeless pages through the free browser-fingerprint route first (curl_cffi), with
ZenRows as a fallback limited to a few credits per run. curl_cffi is faked (it is not installed in the test environment)."""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import httpx
import pytest

import homeless_client as hc

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"
_spec = importlib.util.spec_from_file_location("scraper_main_homeless_free", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)

_PAGE = "<html>" + "x" * 6000 + "</html>"


class _Resp:
    def __init__(self, status=200, text=_PAGE):
        self.status_code, self.text = status, text


@pytest.fixture
def fake(monkeypatch):
    state = types.SimpleNamespace(curl_calls=[], zen_calls=[], curl_responses=[], zen_body=_PAGE)

    def curl_get(url, **kwargs):
        state.curl_calls.append((url, kwargs))
        item = state.curl_responses.pop(0) if state.curl_responses else _Resp()
        if isinstance(item, Exception):
            raise item
        return item

    module = types.ModuleType("curl_cffi")
    module.requests = types.SimpleNamespace(get=curl_get)
    monkeypatch.setitem(sys.modules, "curl_cffi", module)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", module.requests)

    def zen_get(url, **kwargs):
        state.zen_calls.append(url)
        return httpx.Response(200, text=state.zen_body, request=httpx.Request("GET", url))

    monkeypatch.setattr(hc.httpx, "get", zen_get)
    monkeypatch.setenv(hc.FREE_FETCH_ENV_VAR, "true")
    monkeypatch.setenv(hc.ZENROWS_API_KEY_ENV_VAR, "key")
    monkeypatch.delenv(hc.ZENROWS_FALLBACK_MAX_ENV_VAR, raising=False)
    monkeypatch.setattr(hc, "_free_consecutive_failures", 0)
    monkeypatch.setattr(hc, "_free_route_blocked", False)
    monkeypatch.setattr(hc, "_zenrows_requests_this_process", 0)
    monkeypatch.setattr(hc, "_FREE_MIN_SPACING_SECONDS", 0.0)
    return state


def test_the_free_route_is_used_first_and_costs_no_zenrows_credit(fake):
    body = hc._zenrows_get("https://www.homeless.co.il/rent/", context_label="t", custom_headers=True)
    assert body == _PAGE
    assert len(fake.curl_calls) == 1 and fake.zen_calls == []
    assert fake.curl_calls[0][1]["impersonate"] == "chrome"


def test_the_free_route_is_off_unless_enabled(fake, monkeypatch):
    monkeypatch.delenv(hc.FREE_FETCH_ENV_VAR)
    hc._zenrows_get("https://www.homeless.co.il/rent/", context_label="t")
    assert fake.curl_calls == [] and len(fake.zen_calls) == 1


@pytest.mark.parametrize(
    "bad",
    [_Resp(403), _Resp(200, "tiny"), _Resp(200, "<html>Just a moment..." + "x" * 6000), ConnectionError("boom")],
)
def test_a_failed_free_fetch_falls_back_to_zenrows(fake, bad):
    fake.curl_responses.append(bad)
    body = hc._zenrows_get("https://www.homeless.co.il/rent/", context_label="t")
    assert body == _PAGE
    assert len(fake.zen_calls) == 1


def test_four_failures_in_a_row_switch_the_free_route_off(fake):
    fake.curl_responses.extend([_Resp(403)] * 4)
    for _ in range(4):
        hc._zenrows_get("https://www.homeless.co.il/rent/", context_label="t")
    assert hc._free_route_blocked is True
    calls_before = len(fake.curl_calls)
    hc._zenrows_get("https://www.homeless.co.il/rent/", context_label="t")
    assert len(fake.curl_calls) == calls_before  # no more free attempts this process


def test_a_success_resets_the_failure_count(fake):
    fake.curl_responses.extend([_Resp(403)] * 3 + [_Resp()] + [_Resp(403)] * 3)
    for _ in range(7):
        hc._zenrows_get("https://www.homeless.co.il/rent/", context_label="t")
    assert hc._free_route_blocked is False


def test_zenrows_fallback_is_capped_per_run(fake, monkeypatch):
    monkeypatch.setenv(hc.ZENROWS_FALLBACK_MAX_ENV_VAR, "2")
    fake.curl_responses.extend([_Resp(403)] * 3)
    hc._zenrows_get("https://www.homeless.co.il/rent/", context_label="t")
    hc._zenrows_get("https://www.homeless.co.il/rent/", context_label="t")
    with pytest.raises(hc.HomelessFetchError, match="credit cap"):
        hc._zenrows_get("https://www.homeless.co.il/rent/", context_label="t")
    assert len(fake.zen_calls) == 2


def test_description_fetch_uses_the_free_route(fake):
    fake.curl_responses.append(
        _Resp(200, '<html><meta property="og:description" content="דירה יפה בלב העיר עם מרפסת גדולה ומעלית" />' + "x" * 6000)
    )
    description = hc.fetch_listing_description("https://www.homeless.co.il/rent/viewad,1.aspx")
    assert description is not None and "דירה יפה" in description
    assert fake.zen_calls == []


def test_rolling_pages_per_run_setting(monkeypatch):
    monkeypatch.delenv(scraper_main._HOMELESS_ROLLING_PAGES_ENV_VAR, raising=False)
    assert scraper_main._homeless_rolling_pages_per_run() == 2
    monkeypatch.setenv(scraper_main._HOMELESS_ROLLING_PAGES_ENV_VAR, "6")
    assert scraper_main._homeless_rolling_pages_per_run() == 6
    monkeypatch.setenv(scraper_main._HOMELESS_ROLLING_PAGES_ENV_VAR, "999")
    assert scraper_main._homeless_rolling_pages_per_run() == 20
    monkeypatch.setenv(scraper_main._HOMELESS_ROLLING_PAGES_ENV_VAR, "abc")
    assert scraper_main._homeless_rolling_pages_per_run() == 2


def test_homeless_backfill_cap_can_be_set_to_zero_for_the_facebook_job(monkeypatch):
    """The Facebook CronJob sets HOMELESS_BACKFILL_MAX_PER_RUN=0: it only scrapes Facebook, and the Homeless description catch-up it
    inherited at the default of 30 wasted ZenRows credits (13 and 30 errors in the 06:00 and 12:00 UTC runs)."""
    monkeypatch.setenv(scraper_main._HOMELESS_BACKFILL_MAX_PER_RUN_ENV_VAR, "0")
    assert scraper_main._homeless_backfill_max_per_run() == 0
    chart = (Path(__file__).resolve().parent.parent / "charts/todira/templates/facebook-scraper-cronjob.yaml").read_text()
    assert 'name: HOMELESS_BACKFILL_MAX_PER_RUN\n                  value: "0"' in chart
