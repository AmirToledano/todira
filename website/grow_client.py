"""Thin wrapper around Grow's (formerly Meshulam) hosted-checkout API for real plan purchases —
website/main.py's /upgrade calls create_checkout_url() once GROW_PAGE_CODE/GROW_USER_ID/
GROW_API_KEY are all configured, and falls back to the earlier informal click-trust model when
they aren't (see that route's own comment).

⚠️ PROVISIONAL, NOT VERIFIED AGAINST GROW'S OWN DOCS. This sandbox's network egress blocks every
Grow/Meshulam docs domain (grow-il.readme.io, grow.business, doc.meshulam.co.il all came back
EGRESS_BLOCKED) — the request field names below (pageCode/userId/apiKey/sum/successUrl/cancelUrl/
description/notifyUrl/cField1/paymentNum, sent as multipart/form-data, server-to-server only) are
corroborated from public references to Grow's createPaymentProcess endpoint, NOT read from Grow's
actual reference docs. The RESPONSE JSON shape (which key holds the checkout URL) is a pure guess
— create_checkout_url() tries several plausible keys and always logs the full raw response, so the
first real sandbox call tells us exactly what to fix here. Before ever setting GROW_SANDBOX=false:
  1. Get real API credentials + the actual docs from Grow support (contacting them is required
     anyway to get pageCode/userId/apiKey in the first place).
  2. Run one real sandbox checkout end to end and check the logs for this call and for
     /webhooks/grow's (website/main.py) raw payload log — fix field names against what actually
     comes back, not this guess.

Scope: a single ONE-TIME charge per plan purchase (paymentNum=1), not an auto-renewing
subscription — extend_paid_until (dorin_common/access.py) already models a plan as "extend
paid_until by N days from one payment," and the bot's own renewal nudge (bot/handlers/start.py's
RENEWAL_NEEDED) already assumes the user manually re-purchases when access runs out. True
recurring billing (הוראת קבע, silently re-charging without a fresh user action) is a materially
different, riskier feature — deliberately not built here.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

PAGE_CODE_ENV_VAR = "GROW_PAGE_CODE"
USER_ID_ENV_VAR = "GROW_USER_ID"
API_KEY_ENV_VAR = "GROW_API_KEY"
SANDBOX_ENV_VAR = "GROW_SANDBOX"

# See the module docstring — these two hosts came up specifically in connection with
# createPaymentProcess; unverified beyond that.
_SANDBOX_URL = "https://sandbox.meshulam.co.il/api/light/server/1.0/createPaymentProcess"
_LIVE_URL = "https://secure.meshulam.co.il/api/light/server/1.0/createPaymentProcess"
_REQUEST_TIMEOUT_SECONDS = 15.0


def is_configured() -> bool:
    """website/main.py's /upgrade checks this to decide real-gateway vs. informal-fallback flow."""
    return bool(
        os.environ.get(PAGE_CODE_ENV_VAR, "").strip()
        and os.environ.get(USER_ID_ENV_VAR, "").strip()
        and os.environ.get(API_KEY_ENV_VAR, "").strip()
    )


def create_checkout_url(
    *,
    payment_id: int,
    amount_ils: int,
    description: str,
    success_url: str,
    cancel_url: str,
    notify_url: str,
) -> str | None:
    """Returns the URL to redirect the customer's browser to for a real Grow-hosted checkout, or
    None on any failure (logged, never raises — the caller shows an error page rather than
    crashing the request). `payment_id` (our own payments.id) round-trips via cField1 so
    /webhooks/grow can match the eventual webhook back to the right row."""
    page_code = os.environ.get(PAGE_CODE_ENV_VAR, "").strip()
    user_id = os.environ.get(USER_ID_ENV_VAR, "").strip()
    api_key = os.environ.get(API_KEY_ENV_VAR, "").strip()
    if not (page_code and user_id and api_key):
        logger.error("create_checkout_url called but GROW_PAGE_CODE/USER_ID/API_KEY not fully set")
        return None

    sandbox = os.environ.get(SANDBOX_ENV_VAR, "true").strip().lower() != "false"
    url = _SANDBOX_URL if sandbox else _LIVE_URL

    try:
        response = httpx.post(
            url,
            data={
                "pageCode": page_code,
                "userId": user_id,
                "apiKey": api_key,
                "sum": str(amount_ils),
                "paymentNum": "1",
                "description": description,
                "successUrl": success_url,
                "cancelUrl": cancel_url,
                "notifyUrl": notify_url,
                "cField1": str(payment_id),
            },
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Grow createPaymentProcess call failed for payment_id=%s", payment_id)
        return None

    logger.info("Grow createPaymentProcess raw response for payment_id=%s: %r", payment_id, payload)

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    checkout_url = data.get("url") or payload.get("url") or payload.get("processUrl")
    if not checkout_url:
        logger.error(
            "Grow createPaymentProcess response had no recognizable checkout-URL field "
            "(payment_id=%s) — see the raw payload logged above and fix grow_client.py's "
            "field-name guesses against it",
            payment_id,
        )
        return None
    return checkout_url
