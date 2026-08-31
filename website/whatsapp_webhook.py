"""WhatsApp Cloud API webhook — GET is Meta's one-time verification handshake (run when the
webhook URL + verify token are configured in the app dashboard); POST delivers real events
(incoming messages, delivery/read receipts) going forward.

Onboarding reuses dorin_common.gemini_client.parse_onboarding_message — the exact same
channel-agnostic parser the Telegram bot's free-text onboarding uses (bot/handlers/onboarding.py)
— so a WhatsApp user gets the identical "describe what you want in your own words" experience.
The one real difference: this webhook is stateless between requests (no long-lived process +
PicklePersistence like the bot has), so in-progress onboarding state is persisted on
User.pending_onboarding_state (JSONB) between turns instead of living in memory — see migration
0003_whatsapp_users.

NOT built yet, deliberately: proactive "a new listing matches your filter" pushes. WhatsApp only
allows free-form replies within 24 hours of the user's last message (the "customer service
window") — fine for this webhook's own replies (always responding to something just received),
but a proactive push from scraper/notifier.py outside that window needs a pre-approved message
template (a separate Meta review process). scraper/notifier.py still only sends via Telegram;
extending it is a follow-up, not silently promised here.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os

from dorin_common import cities, gemini_client
from dorin_common.db import get_session
from dorin_common.models import Filter
from dorin_common.users import get_or_create_whatsapp_user
from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

import whatsapp_client

logger = logging.getLogger(__name__)

router = APIRouter()

WEBHOOK_VERIFY_TOKEN_ENV_VAR = "WHATSAPP_WEBHOOK_VERIFY_TOKEN"
APP_SECRET_ENV_VAR = "WHATSAPP_APP_SECRET"

# Mirrors bot/handlers/onboarding.py's _EMPTY_STATE exactly — both feed the same parser.
_EMPTY_ONBOARDING_STATE = {
    "deal_type": None,
    "cities": [],
    "rooms_min": None,
    "rooms_max": None,
    "price_min": None,
    "price_max": None,
    "keywords": [],
}


@router.get("/webhook/whatsapp")
def verify_webhook(request: Request) -> Response:
    expected_token = os.environ.get(WEBHOOK_VERIFY_TOKEN_ENV_VAR, "").strip()
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge", "")
    if expected_token and mode == "subscribe" and token == expected_token:
        return PlainTextResponse(challenge)
    logger.warning("WhatsApp webhook verification failed (mode=%r)", mode)
    return Response(status_code=403)


def _verify_signature(body: bytes, signature_header: str | None) -> bool:
    """Fails CLOSED: if WHATSAPP_APP_SECRET isn't configured, every POST is rejected rather than
    silently accepted unverified — this is a public internet-facing endpoint, so "no secret
    configured yet" must never mean "accept anything.\""""
    app_secret = os.environ.get(APP_SECRET_ENV_VAR, "").strip()
    if not app_secret:
        logger.error("%s not set — rejecting webhook POST (fail closed)", APP_SECRET_ENV_VAR)
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header[len("sha256=") :]
    return hmac.compare_digest(expected, provided)


def _handle_incoming_text_sync(wa_id: str, profile_name: str | None, text: str) -> None:
    with get_session() as session:
        user = get_or_create_whatsapp_user(session, wa_id, profile_name)

        if session.scalar(select(Filter.id).where(Filter.user_id == user.id)) is not None:
            whatsapp_client.send_text_message(
                wa_id,
                "כבר יש לך פילטר רשום אצלנו — אני אמשיך לחפש ולעדכן ברגע שתעלה דירה מתאימה. "
                "עריכת הפילטר דרך וואטסאפ עוד לא זמינה, אבל אפשר כבר עכשיו דרך הבוט בטלגרם.",
            )
            return

        state = user.pending_onboarding_state or dict(_EMPTY_ONBOARDING_STATE)
        result = gemini_client.parse_onboarding_message(text, state, cities.CITIES)

        if result is None:
            whatsapp_client.send_text_message(
                wa_id, "מצטער, יש לי תקלה טכנית רגעית 😅 נסה/י לשלוח שוב בעוד רגע."
            )
            return

        for key in _EMPTY_ONBOARDING_STATE:
            if key in result:
                state[key] = result[key]

        whatsapp_client.send_text_message(wa_id, result.get("response_message") or "רשמתי, תודה!")

        if result.get("missing_required") or not state["deal_type"] or not state["cities"]:
            user.pending_onboarding_state = state
            session.commit()
            return

        session.add(
            Filter(
                user_id=user.id,
                deal_type=state["deal_type"],
                cities=state["cities"],
                rooms_min=state["rooms_min"],
                rooms_max=state["rooms_max"],
                price_min=int(state["price_min"]) if state["price_min"] is not None else None,
                price_max=int(state["price_max"]) if state["price_max"] is not None else None,
                keywords=state["keywords"],
            )
        )
        user.pending_onboarding_state = None
        session.commit()

        whatsapp_client.send_text_message(
            wa_id, "מעולה, נרשמת! אני אתריע ברגע שתעלה דירה מתאימה 🏠"
        )


@router.post("/webhook/whatsapp")
async def receive_webhook(request: Request) -> Response:
    body = await request.body()
    if not _verify_signature(body, request.headers.get("x-hub-signature-256")):
        return Response(status_code=403)

    try:
        payload = await request.json()
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages")
                if not messages:
                    continue  # a delivery/read status update, not an incoming message
                contacts = {
                    c.get("wa_id"): (c.get("profile") or {}).get("name")
                    for c in value.get("contacts", [])
                }
                for message in messages:
                    wa_id = message.get("from")
                    if not wa_id:
                        continue
                    if message.get("type") != "text":
                        await asyncio.to_thread(
                            whatsapp_client.send_text_message,
                            wa_id,
                            "כרגע אני יודע לקרוא רק הודעות טקסט 🙂 אפשר לתאר במילים מה את/ה מחפש/ת?",
                        )
                        continue
                    text = (message.get("text") or {}).get("body", "")
                    await asyncio.to_thread(
                        _handle_incoming_text_sync, wa_id, contacts.get(wa_id), text
                    )
    except Exception:
        # Meta retries a webhook that doesn't return 200 promptly — always return 200 below
        # regardless of what happened processing the payload, so a malformed/unexpected shape
        # can't turn into a retry storm; the exception is still logged for visibility.
        logger.exception("Error processing WhatsApp webhook payload")

    return Response(status_code=200)
