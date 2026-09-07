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

import hashlib
import hmac
import html
import logging
import os
import threading
from collections import OrderedDict

import httpx
from dorin_common import cities, gemini_client
from dorin_common.channel_link import resolve_link_code
from dorin_common.db import get_session
from dorin_common.matching import safe_range_update
from dorin_common.models import ContactMessage, Filter, User
from dorin_common.support import looks_like_help_request
from dorin_common.users import get_or_create_whatsapp_user
from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

import whatsapp_client

logger = logging.getLogger(__name__)

router = APIRouter()

WEBHOOK_VERIFY_TOKEN_ENV_VAR = "WHATSAPP_WEBHOOK_VERIFY_TOKEN"
APP_SECRET_ENV_VAR = "WHATSAPP_APP_SECRET"

# Mirrors website/main.py's own WEBSITE_URL (and scraper/notifier.py's copy of the same pattern) —
# needed here so the "you already have a filter" reply (below) can link straight to /filter?wid=
# instead of just saying editing isn't available (2026-09-06 fix, see that reply's own comment).
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://todira.app").rstrip("/")

# Same emoji base.html's own nav bar uses for the filter page (⚙️ {{ t('nav.filter') }}) —
# 2026-09-06: a real tappable button (whatsapp_client.send_cta_url_message), not a bare link in the
# message text, matching how the reference competitor bot renders its own "עדכון סינון ⚙️" prompt.
_FILTER_EDIT_BUTTON_TEXT = "⚙️ עריכת הסינון"

# 2026-09-06 follow-up: the owner sent a screenshot of the reference competitor bot's own 3-message
# sequence for this exact moment (a CTA button, then two short explanatory follow-ups) and asked
# for the same flow, one to one — these two follow-up lines are copied verbatim from that
# screenshot; the fields they name (price, cities, parking/elevator/safe room) are a real match for
# Todira's own filter fields, not just borrowed wording that happens not to fit.
_FILTER_EDIT_INTRO_TEXT = "כדי לערוך את הסינון, הכי פשוט להיכנס ישירות לדף הסינון שלנו:"
_FILTER_EDIT_FOLLOWUP_1 = (
    "שם תוכל לשנות בקלות את המחיר, להוסיף או להסיר ערים ושכונות, ולבחור העדפות כמו חניה, "
    "מעלית, או ממ\"ד. ברגע שתשמור שם את השינויים, אני אעדכן את ההתראות שלך בהתאם! ✨🏠"
)
_FILTER_EDIT_FOLLOWUP_2 = "צריך עזרה עם משהו ספציפי בסינון? 😊"


def _send_filter_edit_prompt(wa_id: str) -> None:
    """The CTA button + its two follow-up messages, in one place since both call sites below (the
    "you already have a filter" reply and the registration confirmation) end with the exact same
    prompt to go edit it."""
    whatsapp_client.send_cta_url_message(
        wa_id, _FILTER_EDIT_INTRO_TEXT, _FILTER_EDIT_BUTTON_TEXT, f"{WEBSITE_URL}/filter?wid={wa_id}"
    )
    whatsapp_client.send_text_message(wa_id, _FILTER_EDIT_FOLLOWUP_1)
    whatsapp_client.send_text_message(wa_id, _FILTER_EDIT_FOLLOWUP_2)


# 2026-09-07: a real "תמיכה" message used to fall straight into gemini_client.chat_with_existing_user
# (for an already-onboarded user) same as any other free text, which produced a natural-sounding but
# non-actionable reply ("...אני שולח עדכונים ברגע שיש שדירות חדשות...לפנות אלינו דרך עמוד יצירת הקשר
# באתר") with no real link the owner could tap — found live by the owner testing "תמיכה" himself.
# Mirrors bot/handlers/contact_fallback.py's own precedence on Telegram (looks_like_help_request
# checked FIRST, before anything conversation-state-specific): here too it's checked before the
# existing-filter chat branch AND before onboarding parsing, so a help request never gets
# reinterpreted as apartment criteria or small talk on either channel. Owner notification mirrors
# website/main.py's own _notify_owner_sync (same raw Telegram HTTP call) rather than importing that
# private function directly — whatsapp_webhook.py and main.py are separate routers.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OWNER_TELEGRAM_USER_ID = os.environ.get("OWNER_TELEGRAM_USER_ID")

_HELP_REQUEST_BODY = "תודה שכתבת! ההודעה שלך התקבלה ואנחנו נחזור אליך בהקדם 🙏\nאפשר גם לפנות ישירות דרך עמוד יצירת הקשר שלנו:"
_HELP_REQUEST_BUTTON_TEXT = "✉️ יצירת קשר"


def _save_help_request_sync(name: str | None, wa_id: str, message: str) -> int:
    with get_session() as session:
        row = ContactMessage(
            name=name, message=f"[WhatsApp: {wa_id}]\n{message}", source="whatsapp_bot"
        )
        session.add(row)
        session.commit()
        return row.id


def _mark_help_request_notified_sync(contact_message_id: int) -> None:
    with get_session() as session:
        row = session.get(ContactMessage, contact_message_id)
        if row is not None:
            row.notified_owner = True
            session.commit()


def _notify_owner_of_help_request(name: str | None, wa_id: str, text: str) -> bool:
    """Best-effort, mirrors website/main.py's _notify_owner_sync. Never raises: the ContactMessage
    is already committed by the caller before this runs, so a broken/missing token never loses the
    message itself."""
    if not TELEGRAM_BOT_TOKEN or not OWNER_TELEGRAM_USER_ID:
        return False
    # name/text are both attacker-controlled (any WhatsApp sender's profile name/message text) —
    # escaped before going into an HTML-parsed Telegram message, same fix as website/main.py's
    # _notify_owner_sync and bot/handlers/support.py's escalate_to_owner (found live 2026-09-07).
    lines = ["🙋 <b>בקשת תמיכה מ-WhatsApp (טודירה)</b>"]
    if name:
        lines.append(f"שם: {html.escape(name)}")
    lines.append(f"מספר WhatsApp: {wa_id}")
    lines.append("")
    lines.append(html.escape(text))
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": OWNER_TELEGRAM_USER_ID, "text": "\n".join(lines), "parse_mode": "HTML"},
            timeout=10.0,
        )
        return resp.status_code == 200
    except httpx.HTTPError:
        logger.exception("Failed to push WhatsApp help-request to Telegram")
        return False


def _handle_help_request(wa_id: str, profile_name: str | None, text: str) -> None:
    contact_message_id = _save_help_request_sync(profile_name, wa_id, text)
    if _notify_owner_of_help_request(profile_name, wa_id, text):
        _mark_help_request_notified_sync(contact_message_id)
    whatsapp_client.send_cta_url_message(
        wa_id, _HELP_REQUEST_BODY, _HELP_REQUEST_BUTTON_TEXT, f"{WEBSITE_URL}/contact"
    )


# Meta redelivers a webhook it didn't get a prompt 200 for — and used to, here: the whole
# onboarding turn (DB roundtrip + a Gemini call that can legitimately take up to the 10s timeout
# in dorin_common/gemini_client.py, longer under Gemini's own retries before that fix) used to run
# INSIDE the request/response cycle below, so a slow or high-demand Gemini call meant Meta's own
# retry fired before we ever answered — producing the exact live symptom the owner reported
# 2026-09-06: two different bot replies to what looked like one message, and a "technical hiccup"
# reply that took up to a minute to show up. `_seen_message_ids` is a small in-memory
# belt-and-suspenders guard (WhatsApp's own docs call delivery "at least once") — fine as
# process-local state since the website pod is a single replica (charts/todira/templates/
# website-deployment.yaml, replicas: 1), not correctness-critical infrastructure.
_MAX_SEEN_MESSAGE_IDS = 500
_seen_message_ids: "OrderedDict[str, None]" = OrderedDict()


def _already_processed(message_id: str | None) -> bool:
    if not message_id:
        return False
    if message_id in _seen_message_ids:
        return True
    _seen_message_ids[message_id] = None
    if len(_seen_message_ids) > _MAX_SEEN_MESSAGE_IDS:
        _seen_message_ids.popitem(last=False)
    return False

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
    token = request.query_params.get("hub.verify_token") or ""
    challenge = request.query_params.get("hub.challenge", "")
    # hmac.compare_digest, not ==, for the same reason _verify_signature below already uses it:
    # a plain string comparison on a secret token short-circuits on the first mismatched byte,
    # letting a timing attack narrow it down one byte at a time. This endpoint is only ever called
    # once by Meta during setup, so the practical risk is low, but there's no cost to doing it
    # right and it matches this file's own POST-path precedent (found live 2026-09-07).
    token_matches = bool(expected_token) and hmac.compare_digest(token, expected_token)
    if token_matches and mode == "subscribe":
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


def _fire_typing_indicator(message_id: str) -> None:
    """Kicks off the "typing…" indicator on its own thread instead of awaiting it inline — this
    already runs inside a BackgroundTask worker thread, and the indicator call itself is a network
    round-trip that has nothing to do with the actual reply; waiting for it here would just tack
    its own latency onto the START of the Gemini call it's meant to cover for. Best-effort: if it
    fails, the user simply doesn't see the bubble, same as before this feature existed."""
    threading.Thread(
        target=whatsapp_client.mark_as_read_with_typing_indicator,
        args=(message_id,),
        daemon=True,
    ).start()


def _handle_incoming_text_sync(wa_id: str, profile_name: str | None, text: str) -> None:
    with get_session() as session:
        # Channel linking (see dorin_common/channel_link.py): a `ref_xxxxxx` code generated on
        # the website's /account page for an already-logged-in user, sent here as a plain text
        # message to attach THIS WhatsApp number to that same existing account. Checked before
        # get_or_create_whatsapp_user below so a first-time sender linking an account never gets
        # a brand-new, disconnected user row created for them first.
        code_user = resolve_link_code(session, text)
        if code_user is not None:
            existing = session.scalar(
                select(User).where(User.whatsapp_phone_number == wa_id)
            )
            if existing is not None and existing.id != code_user.id:
                # This WhatsApp number already has its own separate account — linking it to a
                # second one would mean merging two rows' filters/history, which we don't do
                # automatically. Leave both accounts exactly as they were.
                whatsapp_client.send_text_message(
                    wa_id,
                    "למספר הווטסאפ הזה כבר יש חשבון נפרד אצלי, אז אי אפשר לחבר אותו לחשבון אחר. "
                    "אם זו טעות, אפשר לפנות אלינו דרך האתר.",
                )
                return
            code_user.whatsapp_phone_number = wa_id
            if profile_name:
                code_user.first_name = code_user.first_name or profile_name
            session.commit()
            whatsapp_client.send_text_message(
                wa_id, "🎉 חיברתי! אתה כבר רשום ומעודכן אצלי במערכת — מעכשיו תקבל עדכונים גם כאן."
            )
            return

        user = get_or_create_whatsapp_user(session, wa_id, profile_name)

        if looks_like_help_request(text):
            _handle_help_request(wa_id, profile_name, text)
            return

        existing_filter = session.scalar(select(Filter).where(Filter.user_id == user.id))
        if existing_filter is not None:
            # 2026-09-06: used to unconditionally send the exact same 3-message "here's how to
            # edit your filter" block on EVERY free-text message from an already-onboarded user,
            # regardless of what they actually wrote ("מה שלומך", random slang, anything) — found
            # live by the owner comparing side-by-side against the reference bot, whose already-
            # onboarded users get a real, varied, contextual reply instead. Now a genuine chat
            # turn via chat_with_existing_user: either applies a requested filter change directly
            # (see that function's own docstring for exactly which fields it can touch and its one
            # known limitation), or just replies naturally — no canned block on every message.
            current_filter = {
                "deal_type": existing_filter.deal_type,
                "cities": existing_filter.cities,
                "rooms_min": float(existing_filter.rooms_min) if existing_filter.rooms_min is not None else None,
                "rooms_max": float(existing_filter.rooms_max) if existing_filter.rooms_max is not None else None,
                "price_min": existing_filter.price_min,
                "price_max": existing_filter.price_max,
                "keywords": existing_filter.keywords,
            }
            result = gemini_client.chat_with_existing_user(
                text, current_filter, cities.CITIES, profile_name
            )
            if result is None:
                whatsapp_client.send_text_message(
                    wa_id, "מצטער, יש לי תקלה טכנית רגעית 😅 נסה/י לשלוח שוב בעוד רגע."
                )
                return

            if result.get("filter_changed"):
                for key in ("deal_type", "cities", "keywords"):
                    if key in result:
                        setattr(existing_filter, key, result[key])
                # safe_range_update refuses to write an inverted min>max range - Gemini decides
                # both sides here from freeform text, not a structured menu, so there's no
                # re-prompt available to catch a garbled range before it's saved (see that
                # function's own docstring; found live 2026-09-07 - an inverted range hard-fails
                # every listing forever, silently). Mirrors bot/handlers/contact_fallback.py's
                # identical fix for the same code path on Telegram.
                if "rooms_min" in result or "rooms_max" in result:
                    existing_filter.rooms_min, existing_filter.rooms_max = safe_range_update(
                        existing_filter.rooms_min, existing_filter.rooms_max,
                        result.get("rooms_min"), result.get("rooms_max"),
                    )
                if "price_min" in result or "price_max" in result:
                    price_min = result.get("price_min")
                    price_max = result.get("price_max")
                    existing_filter.price_min, existing_filter.price_max = safe_range_update(
                        existing_filter.price_min, existing_filter.price_max,
                        int(price_min) if price_min is not None else None,
                        int(price_max) if price_max is not None else None,
                    )
                session.commit()

            whatsapp_client.send_text_message(wa_id, result.get("response_message") or "בסדר! 🙂")
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
        _send_filter_edit_prompt(wa_id)


def _process_payload_sync(payload: dict) -> None:
    """Runs as a FastAPI BackgroundTask — i.e. AFTER the 200 below has already been sent to Meta.
    Doing the actual work (DB + Gemini + the WhatsApp send) here instead of inline in
    receive_webhook is the fix for the slow-reply/duplicate-reply bug: Meta's own retry no longer
    has anything to race, because the ack no longer waits on any of this."""
    try:
        entries = payload.get("entry", [])
    except AttributeError:
        logger.exception("Malformed WhatsApp webhook payload shape")
        return

    for entry in entries:
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
                # Found live 2026-09-07: this used to be ONE try/except around the entire batch —
                # a real webhook delivery can carry several senders' messages at once (Meta
                # batches them), so one message that happens to blow up (a malformed shape, a
                # DB hiccup for that one user) aborted every OTHER message in the same batch too,
                # silently dropping unrelated users' messages. Scoped per-message so a single
                # failure only ever costs that one message.
                try:
                    wa_id = message.get("from")
                    if not wa_id:
                        continue
                    if _already_processed(message.get("id")):
                        continue
                    if message.get("type") != "text":
                        whatsapp_client.send_text_message(
                            wa_id,
                            "כרגע אני יודע לקרוא רק הודעות טקסט 🙂 אפשר לתאר במילים מה את/ה מחפש/ת?",
                        )
                        continue
                    if message.get("id"):
                        _fire_typing_indicator(message["id"])
                    text = (message.get("text") or {}).get("body", "")
                    _handle_incoming_text_sync(wa_id, contacts.get(wa_id), text)
                except Exception:
                    logger.exception(
                        "Error processing one WhatsApp message in the batch (id=%s) — "
                        "continuing with the rest of the batch",
                        message.get("id"),
                    )


@router.post("/webhook/whatsapp")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks) -> Response:
    body = await request.body()
    if not _verify_signature(body, request.headers.get("x-hub-signature-256")):
        return Response(status_code=403)

    try:
        payload = await request.json()
    except Exception:
        logger.exception("Error parsing WhatsApp webhook payload")
        return Response(status_code=200)

    # Ack Meta FIRST, always — see _process_payload_sync's own comment on why this ordering is
    # the actual fix, not just a refactor. A malformed/unexpected payload shape is handled inside
    # the background task itself (logged, never raised) so it can't turn into a retry storm either.
    background_tasks.add_task(_process_payload_sync, payload)
    return Response(status_code=200)
