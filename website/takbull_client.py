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

Scope: same one-time-charge-per-purchase model as Grow (see grow_client.py's own comment) — not
auto-renewing billing.
"""
from __future__ import annotations

import os

PAYMENT_PAGE_URL_ENV_VAR = "TAKBULL_PAYMENT_PAGE_URL"
WEBHOOK_SECRET_ENV_VAR = "TAKBULL_WEBHOOK_SECRET"


def is_configured() -> bool:
    """website/main.py's /upgrade checks this to decide the Takbull path vs. Grow vs. the informal
    fallback. Both env vars are required together — a payment page URL with no way to verify the
    webhook that confirms it would be worse than not offering this path at all."""
    return bool(
        os.environ.get(PAYMENT_PAGE_URL_ENV_VAR, "").strip()
        and os.environ.get(WEBHOOK_SECRET_ENV_VAR, "").strip()
    )


def build_checkout_url(*, payment_id: int) -> str | None:
    """Returns the URL to redirect the customer's browser to — the owner's shared Takbull payment
    page, with `order_reference` set to our own payments.id so /webhooks/takbull can (attempt to)
    match the eventual webhook back to the right row. Unlike Grow's create_checkout_url, this never
    calls out to Takbull at all (there's no API involved on this ₪0/month plan) — it's pure string
    building, so the only failure mode is "not configured," never a network/API error."""
    base_url = os.environ.get(PAYMENT_PAGE_URL_ENV_VAR, "").strip()
    if not base_url:
        return None
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}order_reference={payment_id}"
