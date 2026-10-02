"""WhatsApp Cloud API webhook — GET is Meta's one-time verification handshake (run when the
webhook URL + verify token are configured in the app dashboard); POST delivers real events
(incoming messages, delivery/read receipts) going forward.

Onboarding reuses todira_common.gemini_client.parse_onboarding_message — the exact same
channel-agnostic parser the Telegram bot's free-text onboarding uses (bot/handlers/onboarding.py)
— so a WhatsApp user gets the identical "describe what you want in your own words" experience.
The one real difference: this webhook is stateless between requests (no long-lived process +
PicklePersistence like the bot has), so in-progress onboarding state is persisted on
User.pending_onboarding_state (JSONB) between turns instead of living in memory — see migration
0003_whatsapp_users.

Proactive pushes (2026-10-02, zero-cost): this project NEVER sends a paid Message Template. A listing
goes out as a free-form message only inside the 24h window opened by the user's own last message
(every inbound message, including a button tap, is stamped on User.whatsapp_last_inbound_at here), and
scraper/whatsapp_checkin.py asks "still looking?" with reply buttons near the end of each window so the
user taps and the window reopens. A user whose window closed gets nothing until they write again, and
then ONE link summarizing what they missed (_send_missed_digest_sync). See todira_common/
whatsapp_window.py.

2026-09-27: connecting WhatsApp (either path) now also sends ONE free-form summary right here
(_send_current_matches_summary, "X apartments already match — see them all: <link>"), covering
every listing that already matches the user's filter at connect time — see that function's own
docstring for why this is a single aggregate link and not one push per already-matching listing.
Going forward from that moment, genuinely NEW listings still reach the user one at a time, via the
normal proactive free-form push above, as the scraper actually finds them.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import logging
import os
import threading
import datetime as dt
import time
from collections import OrderedDict

import httpx
from todira_common import cities, gemini_client, whatsapp_client, whatsapp_guard
from todira_common.bot_strings import bot_text
from todira_common.channel_link import resolve_link_code
from todira_common.db import get_session
from todira_common.language import DEFAULT_LANG, SUPPORTED_LANGS
from todira_common.listing_matches import find_new_matches_to_show
from todira_common.matching import safe_range_update
from todira_common.owner_alert import alert_owner
from todira_common.models import ContactMessage, Filter, User
from todira_common.support import looks_like_help_request
from todira_common.users import get_or_create_whatsapp_user
from todira_common.whatsapp_window import window_open
from todira_common.wid_token import generate_wid_token
from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

router = APIRouter()

WEBHOOK_VERIFY_TOKEN_ENV_VAR = "WHATSAPP_WEBHOOK_VERIFY_TOKEN"
APP_SECRET_ENV_VAR = "WHATSAPP_APP_SECRET"

# Mirrors website/main.py's own WEBSITE_URL (and scraper/notifier.py's copy of the same pattern) —
# needed here so the "you already have a filter" reply (below) can link straight to /filter?wid=
# instead of just saying editing isn't available (2026-09-06 fix, see that reply's own comment).
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://todira.app").rstrip("/")

def _send_filter_edit_prompt(wa_id: str, lang: str) -> None:
    """The CTA button + its two follow-up messages, in one place since both call sites below (the
    "you already have a filter" reply and the registration confirmation) end with the exact same
    prompt to go edit it. Copy originally matched a reference competitor bot's own 3-message
    sequence one to one (2026-09-06); the fields it names (price, cities, parking/elevator/safe
    room) are a real match for Todira's own filter fields, not just borrowed wording."""
    whatsapp_client.send_cta_url_message(
        wa_id,
        bot_text("whatsapp.filter_edit_intro", lang),
        bot_text("whatsapp.filter_edit_button", lang),
        f"{WEBSITE_URL}/filter?wid={generate_wid_token(wa_id)}",
    )
    whatsapp_client.send_text_message(wa_id, bot_text("whatsapp.filter_edit_followup1", lang))
    whatsapp_client.send_text_message(wa_id, bot_text("whatsapp.filter_edit_followup2", lang))


def _send_current_matches_summary(wa_id: str, lang: str, total: int) -> None:
    """Sent once, right when WhatsApp notifications actually turn on — both _try_link_code_sync
    and _handle_incoming_text_sync's onboarding-complete branch, right after each one's own call to
    find_new_matches_to_show. This is the ONE aggregate link/summary for whatever already matches
    at connect time (mirrors Telegram's own onboarding.matches_found/no_matches_yet, see
    bot/handlers/onboarding.py's _save_filter_sync and filter_conversation.py's identical pattern)
    — deliberately NOT one WhatsApp message per matching listing. find_new_matches_to_show already
    recorded every one of these as SentNotification(reason=NEW) as a bookkeeping side effect, so
    the scraper's own proactive WhatsApp push (scraper/notifier.py) only ever fires afterward, for
    listings that show up AFTER this moment, one at a time as they're actually found. This is
    exactly the real owner report this fixes (2026-09-27): connecting WhatsApp used to try to push
    every already-matching listing individually, all at once, right at connect time.

    Free-form send (send_text_message), not the proactive Message Template: this always runs
    within 24h of the user's own inbound message (the link code, or the final onboarding message),
    so it's within WhatsApp's customer-service window and needs no Meta-approved template — same
    reasoning as _send_filter_edit_prompt above.

    The link uses ?wid= (see website/main.py's _resolve_user), not ?uid= — a WhatsApp-only account
    has no telegram_user_id to build a ?uid= link from, and the wid magic link also establishes a
    real signed session on click, same as the filter-edit CTA."""
    apartments_url = f"{WEBSITE_URL}/apartments?wid={generate_wid_token(wa_id)}"
    if total > 0:
        whatsapp_client.send_text_message(
            wa_id,
            bot_text("onboarding.matches_found", lang, total=total, apartments_url=apartments_url),
        )
    else:
        whatsapp_client.send_text_message(
            wa_id, bot_text("onboarding.no_matches_yet", lang, apartments_url=apartments_url)
        )


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


def _handle_help_request(wa_id: str, profile_name: str | None, text: str, lang: str) -> None:
    contact_message_id = _save_help_request_sync(profile_name, wa_id, text)
    if _notify_owner_of_help_request(profile_name, wa_id, text):
        _mark_help_request_notified_sync(contact_message_id)
    whatsapp_client.send_cta_url_message(
        wa_id,
        bot_text("whatsapp.help_request_body", lang),
        bot_text("whatsapp.help_request_button", lang),
        f"{WEBSITE_URL}/contact",
    )


# Meta redelivers a webhook it didn't get a prompt 200 for — and used to, here: the whole
# onboarding turn (DB roundtrip + a Gemini call that can legitimately take up to the 10s timeout
# in todira_common/gemini_client.py, longer under Gemini's own retries before that fix) used to run
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


# 2026-09-26 real owner request: WhatsApp gives us no signal at all about the user's language
# (unlike Telegram's own language_code — see todira_common/language.py's own docstring for why
# that channel auto-detects silently instead). Every message from a WhatsApp number whose User row
# doesn't have a language set yet (a brand-new sender, or an existing user from before this column
# existed) gets this picker instead of proceeding into onboarding/chat; their FIRST reply after
# picking one continues normally. A structured WhatsApp Cloud API "list" message (up to 10 rows —
# a "reply buttons" message caps out at 3, not enough for our 5 languages) is the primary path; a
# plain-text reply matching a row's own title or its language code (in case someone types instead
# of tapping) is accepted too.
_LANGUAGE_ROW_TITLES = {
    "he": "עברית", "en": "English", "ru": "Русский", "fr": "Français", "ar": "العربية",
}
_LANGUAGE_ROW_ID_PREFIX = "lang_"
# Deliberately not per-language-keyed — we don't know the visitor's language yet, so this shows
# all 5 supported languages' own names for "which language" at once, not just Hebrew.
_LANGUAGE_PICKER_BODY = (
    "באיזו שפה תרצה שאדבר איתך? 🌍\n"
    "Which language would you like me to use?\n"
    "На каком языке вам удобнее?\n"
    "Quelle langue préférez-vous ?\n"
    "ما هي اللغة التي تفضلها؟"
)
_LANGUAGE_PICKER_BUTTON = "בחר שפה 🌍"


def _send_language_picker(wa_id: str) -> None:
    rows = [(f"{_LANGUAGE_ROW_ID_PREFIX}{code}", title) for code, title in _LANGUAGE_ROW_TITLES.items()]
    whatsapp_client.send_language_picker_message(
        wa_id, _LANGUAGE_PICKER_BODY, _LANGUAGE_PICKER_BUTTON, rows
    )


def _match_language_from_text(text: str) -> str | None:
    normalized = text.strip().lower()
    for code, title in _LANGUAGE_ROW_TITLES.items():
        if normalized == code or normalized == title.lower():
            return code
    return None


def _resolve_language_choice(list_reply_id: str | None, text: str | None) -> str | None:
    if list_reply_id and list_reply_id.startswith(_LANGUAGE_ROW_ID_PREFIX):
        code = list_reply_id[len(_LANGUAGE_ROW_ID_PREFIX) :]
        return code if code in SUPPORTED_LANGS else None
    if text:
        return _match_language_from_text(text)
    return None


def _ensure_language_selected_sync(
    wa_id: str, profile_name: str | None, list_reply_id: str | None, text: str | None
) -> str | None:
    """Returns the resolved language the moment user.language is already known, so the caller
    proceeds with the normal onboarding/chat flow untouched. Returns None if this message was
    instead consumed by the language-selection flow itself — either because it WAS the user's
    language pick (confirmed, saved) or because we just (re)sent the picker and are still waiting
    for one; the caller should do nothing else with the message this turn either way."""
    with get_session() as session:
        user = get_or_create_whatsapp_user(session, wa_id, profile_name)
        if user.language is not None:
            return user.language

        chosen = _resolve_language_choice(list_reply_id, text)
        if chosen is not None:
            user.language = chosen
            session.commit()
            whatsapp_client.send_text_message(wa_id, bot_text("whatsapp.language_confirmed", chosen))
            return None

    _send_language_picker(wa_id)
    return None


# Channel linking (see todira_common/channel_link.py): a `ref_xxxxxx` code generated on the
# website's /account page for an already-logged-in user, sent here as a plain text message to
# attach THIS WhatsApp number to that same existing account. Checked in _process_payload_sync
# BEFORE _ensure_language_selected_sync runs — found live 2026-09-27: a genuinely first-time
# WhatsApp sender's very first message (their link code) used to hit the language picker's own
# get_or_create_whatsapp_user first, creating a brand-new, disconnected user row for their number
# and swallowing the code entirely (_ensure_language_selected_sync returns None for anything that
# isn't a recognized language, so the code text never reached this check at all). That spurious row
# then permanently blocked any future link attempt for the same number via the conflict branch
# below. Returns True the moment the message is a live code — handled (success or conflict) either
# way — so the caller skips the language picker and the rest of the normal chat flow for it.
def _try_link_code_sync(wa_id: str, profile_name: str | None, text: str) -> bool:
    with get_session() as session:
        code_user = resolve_link_code(session, text)
        if code_user is None:
            return False
        existing = session.scalar(
            select(User).where(User.whatsapp_phone_number == wa_id)
        )
        if existing is not None and existing.id != code_user.id:
            # This WhatsApp number already has its own separate account — linking it to a
            # second one would mean merging two rows' filters/history, which we don't do
            # automatically. Leave both accounts exactly as they were.
            whatsapp_client.send_text_message(
                wa_id, bot_text("whatsapp.link_conflict", existing.language)
            )
            return True
        code_user.whatsapp_phone_number = wa_id
        if profile_name:
            code_user.first_name = code_user.first_name or profile_name
        # 2026-09-27 real owner decision, reversing the same-day opt-in-prompt fix above this
        # comment: linking WhatsApp now auto-enables whatsapp_notifications_opted_in immediately
        # (no separate /account click), on the owner's own explicit instruction after being told
        # this is exactly the "unconsented enrollment" pattern Meta's Utility/Marketing template
        # review looks for (see User.whatsapp_notifications_opted_in's own docstring) — a real
        # product/compliance tradeoff he's making knowingly, not something discovered/assumed here.
        # Safe to combine with auto-enable now that this whole backlog of already-matching listings
        # is collapsed into the ONE _send_current_matches_summary link below, right after this, and
        # scraper/notifier.py separately caps its own proactive WhatsApp push to one send per user
        # per run (see run_notifications' own docstring) — the flood this fixes is what the owner
        # actually reported and asked to fix, same night.
        code_user.whatsapp_notifications_opted_in = True
        lang = code_user.language
        filter_row = code_user.filter
        total = None
        if filter_row is not None:
            total, _new_to_show = find_new_matches_to_show(session, code_user.id, filter_row)
        session.commit()
        whatsapp_client.send_text_message(wa_id, bot_text("whatsapp.link_success", lang))
        if total is not None:
            _send_current_matches_summary(wa_id, lang, total)
        return True


def _handle_incoming_text_sync(wa_id: str, profile_name: str | None, text: str) -> None:
    with get_session() as session:
        user = get_or_create_whatsapp_user(session, wa_id, profile_name)
        lang = user.language or DEFAULT_LANG

        if looks_like_help_request(text):
            _handle_help_request(wa_id, profile_name, text, lang)
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
                text, current_filter, cities.CITIES, profile_name, lang
            )
            if result is None:
                whatsapp_client.send_text_message(wa_id, bot_text("whatsapp.error", lang))
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

            whatsapp_client.send_text_message(
                wa_id, result.get("response_message") or bot_text("whatsapp.chat_default_ack", lang)
            )
            return

        # dict(...) copy, not the loaded JSONB dict itself: mutating that in place and assigning it
        # back is the SAME object to SQLAlchemy (no change detected, no UPDATE) — so every turn
        # after the first silently lost its progress. Found 2026-09-30 in a code-review pass.
        state = dict(user.pending_onboarding_state or _EMPTY_ONBOARDING_STATE)
        result = gemini_client.parse_onboarding_message(text, state, cities.CITIES, lang)

        if result is None:
            whatsapp_client.send_text_message(wa_id, bot_text("whatsapp.error", lang))
            return

        for key in _EMPTY_ONBOARDING_STATE:
            if key in result:
                state[key] = result[key]

        whatsapp_client.send_text_message(
            wa_id, result.get("response_message") or bot_text("whatsapp.onboarding_default_ack", lang)
        )

        if result.get("missing_required") or not state["deal_type"] or not state["cities"]:
            user.pending_onboarding_state = state
            session.commit()
            return

        new_filter = Filter(
            user_id=user.id,
            deal_type=state["deal_type"],
            cities=state["cities"],
            rooms_min=state["rooms_min"],
            rooms_max=state["rooms_max"],
            price_min=int(state["price_min"]) if state["price_min"] is not None else None,
            price_max=int(state["price_max"]) if state["price_max"] is not None else None,
            keywords=state["keywords"],
        )
        session.add(new_filter)
        user.pending_onboarding_state = None
        # 2026-09-27: auto-enabled here too, same owner decision/tradeoff as _try_link_code_sync's
        # own comment on this — the brand-new-signup path and the existing-account-link path now
        # behave identically (WhatsApp connected implies opted in, immediately, no separate step).
        user.whatsapp_notifications_opted_in = True
        filter_row = new_filter
        try:
            session.commit()
        except IntegrityError:
            # 2026-09-25 real bug fix, found via a live code-review pass: Filter.user_id is
            # unique, and this webhook is stateless between requests — two genuinely concurrent
            # deliveries for the same new user's onboarding-completing messages (Meta can and does
            # deliver two rapid messages as separate webhook POSTs, each its own BackgroundTask)
            # could both reach this exact point before either commits. The losing request used to
            # have this whole per-message try/except (see _process_payload_sync) swallow the
            # IntegrityError silently — the user got no reply at all for that message, looking
            # like their onboarding just hung. Same "the other request already finished the job,
            # just confirm it" resolution as get_or_create_user/get_or_create_whatsapp_user.
            session.rollback()
            # The OTHER (winning) request's row, not new_filter above — that one was never
            # actually persisted, this session's own copy of it is stale after the rollback.
            filter_row = session.scalar(select(Filter).where(Filter.user_id == user.id))
            if filter_row is None:
                raise

        whatsapp_client.send_text_message(wa_id, bot_text("whatsapp.onboarding_complete", lang))
        _send_filter_edit_prompt(wa_id, lang)
        total, _new_to_show = find_new_matches_to_show(session, user.id, filter_row)
        session.commit()
        _send_current_matches_summary(wa_id, lang, total)


# --- Zero-cost WhatsApp (2026-10-02) -----------------------------------------------------------
# Every inbound message (text or button tap) reopens WhatsApp's free 24h window, so it is stamped on
# the user's row here; scraper/notifier.py only ever sends inside that window (never a paid
# template), and scraper/whatsapp_checkin.py asks "still looking?" near the end of each window so the
# user taps a button and the window reopens. The button ids below are shared with that module.
CHECKIN_CONTINUE_ID = "checkin_continue"
CHECKIN_FOUND_ID = "checkin_found"
CHECKIN_STOP_ID = "checkin_stop"
_CHECKIN_BUTTON_IDS = {CHECKIN_CONTINUE_ID, CHECKIN_FOUND_ID, CHECKIN_STOP_ID}
_RESUME_WORDS = {"המשך", "continue", "продолжить", "continuer", "متابعة", "start", "חידוש"}


def _message_sent_at(message: dict) -> dt.datetime | None:
    """When the USER sent this message, per Meta's own `timestamp` (epoch seconds). Used instead of
    "now" so a webhook Meta redelivers hours late can never make the 24h window look fresher than it
    really is (which could let a message go out after the window closed)."""
    try:
        return dt.datetime.fromtimestamp(int(message.get("timestamp")), dt.timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


# The one-link "while you were away" summary covers listings first seen since the user's previous
# message - however long that was (hours, days, weeks: no fixed window). When the previous message time
# is unknown (a user from before the column existed, or an explicit "continue") there is no cutoff at
# all: it covers everything the user has not been shown yet.


_NO_CUTOFF = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)


def _touch_inbound_sync(wa_id: str, sent_at: dt.datetime | None = None) -> dt.datetime | None:
    """Stamps the user's last inbound message. Returns None normally; when this message REOPENED a
    closed window for an opted-in user it returns the moment to summarize FROM (their previous
    message time, whatever the gap) - or, when that time is unknown, the epoch (no cutoff) — the caller then sends the one-link summary
    of what was found while they were away. A number with no user row yet is a no-op (the row is
    created later in this same message's handling; its first stamp lands on their next message)."""
    now = dt.datetime.now(dt.timezone.utc)
    stamp = min(sent_at, now) if sent_at is not None else now
    with get_session() as session:
        user = session.scalar(select(User).where(User.whatsapp_phone_number == wa_id))
        if user is None:
            return None
        previous = user.whatsapp_last_inbound_at
        was_closed = not window_open(previous, now)
        # Never move the stamp backwards (a late redelivery of an older message).
        if previous is None or stamp > (previous if previous.tzinfo else previous.replace(tzinfo=dt.timezone.utc)):
            user.whatsapp_last_inbound_at = stamp
        session.commit()
        if not (was_closed and user.whatsapp_notifications_opted_in):
            return None
        previous_utc = None if previous is None else (previous if previous.tzinfo else previous.replace(tzinfo=dt.timezone.utc))
        return previous_utc or _NO_CUTOFF


def _touch_inbound_safely(wa_id: str, sent_at: dt.datetime | None = None) -> dt.datetime | None:
    """_touch_inbound_sync, but a DB hiccup in the stamp must never block handling the message."""
    try:
        return _touch_inbound_sync(wa_id, sent_at)
    except Exception:
        logger.exception("Could not stamp WhatsApp inbound time")
        return None


def _send_missed_digest_sync(wa_id: str, since: dt.datetime | None = None) -> None:
    """ONE free-form message with one link, covering the matching listings first seen since `since`
    (default: no cutoff) that the user hasn't been shown yet — found while their window was
    closed and nothing could be sent. Marks exactly those shown, so it can never repeat and the
    scraper never re-sends them one by one. Older unseen matches stay on the website."""
    with get_session() as session:
        user = session.scalar(select(User).where(User.whatsapp_phone_number == wa_id))
        if user is None:
            return
        filter_row = session.scalar(select(Filter).where(Filter.user_id == user.id))
        if filter_row is None:
            return
        _total, new_to_show = find_new_matches_to_show(session, user.id, filter_row, since=since)
        session.commit()
        lang = user.language or DEFAULT_LANG
    if not new_to_show:
        return
    whatsapp_client.send_text_message(
        wa_id,
        bot_text(
            "whatsapp.missed_digest", lang,
            total=len(new_to_show),
            url=f"{WEBSITE_URL}/apartments?wid={generate_wid_token(wa_id)}",
        ),
    )


def _set_opt_in_sync(wa_id: str, opted_in: bool) -> str | None:
    """Returns the user's language (None if there is no such user)."""
    with get_session() as session:
        user = session.scalar(select(User).where(User.whatsapp_phone_number == wa_id))
        if user is None:
            return None
        user.whatsapp_notifications_opted_in = opted_in
        session.commit()
        return user.language or DEFAULT_LANG


def _handle_checkin_button_sync(wa_id: str, button_id: str) -> None:
    """The user's tap on a check-in button (scraper/whatsapp_checkin.py). The tap itself already
    reopened the window (_touch_inbound_sync); this just answers it."""
    if button_id == CHECKIN_CONTINUE_ID:
        lang = _set_opt_in_sync(wa_id, True)
        if lang is not None:
            whatsapp_client.send_text_message(wa_id, bot_text("whatsapp.checkin_continue_ack", lang))
    elif button_id == CHECKIN_FOUND_ID:
        lang = _set_opt_in_sync(wa_id, False)
        if lang is not None:
            whatsapp_client.send_text_message(wa_id, bot_text("whatsapp.checkin_found_ack", lang))
    elif button_id == CHECKIN_STOP_ID:
        lang = _set_opt_in_sync(wa_id, False)
        if lang is not None:
            whatsapp_client.send_text_message(wa_id, bot_text("whatsapp.checkin_stop_ack", lang))


def _try_resume_sync(wa_id: str, text: str) -> bool:
    """A user who stopped (or found an apartment) sends "המשך" to start again. True when handled."""
    if text.strip().strip("״\"'.!").lower() not in _RESUME_WORDS:
        return False
    with get_session() as session:
        user = session.scalar(select(User).where(User.whatsapp_phone_number == wa_id))
        if user is None or user.whatsapp_notifications_opted_in:
            return False
        if session.scalar(select(Filter).where(Filter.user_id == user.id)) is None:
            return False
        user.whatsapp_notifications_opted_in = True
        session.commit()
        lang = user.language or DEFAULT_LANG
    whatsapp_client.send_text_message(wa_id, bot_text("whatsapp.resume_ack", lang))
    return True



# error code -> time.monotonic() of the last owner alert, so a burst of failures (every message of a
# scraper run fails the same way) produces ONE Telegram message, not hundreds.
_DELIVERY_ALERT_COOLDOWN_SECONDS = 6 * 60 * 60
_last_delivery_alert_at: dict[object, float] = {}
_delivery_alert_lock = threading.Lock()


def _alert_owner_of_delivery_failure(errors: list[tuple]) -> None:
    """Best-effort Telegram message to the owner when Meta reports a WhatsApp send as failed — found
    2026-10-01: a WhatsApp Business account with unsettled payments (Meta error 131042) silently
    rejected every message for hours while each send still answered HTTP 200, and nothing told the
    owner. At most one alert per error code per _DELIVERY_ALERT_COOLDOWN_SECONDS. Never raises."""
    if not TELEGRAM_BOT_TOKEN or not OWNER_TELEGRAM_USER_ID:
        return
    now = time.monotonic()
    fresh = []
    with _delivery_alert_lock:
        for code, title, details in errors:
            last = _last_delivery_alert_at.get(code)
            if last is None or now - last >= _DELIVERY_ALERT_COOLDOWN_SECONDS:
                _last_delivery_alert_at[code] = now
                fresh.append((code, title, details))
    if not fresh:
        return
    lines = ["⚠️ <b>וואטסאפ: Meta מדווחת שהודעות לא נמסרות</b>", ""]
    for code, title, details in fresh:
        lines.append(f"קוד {html.escape(str(code))}: {html.escape(str(title))}")
        if details:
            lines.append(html.escape(str(details)))
    try:
        httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": OWNER_TELEGRAM_USER_ID, "text": "\n".join(lines), "parse_mode": "HTML"},
            timeout=10.0,
        )
    except httpx.HTTPError:
        logger.exception("Failed to push a WhatsApp delivery-failure alert to Telegram")


def _trip_billing_breaker(category, pricing_model, pricing_type) -> None:
    """Meta says a message WE sent is BILLABLE. The owner's rule is zero cost, so this pauses every
    proactive WhatsApp send (todira_common/whatsapp_guard.py) and alerts the owner. Never raises, and
    never logs a recipient or message id."""
    reason = f"billable WhatsApp message reported by Meta (category={category}, type={pricing_type}, model={pricing_model})"
    logger.error("WhatsApp BILLING breaker tripped: %s", reason)
    try:
        with get_session() as session:
            already_paused = whatsapp_guard.is_paused(session)
            if not already_paused:
                whatsapp_guard.pause(session, reason)
        if not already_paused:
            alert_owner(
                "🛑 <b>וואטסאפ הושהה אוטומטית</b>\n"
                f"מטא דיווחה על הודעה שמחויבת בתשלום (קטגוריה: {html.escape(str(category))}). "
                "כל השליחות היזומות נעצרו עד שתחליט להמשיך."
            )
    except Exception:
        logger.exception("Could not trip the WhatsApp billing breaker")


def _log_delivery_statuses(value: dict) -> None:
    """Meta reports what happened to every message WE sent (sent/delivered/read/failed) as a
    "statuses" entry on this same webhook. They used to be dropped silently, which made a message
    Meta accepted (HTTP 200) but never delivered completely invisible — found 2026-10-01 when a real
    owner stopped receiving match pushes while every send still answered 200. Logs only the status,
    the pricing category and, for a failure, Meta's own error code/title/details. Never the
    recipient or the message id: a wamid base64-encodes the recipient's phone number."""
    for status in value.get("statuses") or []:
        pricing = status.get("pricing") or {}
        category = pricing.get("category")
        if pricing.get("billable") is True:
            _trip_billing_breaker(category, pricing.get("pricing_model"), pricing.get("type"))
        if status.get("status") == "failed":
            errors = [
                (error.get("code"), error.get("title"), (error.get("error_data") or {}).get("details"))
                for error in status.get("errors") or []
            ]
            logger.warning("WhatsApp delivery FAILED (category=%s): %s", category, errors)
            _alert_owner_of_delivery_failure(errors)
        else:
            logger.info("WhatsApp delivery status=%s (category=%s)", status.get("status"), category)


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
            _log_delivery_statuses(value)
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

                    # Every inbound message (any type) reopens the free 24h window.
                    reopened_window = _touch_inbound_safely(wa_id, _message_sent_at(message))

                    msg_type = message.get("type")
                    list_reply_id = None
                    text = None
                    if msg_type == "interactive":
                        interactive = message.get("interactive") or {}
                        button_reply_id = (interactive.get("button_reply") or {}).get("id")
                        if button_reply_id in _CHECKIN_BUTTON_IDS:
                            _handle_checkin_button_sync(wa_id, button_reply_id)
                            if reopened_window and button_reply_id == CHECKIN_CONTINUE_ID:
                                _send_missed_digest_sync(wa_id, reopened_window)
                            continue
                        list_reply_id = (interactive.get("list_reply") or {}).get("id")
                    elif msg_type == "text":
                        text = (message.get("text") or {}).get("body", "")

                    if msg_type == "text" and text and _try_resume_sync(wa_id, text):
                        _send_missed_digest_sync(wa_id)
                        continue

                    # A link code (see _try_link_code_sync's own docstring) is checked before
                    # anything else, including the language picker below — it must never fall
                    # into get_or_create_whatsapp_user first, or the code is silently swallowed
                    # and a spurious, disconnected user row is created for the sender's number.
                    if msg_type == "text" and text and _try_link_code_sync(wa_id, contacts.get(wa_id), text):
                        continue

                    # Every message goes through this FIRST, regardless of type — a brand-new
                    # WhatsApp sender (or an existing one from before this column existed) gets the
                    # language picker instead of anything else, even a non-text message. See its
                    # own docstring for the exact contract.
                    lang = _ensure_language_selected_sync(wa_id, contacts.get(wa_id), list_reply_id, text)
                    if lang is None:
                        continue

                    if msg_type != "text":
                        whatsapp_client.send_text_message(
                            wa_id, bot_text("whatsapp.unsupported_message_type", lang)
                        )
                        continue
                    if message.get("id"):
                        _fire_typing_indicator(message["id"])
                    _handle_incoming_text_sync(wa_id, contacts.get(wa_id), text)
                    if reopened_window:
                        _send_missed_digest_sync(wa_id, reopened_window)
                except Exception:
                    logger.exception(
                        "Error processing one WhatsApp message in the batch (id=%s) — "
                        "continuing with the rest of the batch",
                        message.get("id"),
                    )
                finally:
                    # Second stamp, AFTER handling: a number that only gets a user row (or gets
                    # linked to one) while this very message is processed had nothing to stamp at the
                    # top of the loop, yet its window is open right now.
                    if message.get("from"):
                        _touch_inbound_safely(message["from"], _message_sent_at(message))


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
