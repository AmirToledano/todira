"""Display-time enrichment of Yad2 listings that are missing their details (2026-10-05).

A listing normally gets its details (description, floor, parking/elevator/balcony/safe-room, future move-in) when the
scraper first sees it or when it is about to be sent to a paying user. Some never do (over the per-run cap, the one
attempt failed, discovered before the feature existed). This fills them in the first time somebody actually looks at
them — in the background, so the page is never slowed — using Gemini's URL-context tool only
(todira_common/gemini_url_detail.py; no paid fallback). One worker thread serialises the requests (Gemini's free tier
allows ~10/min per model), a listing already queued is never queued twice, and the queue is bounded so a huge page
cannot pile up work. Whatever Gemini returns is stored on the row, so every later viewer gets it for free.

Only FILLS GAPS: a column that already has a value is never overwritten."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from todira_common import gemini_url_detail
from todira_common.db import get_session
from todira_common.enums import Source
from todira_common.models import Listing

logger = logging.getLogger(__name__)

_MAX_QUEUED = 200
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="listing-enrich")
_queued: set[int] = set()
_queued_lock = threading.Lock()


def apply_missing_updates(listing: Listing, updates: dict) -> bool:
    """Sets each updated column only where the listing has no value yet. True if anything changed."""
    changed = False
    for column, value in updates.items():
        current = getattr(listing, column, None)
        if column == "description":
            if current and str(current).strip():
                continue
        elif current is not None:
            continue
        setattr(listing, column, value)
        changed = True
    return changed


def needs_enrichment(listing: Listing) -> bool:
    return listing.source == Source.YAD2 and not (listing.description or "").strip()


def enrich_listing_sync(listing_id: int, url: str) -> bool:
    """Fetch via Gemini and store what it found. Blocking (may wait its turn behind other requests); never raises."""
    try:
        updates = gemini_url_detail.fetch_yad2_detail_updates(url)
        if not updates:
            return False
        with get_session() as session:
            listing = session.get(Listing, listing_id)
            if listing is None:
                return False
            changed = apply_missing_updates(listing, updates)
            if changed:
                session.commit()
            return changed
    except Exception:
        logger.exception("Listing enrichment failed for listing id=%s", listing_id)
        return False
    finally:
        with _queued_lock:
            _queued.discard(listing_id)


def fill_missing_in_background(listings: list[Listing]) -> int:
    """Queue every shown Yad2 listing that has no description for background enrichment. Returns how many were queued.
    Fire-and-forget: the page that called this renders immediately with what it already has."""
    if not gemini_url_detail.is_enabled():
        return 0
    queued = 0
    for listing in listings:
        if not needs_enrichment(listing):
            continue
        with _queued_lock:
            if listing.id in _queued or len(_queued) >= _MAX_QUEUED:
                continue
            _queued.add(listing.id)
        _executor.submit(enrich_listing_sync, listing.id, listing.url)
        queued += 1
    return queued
