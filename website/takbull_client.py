"""Thin wrapper around Takbull's hosted payment page for real plan purchases — same role as
website/grow_client.py, offered as a zero-monthly-fee alternative the owner chose specifically
because Grow's fixed monthly fee (₪29-69) wasn't justifiable against Todira's unproven revenue.
website/main.py's /upgrade tries this BEFORE Grow (see that route's own comment for the exact
fallback order).

Verified live 2026-09-06 against the owner's own real Takbull account (not guessed):
- The plan is "עסקים מהיר – 50 מסמכים" (₪0/month, 1.4% per transaction) — hosted payment pages and
  Webhook automation are both included at no extra monthly cost. Only the API-key/"מוסף סליקת
  אשראי" module (₪99 one-time) is paywalled, and this integration deliberately doesn't need it:
  the owner creates the payment page and its 3 line items (SKUs todira-plan-weekly/biweekly/
  monthly, matching website/main.py's PLAN_PRICES_ILS keys exactly) once by hand in Takbull's
  dashboard, not via API.
- That page (one URL, e.g. https://paypage.takbull.co.il/xxxxx) lists all 3 plan items as a small
  cart — confirmed it honors `?email=...` as a URL query param that pre-fills the checkout form.
  This module uses the same mechanism to pass `order_reference` through, since Takbull's own
  published Webhook guide documents an `order_reference` field on the order-success event payload
  for exactly this purpose. NOT independently confirmed end-to-end yet — order_reference has no
  visible form field to check against like email did, so the first real payment is what actually
  confirms this. /webhooks/takbull in website/main.py logs the full raw payload unconditionally
  and cross-checks OrderTotalSum against the payment's own recorded amount before granting
  anything, so a wrong/missing order_reference fails safe (left pending, not guessed at) rather
  than silently mis-crediting.
- Takbull's webhook has NO signature/HMAC verification (confirmed against their own published
  security guidance, which recommends validating sensitive actions server-side rather than
  trusting the payload alone) — and unlike Grow, the webhook URL is configured ONCE in their
  dashboard for ALL orders, not passed per-transaction, so the per-payment webhook_token trick
  Payment already has (see its own comment) doesn't apply here. Same defense, different shape: a
  single shared secret baked into the URL PATH itself (TAKBULL_WEBHOOK_SECRET below), registered
  as that one static "Hook Address" in Takbull's dashboard — see website/main.py's
  /webhooks/takbull/{secret} route.

Scope: this module originally also had a one-time-charge-per-purchase hosted-page flow
(is_configured()/build_checkout_url(), see grow_client.py's own comment for the equivalent Grow
concept) — removed 2026-09-25 as confirmed-dead code, see the removal note further down.

2026-09-21 addition — real recurring subscription billing (₪49.90/month, see
todira_common/access.py's SUBSCRIPTION_PLAN): Takbull's ₪0/month hosted-page trick above has no
concept of a recurring order at all — that requires their actual REST API (api.takbull.co.il,
API_Key/API_Secret headers), documented in the PDF the owner supplied (Postman workspace
pawow2/takbull, base URL confirmed live against real request/response examples, not guessed):
- POST /api/ExtranalAPI/GetTakbullPaymentPageRedirectUrl with DealType=4 ("Recurring"),
  RecuringInterval=5 ("EachMonth"), OrderTotalSum/InitialAmount for the charge amount, plus the
  same order_reference/RedirectAddress/CancelReturnAddress/IPNAddress fields the one-time flow
  already uses — response is {responseCode, uniqId}; redirect the customer to
  https://api.takbull.co.il/PaymentGateway?orderUniqId={uniqId} same as any other order.
- GET /api/ExtranalAPI/CancelSubscription?uniqId={uniqId} to stop future auto-renewal.
Requires the owner's account to have the API-key module enabled (₪99 one-time — see this module's
history above: the hosted-page flow was deliberately built to NOT need it, but recurring billing
genuinely requires the real API, there's no hosted-page equivalent) and real API_Key/API_Secret.
CORRECTED 2026-09-21 (the previous version of this line named a specific dashboard URL —
app.takbull.co.il/api-setting — that was never actually confirmed against the PDF and should not
have been stated as fact): the PDF's own Authentication section says only "Contact Takbull support
to obtain sandbox credentials at app.takbull.co.il" — it does not document a self-service page for
PRODUCTION keys. Where the owner actually gets the real API_Key/API_Secret from is genuinely
unconfirmed; ask Takbull support directly rather than hunting for a menu that may not exist.
recurring_api_configured() gates every function below on both
being set — NOT YET LIVE-VERIFIED end to end (no real subscription has been created or renewed
through this yet); the first real subscription checkout is what actually confirms these field
names/response shapes, same "verify live, don't guess" posture as grow_client.py's own module
docstring. In particular: the exact webhook payload shape for a RENEWAL charge (month 2+, fired
automatically by Takbull's own recurring engine, not by anything this site does) is inferred from
the documented IsSubscriptionPayment field, not confirmed against a real renewal event — see
website/main.py's /webhooks/takbull for how that's handled defensively (matches by
subscription_uniqid, keyed off Payment.gateway_transaction_id for idempotency, never trusts an
unrecognized shape).
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

WEBHOOK_SECRET_ENV_VAR = "TAKBULL_WEBHOOK_SECRET"
API_KEY_ENV_VAR = "TAKBULL_API_KEY"
API_SECRET_ENV_VAR = "TAKBULL_API_SECRET"

_API_BASE_URL = "https://api.takbull.co.il"
_REQUEST_TIMEOUT_SECONDS = 15.0
# RecuringInterval enum value for "EachMonth" — per the API docs' Order Parameters table
# (1=Daily, 2=Weekly, 3=Monthly, 4=Annual, 5=EachMonth).
_RECURRING_INTERVAL_EACH_MONTH = 5
_DEAL_TYPE_RECURRING = 4


# 2026-09-25 real cleanup, found while answering the owner's own direct question ("is the honor-
# system 'I paid' button actually old leftover code?"): is_configured()/build_checkout_url() used
# to gate a Takbull PAYMENT-PAGE-URL-based checkout flow, superseded by the real recurring-API
# integration below (recurring_api_configured()/create_subscription_checkout_url) — confirmed live
# that website/main.py's /upgrade route never calls either function anywhere, and a repo-wide grep
# found no other caller either. Removed rather than left as dead code that could itself cause the
# exact confusion this question came from.


def recurring_api_configured() -> bool:
    """Gates every function below (create_subscription_checkout_url/cancel_subscription) — see the
    module docstring for why recurring billing needs Takbull's real API (API_Key/API_Secret),
    unlike the ₪0/month hosted-page flow above which needs neither. website/main.py's /upgrade
    falls back to the earlier one-time plans/Grow/informal flow when this is False."""
    return bool(
        os.environ.get(WEBHOOK_SECRET_ENV_VAR, "").strip()
        and os.environ.get(API_KEY_ENV_VAR, "").strip()
        and os.environ.get(API_SECRET_ENV_VAR, "").strip()
    )


def _api_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "API_Key": os.environ.get(API_KEY_ENV_VAR, "").strip(),
        "API_Secret": os.environ.get(API_SECRET_ENV_VAR, "").strip(),
    }


def create_subscription_checkout_url(
    *,
    payment_id: int,
    amount_ils: str,
    customer_full_name: str | None,
    customer_email: str | None,
    redirect_address: str,
    cancel_address: str,
    ipn_address: str,
) -> tuple[str, str] | None:
    """Creates a new recurring (monthly) order via Takbull's real API and returns
    (checkout_url, uniqid) — the uniqid is Takbull's own identifier for this subscription, stored
    on both User.takbull_subscription_uniqid and Payment.subscription_uniqid so a later
    cancel_subscription() call and every renewal-charge webhook can be tied back to it. Returns
    None on any failure (logged, never raises), same fail-soft contract as grow_client.py's
    create_checkout_url. `amount_ils` is passed as a string (Takbull's own examples show it that
    way; the request otherwise mirrors the one-time GetTakbullPaymentPageRedirectUrl shape with
    DealType=4/RecuringInterval=5 added)."""
    if not recurring_api_configured():
        logger.error("create_subscription_checkout_url called but the recurring API isn't configured")
        return None

    payload = {
        "order_reference": str(payment_id),
        "OrderTotalSum": amount_ils,
        "InitialAmount": amount_ils,
        "InitialChargeDescroption": "טודירה — מנוי חודשי",
        "DealType": _DEAL_TYPE_RECURRING,
        "RecuringInterval": _RECURRING_INTERVAL_EACH_MONTH,
        "RedirectAddress": redirect_address,
        "CancelReturnAddress": cancel_address,
        "IPNAddress": ipn_address,
        "CustomerFullName": customer_full_name or "",
        "Customer": {"Email": customer_email} if customer_email else {},
    }
    try:
        response = httpx.post(
            f"{_API_BASE_URL}/api/ExtranalAPI/GetTakbullPaymentPageRedirectUrl",
            json=payload,
            headers=_api_headers(),
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception(
            "Takbull GetTakbullPaymentPageRedirectUrl (recurring) call failed for payment_id=%s",
            payment_id,
        )
        return None

    logger.info(
        "Takbull GetTakbullPaymentPageRedirectUrl (recurring) raw response for payment_id=%s: %r",
        payment_id, data,
    )
    # 2026-09-21: TWO different documented response shapes were found for this same endpoint —
    # the Postman/PDF doc the owner originally supplied shows {"responseCode": 0, "uniqId": "..."}
    # (no page URL — this project builds one), while takbull.co.il's own official API docs site
    # (found live, separately, later) shows {"Status": 1, "uniqId": "...", "PaymentPageUrl": "..."}
    # (1 = success, 0 = failure — opposite polarity from responseCode's 0-means-success). Neither
    # has been confirmed against a real live call yet (still blocked on TAKBULL_API_KEY/
    # TAKBULL_API_SECRET), so rather than guess which one the real API actually returns, this
    # accepts either success signal and prefers a real PaymentPageUrl from the response when one is
    # present, falling back to constructing the URL (the only option the PDF's own shape allows).
    uniqid = data.get("uniqId")
    success = data.get("responseCode") == 0 or data.get("Status") == 1
    if not success or not uniqid:
        logger.error(
            "Takbull GetTakbullPaymentPageRedirectUrl (recurring) response had no usable uniqId "
            "(payment_id=%s) — see the raw payload logged above",
            payment_id,
        )
        return None
    payment_page_url = data.get("PaymentPageUrl") or f"{_API_BASE_URL}/PaymentGateway?orderUniqId={uniqid}"
    return payment_page_url, uniqid


def validate_notification(uniqid: str) -> dict | None:
    """Calls Takbull's real ValidateNotification API and returns its raw response dict, or None on
    any failure (not configured, network error, non-200) — never raises.

    2026-09-21 addition, found live by re-reading the PDF's own IPN section carefully after the
    owner asked "is this about GET?": Takbull's real IPN callback (see website/main.py's
    /webhooks/takbull GET handler) is a lightweight GET ping carrying only uniqId/order_reference/
    a basic statusCode — genuinely no amount, no IsSubscriptionPayment, nothing needed to safely
    grant access. The PDF is explicit: "On receiving the IPN, call ValidateNotification with the
    uniqId to confirm payment details" — this function IS that call. The docs' own example response
    shape (for a deliberately-invalid test uniqId) is {"orderId", "internalCode",
    "internalDescription", "providerCode", "doNotRetry", "isSubscriptionPayment", "saveToken",
    "documentId", "amount", "dealType", "orderStatus", "tranSactionStatus"} — NOT yet live-verified
    against a real successful uniqId (this whole recurring API is still blocked on
    TAKBULL_API_KEY/TAKBULL_API_SECRET never having been set — see PROJECT_STATE.md/the owner
    conversation this was found in), so website/main.py's own webhook handler treats `amount`/
    `isSubscriptionPayment` from this response as the authoritative payment details, but still
    trusts the ORIGINAL IPN's own documented-and-confirmed `statusCode==0` for the actual
    success/failure signal, rather than guessing at what value of `orderStatus`/`internalCode` this
    endpoint uses for "successful" — that specific mapping is NOT confirmed anywhere in the PDF."""
    if not recurring_api_configured():
        logger.error("validate_notification called but the recurring API isn't configured")
        return None
    try:
        response = httpx.post(
            f"{_API_BASE_URL}/api/ExtranalAPI/ValidateNotification",
            json={"uniqId": uniqid},
            headers=_api_headers(),
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Takbull ValidateNotification call failed for uniqid=%s", uniqid)
        return None
    logger.info("Takbull ValidateNotification raw response for uniqid=%s: %r", uniqid, data)
    return data if isinstance(data, dict) else None


def cancel_subscription(uniqid: str) -> bool:
    """Cancels a recurring order via Takbull's real CancelSubscription API — called from
    website/main.py's /account/cancel-subscription. Returns False on any failure (logged, never
    raises); the caller still flips User.cancel_at_period_end regardless (see that route's own
    comment on why: a customer's cancel request shouldn't be blocked by a transient API error, and
    a subsequent renewal-charge webhook that arrives anyway even after Takbull's own cancellation
    failed is now unable to double-credit access past paid_until, since the FRONTEND stops
    reflecting it as an active subscription either way)."""
    if not recurring_api_configured():
        logger.error("cancel_subscription called but the recurring API isn't configured")
        return False
    try:
        response = httpx.get(
            f"{_API_BASE_URL}/api/ExtranalAPI/CancelSubscription",
            params={"uniqId": uniqid},
            headers=_api_headers(),
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Takbull CancelSubscription call failed for uniqid=%s", uniqid)
        return False
    logger.info("Takbull CancelSubscription for uniqid=%s: HTTP %s", uniqid, response.status_code)
    return True
