"""Backstop for the WhatsApp zero-cost rule (2026-10-02): asks Meta's own pricing analytics whether ANY
cost has accrued since the zero-cost design went live, and if so pauses every proactive WhatsApp send
(todira_common/whatsapp_guard.py) and alerts the owner on Telegram.

The real-time layer is the webhook (website/whatsapp_webhook.py trips the same breaker the moment a
delivery status says pricing.billable == true); this catches anything that path could miss, e.g. a
webhook outage. Analytics lag by hours, so it is a backstop, not the primary defence. Runs at most
once every 3 hours (scraper runs hourly), fail-soft: an analytics API error is logged and does NOT
pause anything.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import time

import httpx
from sqlalchemy.orm import Session

from todira_common import whatsapp_guard
from todira_common.owner_alert import alert_owner

logger = logging.getLogger(__name__)

# Charges before the zero-cost design shipped (the 717 template messages, $25.31) must not trip it.
WATCH_FROM = dt.datetime(2026, 10, 2, tzinfo=dt.timezone.utc)
CHECK_EVERY = dt.timedelta(hours=3)
_GRAPH_API_VERSION = "v21.0"


def total_cost(payload: dict) -> float:
    """Sum of every `cost` in a pricing_analytics response. Defensive about the shape."""
    total = 0.0
    analytics = payload.get("pricing_analytics") or {}
    for block in analytics.get("data") or []:
        for point in block.get("data_points") or []:
            try:
                total += float(point.get("cost") or 0)
            except (TypeError, ValueError):
                continue
    return total


def _fetch_cost(waba_id: str, token: str) -> float | None:
    start = int(WATCH_FROM.timestamp())
    end = int(time.time())
    field = (
        f"pricing_analytics.start({start}).end({end}).granularity(DAILY)"
        '.metric_types(["COST"]).dimensions(["PRICING_CATEGORY"])'
    )
    try:
        resp = httpx.get(
            f"https://graph.facebook.com/{_GRAPH_API_VERSION}/{waba_id}",
            params={"fields": field},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return total_cost(resp.json())
    except (httpx.HTTPError, json.JSONDecodeError):
        logger.exception("WhatsApp pricing analytics check failed (not pausing anything)")
        return None


def run_cost_guard(session: Session) -> dict[str, int]:
    waba_id = os.environ.get("WHATSAPP_BUSINESS_ACCOUNT_ID", "").strip()
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip()
    if not waba_id or not token:
        return {}
    now = dt.datetime.now(dt.timezone.utc)
    last_checked = whatsapp_guard.get_flag(session, whatsapp_guard.COST_CHECKED_KEY)
    if last_checked:
        try:
            if now - dt.datetime.fromisoformat(last_checked) < CHECK_EVERY:
                return {}
        except ValueError:
            pass
    cost = _fetch_cost(waba_id, token)
    if cost is None:
        return {}
    whatsapp_guard.set_flag(session, whatsapp_guard.COST_CHECKED_KEY, now.isoformat())
    if cost > 0:
        reason = f"Meta pricing analytics show cost {cost:.4f} since {WATCH_FROM.date()}"
        if not whatsapp_guard.is_paused(session):
            whatsapp_guard.pause(session, reason)
            alert_owner(
                "🛑 <b>וואטסאפ הושהה אוטומטית</b>\n"
                f"מטא מדווחת על עלות ({cost:.2f}$) מאז שהמערכת עברה למצב חינמי. "
                "כל השליחות היזומות נעצרו עד שתחליט להמשיך."
            )
        return {"whatsapp_cost_alarm": 1}
    return {"whatsapp_cost_checked": 1}
