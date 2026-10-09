"""One entry point for "get this Yad2 ad's details" (2026-10-09): Yad2's own item JSON first (free, todira_common/
yad2_item_api.py), Gemini's URL-context tool as the backup (todira_common/gemini_url_detail.py, only while a Gemini key
with balance is configured). Callers (scraper enrichment/backfill, the notifier's just-in-time fetch, the website's
view-time fill) use this instead of picking a fetcher themselves.

Result contract (same as both fetchers): a dict — possibly EMPTY, meaning "the ad was reached and states nothing usable
or is gone", so there is nothing to retry — or None, meaning "no answer right now, try again later"."""
from __future__ import annotations

from todira_common import gemini_url_detail, yad2_item_api


def is_enabled() -> bool:
    return yad2_item_api.is_enabled() or gemini_url_detail.is_enabled()


def fetch_updates(url: str) -> dict | None:
    if yad2_item_api.is_enabled():
        result = yad2_item_api.fetch_yad2_detail_updates(url)
        if result is not None:
            return result
    if gemini_url_detail.is_enabled():
        return gemini_url_detail.fetch_yad2_detail_updates(url)
    return None
