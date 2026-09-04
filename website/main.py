"""ToDira public website (Phase 2) — FastAPI, server-rendered Jinja2 templates, reuses
common/dorin_common (same models/matching/db as the bot and scraper).

AUTH: three ways in, and all three resolve to the same signed session cookie in the end.
  1. Real login via Google — /auth/google/start + /auth/google/callback (2026-09-04), the actual
     replacement UI referenced in #2's history below. This is a LINK to an existing user, not a
     third standalone identity: a brand-new Google sign-in with no `users.google_sub` match and no
     ?uid= in flight gets sent to the bot, same as #2's own "never started the bot" case — Google
     alone can't create a filter. The valuable case is linking: reached with `?uid=` (a visitor
     only viewing a page via their own bot deep link, no real session yet) it stashes that uid in
     the signed session cookie (never the OAuth `state` param — state is attacker-visible, the
     session cookie is cryptographically signed), and on callback links `google_sub` to that SAME
     existing user row. Every later "Sign in with Google" then resolves straight to it — solving
     iOS Safari's actual complaint below without touching Telegram's own flaky redirect at all.
  2. /auth/telegram/callback, which verifies a Telegram Login Widget-shaped HMAC callback and sets
     the session cookie to the internal `users.id` PK (deliberately NOT "telegram_user_id" or
     anything Telegram-specific, so a login provider's own route just needs to resolve its own user
     identity to the same `users.id` and populate the same session key —
     `request.session["user_id"]` — no changes needed here; #1 above is exactly that).
     As of 2026-09-02 nothing in the UI links to this route anymore — the header/`need_uid.html`
     widget embed was removed (real complaint: on iOS Safari's in-app floating browser, Telegram's
     own oauth.telegram.org handshake behind the widget re-asked for phone verification on nearly
     every visit instead of staying logged in — a problem in Telegram's redirect flow itself, not
     in this route's session handling). The route/`_verify_telegram_auth` are kept as-is (untouched,
     still fully tested) as a fallback login path even though #1 is now the header's own button.
  3. `?uid=` query param, via a direct `https://t.me/AmirDirotBot` deep link (bot onboarding/filter
     flows already send these) — the ONLY way in from Telegram now, matching how the reference
     product (dorin.app) treats "Continue with Telegram": open the bot directly, no OAuth handshake
     at all. Not secure on its own (anyone who knows/guesses a uid can view that user's
     filter/liked listings via a raw link), but the real session cookie above is what protects a
     page once you've actually logged in via #1 or #2 — and is also exactly the trust level #1's
     linking flow relies on to prove "this visitor really is that uid" (see #1's own comment).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import hmac
import logging
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from dorin_common.access import PLAN_PRICES_ILS, extend_paid_until, has_full_access
from dorin_common.channel_link import generate_link_code
from dorin_common.cities import CITIES
from dorin_common.db import get_session
from dorin_common.matching import evaluate
from dorin_common.models import ContactMessage, Filter, Listing, Payment, User, UserListingAction
from fastapi import FastAPI, Form, Request

import grow_client
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from i18n import (
    DEFAULT_LANG,
    FURNITURE_LABELS,
    LANG_LABELS,
    PROPERTY_TYPE_LABELS,
    RTL_LANGS,
    SAFE_ROOM_LABELS,
    SUPPORTED_LANGS,
    get_lang,
    make_translator,
    relative_time_label,
)
from whatsapp_webhook import router as whatsapp_router

# Matches bot/main.py's own logging.basicConfig — without this, INFO-level messages are invisible
# in pod logs by default (root logger stays at WARNING), which made a real bug (a Telegram push
# silently not firing) much harder to diagnose than it needed to be. Found and fixed 2026-09-01
# alongside the OWNER_TELEGRAM_USER_ID bug below.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx's own "httpx" logger emits an INFO line per request with the FULL request URL — and
# _notify_owner_sync below calls api.telegram.org/bot<TOKEN>/sendMessage directly, with the live
# bot token embedded in the URL path. That's a leak, not the useful diagnostic this file's comment
# above originally relied on httpx's auto-logging for (2026-09-01) — _notify_owner_sync already
# logs its own status/body on failure and exceptions explicitly (see below), so silencing httpx
# specifically loses nothing here. Same issue found and fixed in scraper/main.py and bot/main.py
# (there: a ZenRows key and the Telegram bot token via python-telegram-bot's own httpx use)
# 2026-09-03.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent

# Falls back to an insecure dev-only value so `uvicorn website.main:app` and the test suite work
# without extra setup; production always sets this via the SESSION_SECRET_KEY Kubernetes secret
# (see charts/todira/templates/bot-secret.yaml) — a login session signed with the fallback would
# be forgeable, so this must never actually be used outside local dev/tests.
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "dev-only-insecure-session-key")

app = FastAPI(title="טודירה")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY, same_site="lax")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(whatsapp_router)
templates = Jinja2Templates(directory=BASE_DIR / "templates")

LANG_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year — a site-wide preference, not per-session

# /contact form notification — reuses the bot's own TELEGRAM_BOT_TOKEN (no extra secret needed) to
# push a message straight to the owner's Telegram chat, since that's already the one channel this
# whole product treats as "always checked." OWNER_TELEGRAM_USER_ID is optional and unset by
# default: without it, messages are still safely stored in the DB (see /contact below), just not
# proactively pushed — find your own numeric Telegram ID via a bot like @userinfobot, then set it.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OWNER_TELEGRAM_USER_ID = os.environ.get("OWNER_TELEGRAM_USER_ID")

# Google Sign-In (login redesign step 2) — a real, persistent website session, independent of
# Telegram's own login-widget flow (which iOS Safari's in-app browser kept re-asking to re-verify,
# see this file's module docstring). Both optional/unset by default so a deploy before the owner
# creates a Google Cloud OAuth Client doesn't break — /auth/google/start just 400s until then.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
# Built from a fixed env var, never from the incoming request's own scheme/host — Caddy terminates
# TLS in front of this pod and proxies plain HTTP internally, so trusting the request could produce
# an `http://` redirect_uri that doesn't match what's registered in the Google Cloud Console
# (redirect_uri must match EXACTLY, or Google rejects the whole flow).
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://todira.duckdns.org")

# Cross-channel linking (2026-09-05, /account below) — the actual displayable WhatsApp number
# (E.164 digits, no leading '+') to build a `wa.me/<number>?text=ref_xxxxxx` deep link. Distinct
# from WHATSAPP_PHONE_NUMBER_ID (whatsapp_client.py) — that's the Cloud API's own internal id
# used to call the Graph API, not something a person can dial or a wa.me link can use. Optional:
# without it, /account still shows the Telegram linking option, just not the WhatsApp one.
WHATSAPP_PUBLIC_NUMBER = os.environ.get("WHATSAPP_PUBLIC_NUMBER", "").strip()

# Informal Bit/PayBox payment (2026-09-05 — the owner decided against עוסק פטור/Grow for now, see
# /upgrade/pay below) — the owner's own phone number for Bit and, optionally, a PayBox payment
# link he generates himself from the PayBox app. Deliberately NOT a "click to open the app
# pre-filled" deep link: neither Bit nor PayBox publish a documented URL scheme for that (checked
# — even commercial Bit-payment WooCommerce plugins just show a phone number + QR code and rely on
# the customer typing the amount manually), so this only ever displays plain instructions. Both
# optional; /upgrade/pay falls back to a generic "send the amount via Bit" hint when unset.
OWNER_BIT_PHONE = os.environ.get("OWNER_BIT_PHONE", "").strip()
OWNER_PAYBOX_URL = os.environ.get("OWNER_PAYBOX_URL", "").strip()


def _notify_owner_sync(name: str, email: str, message: str, telegram_user_id: int | None) -> bool:
    """Best-effort — returns whether the Telegram push succeeded. Never raises: a broken/missing
    token or chat id must never lose the contact message itself (already committed to the DB by
    the caller before this runs)."""
    if not TELEGRAM_BOT_TOKEN or not OWNER_TELEGRAM_USER_ID:
        return False
    lines = ["📬 <b>הודעה חדשה מהאתר (טודירה)</b>"]
    if name:
        lines.append(f"שם: {name}")
    if email:
        lines.append(f"אימייל: {email}")
    if telegram_user_id:
        lines.append(f"Telegram user ID: {telegram_user_id}")
    lines.append("")
    lines.append(message)
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": OWNER_TELEGRAM_USER_ID,
                "text": "\n".join(lines),
                "parse_mode": "HTML",
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            # Telegram rejecting the call (e.g. "chat not found" for a wrong/never-messaged-the-
            # bot OWNER_TELEGRAM_USER_ID) is a normal HTTP response, not an httpx exception - was
            # previously swallowed here with no log line at all, making a bad ID silently
            # indistinguishable from "working fine." Logged (not raised) since this stays best-
            # effort: the contact message itself is already safely in the DB by the time this runs.
            logger.warning(
                "Telegram rejected the /contact owner-notify push: status=%d body=%s",
                resp.status_code,
                resp.text[:500],
            )
        return resp.status_code == 200
    except httpx.HTTPError:
        logger.exception("Failed to push /contact submission to Telegram")
        return False


def _current_user_summary(request: Request) -> dict | None:
    """For the header's login/logout UI, shown on every page — a light column-only lookup (no
    relationships touched) so the returned dict is safe to read from after the DB session closes.
    Returns None both when logged out and when a stale session references a deleted user."""
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    with get_session() as session:
        row = session.execute(
            select(User.telegram_user_id, User.first_name, User.telegram_username).where(
                User.id == user_id
            )
        ).first()
    if row is None:
        return None
    return {
        "telegram_user_id": row.telegram_user_id,
        "first_name": row.first_name,
        "telegram_username": row.telegram_username,
    }


def _render(request: Request, template_name: str, context: dict, status_code: int = 200) -> Response:
    """Every page goes through this: resolves the viewer's language (?lang= > cookie > Hebrew),
    injects lang/dir/t/lang switcher data into the template context, and — only when the request
    explicitly asked for a language via ?lang= — persists it to a cookie so it survives to the
    next page without every internal link needing to carry ?lang= itself (uid already has to be
    threaded through links for auth, but lang is a site-wide preference, a cookie fits better).
    Also injects `current_user` (or None) so the header's login/logout UI is correct on every page,
    not just the ones that already resolve a full user for their own content.
    """
    lang = get_lang(request)
    current_user = _current_user_summary(request)
    is_owner = current_user is not None and _is_owner_id(current_user["telegram_user_id"])
    response = templates.TemplateResponse(
        request,
        template_name,
        {
            **context,
            "lang": lang,
            "dir": "rtl" if lang in RTL_LANGS else "ltr",
            "t": make_translator(lang),
            "posted_ago": lambda posted_at: relative_time_label(posted_at, lang),
            "supported_langs": SUPPORTED_LANGS,
            "lang_labels": LANG_LABELS,
            "current_user": current_user,
            "is_owner": is_owner,
        },
        status_code=status_code,
    )
    requested_lang = request.query_params.get("lang")
    if requested_lang in SUPPORTED_LANGS:
        response.set_cookie("lang", requested_lang, max_age=LANG_COOKIE_MAX_AGE, samesite="lax")
    return response


# /filter form option labels now live in i18n.py (PROPERTY_TYPE_LABELS etc.), keyed by language —
# moved out of this file once the site stopped being Hebrew-only.


@app.exception_handler(404)
async def not_found(request: Request, exc: StarletteHTTPException):
    return _render(request, "404.html", {}, status_code=404)


def _get_user_by_uid(session, uid: int) -> User | None:
    return session.scalar(select(User).where(User.telegram_user_id == uid))


def _resolve_user(request: Request, session, uid: int | None) -> User | None:
    """Prefer the signed session cookie (real login) over the legacy ?uid= query param — the
    query param stays supported unchanged so existing bot deep links keep working.

    Also completes a PENDING Google link (2026-09-05 fix): if this same browser recently signed
    in with Google but had no ?uid= in flight to link to at that moment (auth_google_callback
    stashed the google_sub in the signed session cookie instead of just dead-ending at the bot,
    see that route's own comment), the moment a real uid resolves here — e.g. the visitor opened
    the bot as instructed and came back via any ?uid= link — the link is finished AND a real
    session is established right here, so they don't have to repeat the Google sign-in and don't
    get asked to log in again on the next visit. Only fires when a pending_google_sub genuinely
    exists in THIS session, so a plain uid visit with no prior Google attempt is completely
    unaffected — still exactly as low-trust/ephemeral as the module docstring describes."""
    session_user_id = request.session.get("user_id")
    if session_user_id is not None:
        user = session.get(User, session_user_id)
        if user is not None:
            return user
    if uid is not None:
        user = _get_user_by_uid(session, uid)
        if user is not None:
            pending_google_sub = request.session.get("pending_google_sub")
            if pending_google_sub and user.google_sub is None:
                user.google_sub = pending_google_sub
                session.commit()
                request.session.pop("pending_google_sub", None)
                request.session["user_id"] = user.id
        return user
    return None


def _verify_telegram_auth(params: dict, bot_token: str) -> bool:
    """Validates the Telegram Login Widget callback per Telegram's own algorithm:
    https://core.telegram.org/widgets/login#checking-authorization
    HMAC-SHA256 over the sorted `key=value` fields (excluding `hash`), keyed by SHA256(bot_token).
    Also rejects a callback whose auth_date is more than a day old, so an old, leaked/cached
    callback URL can't be replayed to establish a fresh session."""
    received_hash = params.get("hash")
    if not received_hash:
        return False
    check_fields = {k: v for k, v in params.items() if k != "hash"}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(check_fields.items()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        return False
    try:
        auth_date = int(params.get("auth_date", "0"))
    except ValueError:
        return False
    return time.time() - auth_date <= 60 * 60 * 24


@app.get("/")
def home(request: Request):
    return _render(request, "home.html", {})


@app.get("/login")
def login(request: Request, next: str = "/apartments"):
    """A dedicated screen (2026-09-05 request) instead of the header's own small Google-only
    button — Google/Telegram/WhatsApp shown as three separate, equally prominent "continue with"
    options, matching the reference product's own login screen. Already-logged-in visitors skip
    straight past it. Telegram/WhatsApp still just open that platform directly (there's no
    "sign in with Telegram/WhatsApp" that logs into THIS site without leaving it — Telegram's own
    Login Widget exists (see _verify_telegram_auth below) but was pulled from the UI after a real
    iOS Safari reliability complaint, see this file's module docstring); the payoff for choosing
    Google here shows up once you're actually signed in with it — see _resolve_user's own comment
    on why coming back from either of those two also finishes a pending Google link automatically."""
    if request.session.get("user_id") is not None:
        return RedirectResponse(_safe_next(next), status_code=303)
    return _render(
        request,
        "login.html",
        {"next": _safe_next(next), "whatsapp_public_number": WHATSAPP_PUBLIC_NUMBER},
    )


@app.get("/terms")
def terms(request: Request):
    return _render(request, "terms.html", {})


@app.get("/privacy")
def privacy(request: Request):
    return _render(request, "privacy.html", {})


@app.get("/accessibility")
def accessibility(request: Request):
    return _render(request, "accessibility.html", {})


def _safe_next(next: str) -> str:
    return next if next.startswith("/") and not next.startswith("//") else "/apartments"


@app.get("/auth/telegram/callback")
def auth_telegram_callback(request: Request, next: str = "/apartments"):
    params = dict(request.query_params)
    params.pop("next", None)
    if not TELEGRAM_BOT_TOKEN or not _verify_telegram_auth(params, TELEGRAM_BOT_TOKEN):
        logger.warning("Rejected Telegram login callback: missing token or invalid signature")
        return _render(request, "auth_error.html", {}, status_code=400)

    telegram_user_id = int(params["id"])
    with get_session() as session:
        user = _get_user_by_uid(session, telegram_user_id)
        user_pk = user.id if user is not None else None

    if user_pk is None:
        # Verified as a real Telegram account, but one that's never started the bot — there's no
        # filter/account for the website to show yet, so send them to onboard there first.
        return RedirectResponse("https://t.me/AmirDirotBot", status_code=303)

    request.session["user_id"] = user_pk
    return RedirectResponse(_safe_next(next), status_code=303)


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


@app.get("/auth/google/start")
def auth_google_start(request: Request, next: str = "/apartments", uid: int | None = None):
    """Kicks off the Google OAuth Authorization Code flow. `uid` (present when reached from a page
    the visitor is only viewing via their own ?uid= bot deep link, not a real session yet) is
    stashed in the signed session cookie, not the OAuth `state` param — state is visible to/
    replayable by anyone who intercepts the redirect, while the session cookie is cryptographically
    signed (SESSION_SECRET_KEY), so a forged uid can't be smuggled in to link someone else's
    account. See /auth/google/callback for how it's used."""
    if not GOOGLE_CLIENT_ID:
        logger.warning("Rejected /auth/google/start: GOOGLE_CLIENT_ID is not configured")
        return _render(request, "auth_error.html", {}, status_code=400)

    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    request.session["oauth_next"] = _safe_next(next)
    if uid is not None:
        request.session["oauth_link_uid"] = uid
    else:
        request.session.pop("oauth_link_uid", None)

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{WEBSITE_URL}/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=303)


@app.get("/auth/google/callback")
def auth_google_callback(
    request: Request, code: str | None = None, state: str | None = None, error: str | None = None
):
    expected_state = request.session.pop("oauth_state", None)
    link_uid = request.session.pop("oauth_link_uid", None)
    next_url = request.session.pop("oauth_next", "/apartments")

    if (
        error
        or not code
        or not GOOGLE_CLIENT_ID
        or not GOOGLE_CLIENT_SECRET
        or not expected_state
        or state != expected_state
    ):
        logger.warning(
            "Rejected Google login callback: error=%s missing_code=%s bad_state=%s",
            error,
            code is None,
            state != expected_state,
        )
        return _render(request, "auth_error.html", {}, status_code=400)

    try:
        token_resp = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": f"{WEBSITE_URL}/auth/google/callback",
                "grant_type": "authorization_code",
            },
            timeout=10.0,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]
        userinfo_resp = httpx.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        userinfo_resp.raise_for_status()
        google_sub = userinfo_resp.json()["sub"]
    except (httpx.HTTPError, KeyError):
        logger.exception("Failed to complete the Google OAuth token/userinfo exchange")
        return _render(request, "auth_error.html", {}, status_code=400)

    session_user_id = request.session.get("user_id")
    with get_session() as session:
        user = session.scalar(select(User).where(User.google_sub == google_sub))
        matched_via = "google_sub" if user is not None else None
        if user is None and link_uid is not None:
            # First time this Google account signs in while viewing a page via the visitor's own
            # ?uid= deep link — link it to that SAME existing Telegram/WhatsApp-created account so
            # every later "Sign in with Google" resolves straight back to it.
            user = _get_user_by_uid(session, link_uid)
            if user is not None:
                user.google_sub = google_sub
                session.commit()
                matched_via = "link_uid"
        if user is None and session_user_id is not None:
            # 2026-09-05 fix: the visitor may already be in an authenticated session (e.g. they
            # signed in via Telegram earlier, or a prior Google attempt in this same browser
            # already established one) even though this particular attempt carries no usable
            # link_uid — e.g. the "קשר את Google לחשבון" link was rendered before Telegram
            # finished linking, or the uid param otherwise got lost in transit. Trust the signed
            # session cookie over a missing/stale query param: link this new Google account
            # straight to whoever is already logged in here, instead of stranding them on the
            # google_pending screen while the header plainly shows them as logged in.
            user = session.get(User, session_user_id)
            if user is not None:
                if user.google_sub is None:
                    user.google_sub = google_sub
                    session.commit()
                    matched_via = "session_user_id"
                else:
                    # Already linked to a different Google account — don't silently overwrite it.
                    user = None
        user_pk = user.id if user is not None else None
        logger.info(
            "Google OAuth callback resolved: matched_via=%s link_uid=%s session_user_id=%s user_pk=%s",
            matched_via,
            link_uid,
            session_user_id,
            user_pk,
        )

    if user_pk is None:
        # A real Google account, but not yet linked to any Telegram/WhatsApp-created user, and no
        # ?uid= was in flight right now to link it to (same restriction /auth/telegram/callback
        # already has: Google alone can't create a filter). 2026-09-05 fix: this used to just
        # silently bounce to the bot with zero explanation and zero way back — a real dead end,
        # since the plain header "Sign in with Google" button (shown whenever there's no uid in
        # the URL) could then NEVER succeed for a first-time linker. Now it stashes the google_sub
        # in the signed session cookie and explains what to do; _resolve_user above finishes the
        # link (and starts a real session) automatically the moment this same browser later
        # resolves a real uid — e.g. by opening the bot as instructed and coming back.
        request.session["pending_google_sub"] = google_sub
        return _render(request, "google_pending.html", {})

    request.session["user_id"] = user_pk
    return RedirectResponse(_safe_next(next_url), status_code=303)


@app.get("/auth/logout")
def auth_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.get("/contact")
def contact(request: Request, uid: int | None = None, sent: bool = False):
    return _render(request, "contact.html", {"uid": uid, "sent": sent})


@app.post("/contact")
async def contact_submit(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    message: str = Form(""),
    uid: str = Form(""),
):
    lang = get_lang(request)
    message = message.strip()
    if not message:
        return _render(
            request, "contact.html", {"uid": uid or None, "sent": False, "error": True}
        )

    telegram_user_id = int(uid) if uid.strip().isdigit() else None

    def _save_sync() -> int:
        with get_session() as session:
            row = ContactMessage(
                name=name.strip() or None,
                email=email.strip() or None,
                message=message,
                telegram_user_id=telegram_user_id,
                source="website",
            )
            session.add(row)
            session.commit()
            return row.id

    def _mark_notified_sync(contact_message_id: int) -> None:
        with get_session() as session:
            row = session.get(ContactMessage, contact_message_id)
            if row is not None:
                row.notified_owner = True
                session.commit()

    contact_message_id = await asyncio.to_thread(_save_sync)
    # Best-effort push to the owner — fire-and-forget-ish, but awaited so a slow/failed Telegram
    # call can't leave the request hanging forever; the message is already safely in the DB above
    # regardless of whether this succeeds. notified_owner previously existed on the model but was
    # never actually set here — fixed 2026-09-01 alongside adding the bot's own contact fallback
    # (bot/handlers/contact_fallback.py), which sets the same field for its own messages.
    notified = await asyncio.to_thread(
        _notify_owner_sync, name.strip(), email.strip(), message, telegram_user_id
    )
    if notified:
        await asyncio.to_thread(_mark_notified_sync, contact_message_id)

    redirect_url = f"/contact?sent=1{f'&uid={uid}' if uid else ''}{f'&lang={lang}' if lang != DEFAULT_LANG else ''}"
    return RedirectResponse(redirect_url, status_code=303)


@app.get("/apartments")
def apartments(request: Request, uid: int | None = None):
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "apartments"})
        if user.filter is None:
            return _render(request, "no_filter.html", {"uid": user.telegram_user_id})

        listings = session.scalars(
            select(Listing)
            .where(Listing.is_delisted.is_(False))
            .order_by(Listing.scraped_at.desc())
            .limit(200)
        ).all()
        matches = [listing for listing in listings if evaluate(user.filter, listing).matched]
        # Only true when this page was actually reached via the real, signed session cookie — the
        # "insecure temporary access" notice below must not show for a real login just because a
        # stale ?uid= also happens to be sitting in the URL from an older bookmark/deep link.
        via_session = request.session.get("user_id") == user.id
        has_access = has_full_access(user, is_owner=_is_owner_id(user.telegram_user_id))

    return _render(
        request,
        "apartments.html",
        {
            "listings": matches,
            "uid": user.telegram_user_id,
            "user": user,
            "via_session": via_session,
            "has_access": has_access,
        },
    )


@app.get("/liked")
def liked(request: Request, uid: int | None = None):
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "liked"})

        liked_listing_ids = session.scalars(
            select(UserListingAction.listing_id).where(
                UserListingAction.user_id == user.id, UserListingAction.action == "liked"
            )
        ).all()
        listings = (
            session.scalars(select(Listing).where(Listing.id.in_(liked_listing_ids))).all()
            if liked_listing_ids
            else []
        )
        has_access = has_full_access(user, is_owner=_is_owner_id(user.telegram_user_id))

    return _render(
        request,
        "liked.html",
        {"listings": listings, "uid": user.telegram_user_id, "user": user, "has_access": has_access},
    )


def _is_owner_id(telegram_user_id: int | None) -> bool:
    """Gate for /admin/messages — deliberately keyed off the SAME OWNER_TELEGRAM_USER_ID secret
    that both the /contact form and the bot's contact-fallback handler already forward to, rather
    than a separate admin token/password: "who receives contact notifications" and "who can view
    the inbox on the website" should never be able to drift apart into two different people.
    String comparison (not int()) since OWNER_TELEGRAM_USER_ID is a raw secret string that could
    in principle contain non-numeric noise — this way a malformed secret just never matches
    instead of throwing."""
    return bool(OWNER_TELEGRAM_USER_ID) and str(telegram_user_id) == str(OWNER_TELEGRAM_USER_ID)


@app.get("/admin/messages")
def admin_messages(request: Request):
    """Owner-only inbox for every message from BOTH contact channels — the website's /contact
    form and the bot's free-text fallback (bot/handlers/contact_fallback.py) — since both write
    to the same contact_messages table. Requires the real signed session (Telegram Login), not
    just ?uid=, so a guessed/leaked uid link can't reach this. Renders 404 (not 403) for anyone
    else, including a logged-in non-owner, so the route's existence isn't revealed either."""
    session_user_id = request.session.get("user_id")
    with get_session() as session:
        user = session.get(User, session_user_id) if session_user_id is not None else None
        if user is None or not _is_owner_id(user.telegram_user_id):
            return _render(request, "404.html", {}, status_code=404)

        messages = session.scalars(
            select(ContactMessage).order_by(ContactMessage.created_at.desc()).limit(200)
        ).all()

    return _render(request, "admin_messages.html", {"messages": messages})


def _require_owner(request: Request, session) -> User | None:
    """Same gate as /admin/messages (real signed session, not ?uid=; 404 not 403 for anyone
    else) — shared here so /admin/users doesn't re-derive it slightly differently."""
    session_user_id = request.session.get("user_id")
    user = session.get(User, session_user_id) if session_user_id is not None else None
    if user is None or not _is_owner_id(user.telegram_user_id):
        return None
    return user


@app.get("/admin/users")
def admin_users(request: Request):
    """Owner-only — lets the owner grant/revoke free access (independent of trial/payment) to any
    user, from any device, regardless of which channel they signed up through (Telegram/WhatsApp/
    Google are all just columns on the same `users` row) — a real, explicit request (2026-09-04),
    not something Google/Telegram/WhatsApp each need their own separate tool for."""
    with get_session() as session:
        if _require_owner(request, session) is None:
            return _render(request, "404.html", {}, status_code=404)

        users = session.scalars(select(User).order_by(User.created_at.desc()).limit(500)).all()
        now = dt.datetime.now(dt.timezone.utc)
        rows = [
            {
                "id": u.id,
                "label": u.first_name
                or u.telegram_username
                or u.whatsapp_phone_number
                or f"#{u.id}",
                "channel": "טלגרם" if u.telegram_user_id else ("ווצאפ" if u.whatsapp_phone_number else "—"),
                "has_google": u.google_sub is not None,
                "free_access_granted": u.free_access_granted,
                "has_access": has_full_access(u, is_owner=_is_owner_id(u.telegram_user_id)),
                "trial_ends_at": u.trial_ends_at,
                "paid_until": u.paid_until,
                "in_trial": u.trial_ends_at is not None and now < u.trial_ends_at,
            }
            for u in users
        ]

    return _render(request, "admin_users.html", {"rows": rows})


@app.post("/admin/users/{user_id}/toggle-free-access")
def admin_toggle_free_access(request: Request, user_id: int):
    with get_session() as session:
        if _require_owner(request, session) is None:
            return _render(request, "404.html", {}, status_code=404)

        target = session.get(User, user_id)
        if target is not None:
            target.free_access_granted = not target.free_access_granted
            session.commit()

    return RedirectResponse("/admin/users", status_code=303)


PLAN_LABELS_HE = {
    "weekly": "שבועי — ₪15",
    "biweekly": "שבועיים — ₪25",
    "monthly": "חודשי — ₪40",
}


@app.get("/upgrade")
def upgrade(request: Request, uid: int | None = None):
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "upgrade"})
        is_owner = _is_owner_id(user.telegram_user_id)
        access = has_full_access(user, is_owner=is_owner)

    return _render(
        request,
        "upgrade.html",
        {
            "uid": user.telegram_user_id,
            "has_access": access,
            "is_owner": is_owner,
            "trial_ends_at": user.trial_ends_at,
            "paid_until": user.paid_until,
            "plan_prices": PLAN_PRICES_ILS,
            "plan_labels": PLAN_LABELS_HE,
            "grow_configured": grow_client.is_configured(),
        },
    )


@app.post("/upgrade")
def upgrade_submit(request: Request, plan: str = Form(...), uid: int | None = Form(None)):
    """Plan selection. Real gateway (Grow/Meshulam, 2026-09-05) once GROW_PAGE_CODE/GROW_USER_ID/
    GROW_API_KEY are all configured — creates a pending Payment row and redirects to Grow's hosted
    checkout; access is granted only once /webhooks/grow below confirms a real charge (see
    grow_client.py's own comment on why that confirmation logic is still provisional). Falls back
    to the earlier informal click-trust model (2026-09-04 decision: the click itself IS the
    payment signal, a Bit transfer happens outside this system) whenever Grow isn't configured
    yet, so the site keeps working exactly as before until the owner's Grow account is ready. The
    owner's /admin/users free-access toggle remains the remedy for a click/payment that turns out
    not to have actually happened, under either model."""
    if plan not in PLAN_PRICES_ILS:
        return _render(request, "auth_error.html", {}, status_code=400)

    amount = PLAN_PRICES_ILS[plan]

    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "upgrade"})

        if not grow_client.is_configured():
            payment = Payment(
                user_id=user.id, plan=plan, amount_ils=amount, status="pending", gateway=None
            )
            session.add(payment)
            session.commit()
            payment_id = payment.id
            redirect_uid = user.telegram_user_id
            qs = f"?payment_id={payment_id}" + (f"&uid={redirect_uid}" if redirect_uid else "")
            return RedirectResponse(f"/upgrade/pay{qs}", status_code=303)

        webhook_token = secrets.token_urlsafe(24)
        payment = Payment(
            user_id=user.id,
            plan=plan,
            amount_ils=amount,
            status="pending",
            gateway="grow",
            webhook_token=webhook_token,
        )
        session.add(payment)
        session.commit()
        payment_id = payment.id
        redirect_uid = user.telegram_user_id

    uid_qs = f"&uid={redirect_uid}" if redirect_uid else ""
    checkout_url = grow_client.create_checkout_url(
        payment_id=payment_id,
        amount_ils=amount,
        description=f"טודירה — מנוי {PLAN_LABELS_HE.get(plan, plan)}",
        success_url=f"{WEBSITE_URL}/upgrade/success?payment_id={payment_id}{uid_qs}",
        cancel_url=f"{WEBSITE_URL}/upgrade?{uid_qs.lstrip('&')}" if redirect_uid else f"{WEBSITE_URL}/upgrade",
        notify_url=f"{WEBSITE_URL}/webhooks/grow?token={webhook_token}",
    )
    if checkout_url is None:
        with get_session() as session:
            failed = session.get(Payment, payment_id)
            if failed is not None:
                failed.status = "failed"
                session.commit()
        return _render(request, "auth_error.html", {}, status_code=502)

    return RedirectResponse(checkout_url, status_code=303)


@app.get("/upgrade/success")
def upgrade_success(request: Request, payment_id: int, uid: int | None = None):
    """Landing page for BOTH payment paths: where Grow redirects the browser after checkout
    (access is granted server-to-server by /webhooks/grow below, which may land slightly before or
    after this redirect — this just reports the payment's CURRENT status, never grants anything
    itself), and where /upgrade/pay/confirm below sends the browser after the informal Bit/PayBox
    flow (there access WAS already granted by that POST, so this always shows "paid" immediately)."""
    with get_session() as session:
        payment = session.get(Payment, payment_id)
    paid = payment is not None and payment.status == "paid"
    return _render(request, "upgrade_success.html", {"uid": uid, "paid": paid})


@app.get("/upgrade/pay")
def upgrade_pay(request: Request, payment_id: int, uid: int | None = None):
    """Informal Bit/PayBox payment instructions (2026-09-05) — no verified "open the app
    pre-filled" deep link exists for either (see OWNER_BIT_PHONE's own comment), so this just
    shows the exact amount + the owner's Bit phone / PayBox link plainly, with a self-service
    "I paid" confirmation below. Same honesty tradeoff as the old instant-grant-on-click flow —
    still trusted, not verified — just made into an explicit, visible step instead of an invisible
    side effect of clicking a plan button."""
    with get_session() as session:
        payment = session.get(Payment, payment_id)
        user = _resolve_user(request, session, uid)
        if user is None or payment is None or payment.user_id != user.id:
            return _render(request, "404.html", {}, status_code=404)
        redirect_uid = user.telegram_user_id

    return _render(
        request,
        "upgrade_pay.html",
        {
            "uid": redirect_uid,
            "payment_id": payment.id,
            "amount": payment.amount_ils,
            "plan_label": PLAN_LABELS_HE.get(payment.plan, payment.plan),
            "already_paid": payment.status == "paid",
            "bit_phone": OWNER_BIT_PHONE,
            "paybox_url": OWNER_PAYBOX_URL,
        },
    )


@app.post("/upgrade/pay/confirm")
def upgrade_pay_confirm(request: Request, payment_id: int = Form(...), uid: int | None = Form(None)):
    with get_session() as session:
        payment = session.get(Payment, payment_id)
        user = _resolve_user(request, session, uid)
        if user is None or payment is None or payment.user_id != user.id:
            return _render(request, "404.html", {}, status_code=404)

        if payment.status == "pending":
            extend_paid_until(user, payment.plan)
            payment.status = "paid"
            payment.paid_at = dt.datetime.now(dt.timezone.utc)
            session.commit()
        redirect_uid = user.telegram_user_id

    uid_qs = f"&uid={redirect_uid}" if redirect_uid else ""
    return RedirectResponse(f"/upgrade/success?payment_id={payment_id}{uid_qs}", status_code=303)


def _looks_like_a_successful_grow_payload(body: dict) -> bool:
    """UNVERIFIED — see webhooks_grow's own comment below and grow_client.py's module docstring.
    Accepts any of a few plausible "it worked" shapes rather than betting everything on one
    guessed key name. Update this once a real sandbox transaction shows the actual payload."""
    status = str(body.get("status", body.get("statusCode", ""))).strip().lower()
    if status in {"1", "true", "success", "ok", "approved"}:
        return True
    return bool(body.get("transactionId") or body.get("asmachta"))


@app.post("/webhooks/grow")
async def webhooks_grow(request: Request, token: str | None = None):
    """Grow's server-to-server payment confirmation. The exact payload shape Grow sends here is
    UNVERIFIED (see grow_client.py's module docstring — this sandbox's network egress blocks every
    Grow/Meshulam docs domain), so this logs the full raw body unconditionally and only ever marks
    a payment paid when it can positively identify BOTH a pending payment matching `token` (the
    per-payment secret WE generated and embedded in the notifyUrl handed to Grow at checkout time
    — see /upgrade above; this stands in for Grow's own webhook authentication, which is equally
    unverified) AND a plausible success signal in the body. Anything less confident is left
    pending rather than guessed at — a real customer payment can always still be reconciled by
    hand via /admin/users' free-access toggle. Always returns 200 so Grow doesn't retry-storm this
    endpoint even when the payload can't be made sense of yet (matches whatsapp_webhook.py's own
    documented always-200 contract)."""
    try:
        body = dict(await request.json())
    except Exception:
        body = dict(await request.form())
    logger.info("Grow webhook raw payload (token=%s): %r", token, body)

    if not token:
        logger.warning("Grow webhook received with no token — ignoring")
        return Response(status_code=200)

    with get_session() as session:
        payment = session.scalar(
            select(Payment).where(Payment.webhook_token == token, Payment.status == "pending")
        )
        if payment is None:
            logger.warning("Grow webhook token did not match any pending payment — ignoring")
            return Response(status_code=200)

        if not _looks_like_a_successful_grow_payload(body):
            logger.warning(
                "Grow webhook for payment_id=%s had no recognizable success signal — left "
                "pending, see the raw payload logged above",
                payment.id,
            )
            return Response(status_code=200)

        user = session.get(User, payment.user_id)
        if user is None:
            logger.error("Grow webhook for payment_id=%s references a deleted user", payment.id)
            return Response(status_code=200)

        payment.status = "paid"
        payment.paid_at = dt.datetime.now(dt.timezone.utc)
        payment.gateway_transaction_id = str(
            body.get("transactionId") or body.get("asmachta") or body.get("processId") or payment.id
        )
        extend_paid_until(user, payment.plan)
        session.commit()

    return Response(status_code=200)


@app.get("/account")
def account(request: Request, uid: int | None = None):
    """Cross-channel linking (dorin_common/channel_link.py) — same uid/session resolution as
    /apartments, /liked, /upgrade. Shows which channels are already linked to this user, and —
    for whichever aren't — a fresh 15-minute link code plus ready-to-use WhatsApp/Telegram deep
    links to send it from that channel, matching the reference product's own confirmed UX."""
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "account"})

        has_telegram = user.telegram_user_id is not None
        has_whatsapp = user.whatsapp_phone_number is not None
        has_google = user.google_sub is not None

        code = None
        if not has_telegram or not has_whatsapp:
            code = generate_link_code(session, user)
        redirect_uid = user.telegram_user_id

    return _render(
        request,
        "account.html",
        {
            "uid": redirect_uid,
            "has_telegram": has_telegram,
            "has_whatsapp": has_whatsapp,
            "has_google": has_google,
            "code": code,
            "telegram_link": f"https://t.me/AmirDirotBot?start={code}" if code else None,
            "whatsapp_link": (
                f"https://wa.me/{WHATSAPP_PUBLIC_NUMBER}?text={code}"
                if code and WHATSAPP_PUBLIC_NUMBER
                else None
            ),
        },
    )


@app.get("/filter")
def filter_view(request: Request, uid: int | None = None):
    lang = get_lang(request)
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "filter"})
        if user.filter is None:
            return _render(request, "no_filter.html", {"uid": user.telegram_user_id})
        filter_row = user.filter
        return _render(
            request,
            "filter.html",
            {
                "f": filter_row,
                "uid": user.telegram_user_id,
                "user": user,
                # sorted for display only — CITIES itself stays in its original order since other
                # code (matching, the bot's own city picker) reads it as-is.
                "cities_list": sorted(CITIES),
                "property_type_labels": PROPERTY_TYPE_LABELS.get(lang, PROPERTY_TYPE_LABELS[DEFAULT_LANG]),
                "safe_room_labels": SAFE_ROOM_LABELS.get(lang, SAFE_ROOM_LABELS[DEFAULT_LANG]),
                "furniture_labels": FURNITURE_LABELS.get(lang, FURNITURE_LABELS[DEFAULT_LANG]),
            },
        )


@app.post("/filter")
def filter_update(
    uid: int = Form(...),
    cities: list[str] = Form([]),
    price_min: str = Form(""),
    price_max: str = Form(""),
    rooms_min: str = Form(""),
    rooms_max: str = Form(""),
    property_types: list[str] = Form([]),
    floor_min: str = Form(""),
    floor_max: str = Form(""),
    ground_floor_only: str | None = Form(None),
    require_parking: str | None = Form(None),
    require_elevator: str | None = Form(None),
    require_balcony: str | None = Form(None),
    require_pets_allowed: str | None = Form(None),
    require_renovated: str | None = Form(None),
    require_roommate_friendly: str | None = Form(None),
    require_has_photos: str | None = Form(None),
    no_brokers: str | None = Form(None),
    safe_room_pref: str = Form("any"),
    furniture_pref: str = Form("any"),
    min_area_sqm: str = Form(""),
    keywords: str = Form(""),
    flexible_match: str | None = Form(None),
):
    with get_session() as session:
        user = _get_user_by_uid(session, uid)
        if user is None or user.filter is None:
            return RedirectResponse(f"/filter?uid={uid}", status_code=303)

        f: Filter = user.filter
        f.cities = [c for c in cities if c in CITIES]
        f.price_min = int(price_min) if price_min.strip() else None
        f.price_max = int(price_max) if price_max.strip() else None
        f.rooms_min = float(rooms_min) if rooms_min.strip() else None
        f.rooms_max = float(rooms_max) if rooms_max.strip() else None
        f.property_types = [p for p in property_types if p in PROPERTY_TYPE_LABELS[DEFAULT_LANG]]
        f.floor_min = int(floor_min) if floor_min.strip() else None
        f.floor_max = int(floor_max) if floor_max.strip() else None
        f.ground_floor_only = ground_floor_only is not None
        f.require_parking = require_parking is not None
        f.require_elevator = require_elevator is not None
        f.require_balcony = require_balcony is not None
        f.require_pets_allowed = require_pets_allowed is not None
        f.require_renovated = require_renovated is not None
        f.require_roommate_friendly = require_roommate_friendly is not None
        f.require_has_photos = require_has_photos is not None
        f.no_brokers = no_brokers is not None
        f.safe_room_pref = safe_room_pref if safe_room_pref in SAFE_ROOM_LABELS[DEFAULT_LANG] else "any"
        f.furniture_pref = furniture_pref if furniture_pref in FURNITURE_LABELS[DEFAULT_LANG] else "any"
        f.min_area_sqm = int(min_area_sqm) if min_area_sqm.strip() else None
        f.keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        f.flexible_match = flexible_match is not None
        session.commit()

    return RedirectResponse(f"/filter?uid={uid}", status_code=303)
