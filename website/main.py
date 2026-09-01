"""ToDira public website (Phase 2) — FastAPI, server-rendered Jinja2 templates, reuses
common/dorin_common (same models/matching/db as the bot and scraper).

AUTH: two ways in, and both resolve to the same signed session cookie in the end.
  1. Real login — the Telegram Login Widget (see /auth/telegram/callback below). The session
     cookie stores only the internal `users.id` PK, deliberately NOT "telegram_user_id" or
     anything Telegram-specific — a future WhatsApp bot's own login route just needs to resolve
     its own user identity to the same `users.id` and populate the same session key
     (`request.session["user_id"]`), no changes needed here. This is the important bit: the
     product plan includes a WhatsApp bot later, and everything is meant to sit on/talk to this
     one website, so the session layer can't be hard-wired to "Telegram is the only login".
  2. Legacy `?uid=` query param (the bot's deep links, e.g. from a "check your matches" message) —
     kept working unchanged so existing links never break. Not secure on its own (anyone who
     knows/guesses a uid can view that user's filter/liked listings via a raw link), but the real
     session cookie above is what protects a page once you've actually logged in.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import time
from pathlib import Path

import httpx
from dorin_common.cities import CITIES
from dorin_common.db import get_session
from dorin_common.matching import evaluate
from dorin_common.models import ContactMessage, Filter, Listing, User, UserListingAction
from fastapi import FastAPI, Form, Request
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
)
from whatsapp_webhook import router as whatsapp_router

# Matches bot/main.py's own logging.basicConfig — without this, INFO-level messages (including
# httpx's own automatic request logging) are invisible in pod logs by default (root logger stays
# at WARNING), which made a real bug (a Telegram push silently not firing) much harder to diagnose
# than it needed to be. Found and fixed 2026-09-01 alongside the OWNER_TELEGRAM_USER_ID bug below.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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
    query param stays supported unchanged so existing bot deep links keep working."""
    session_user_id = request.session.get("user_id")
    if session_user_id is not None:
        user = session.get(User, session_user_id)
        if user is not None:
            return user
    if uid is not None:
        return _get_user_by_uid(session, uid)
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


@app.get("/terms")
def terms(request: Request):
    return _render(request, "terms.html", {})


@app.get("/privacy")
def privacy(request: Request):
    return _render(request, "privacy.html", {})


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

    return _render(
        request,
        "apartments.html",
        {"listings": matches, "uid": user.telegram_user_id, "user": user, "via_session": via_session},
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

    return _render(
        request, "liked.html", {"listings": listings, "uid": user.telegram_user_id, "user": user}
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
                "cities_list": CITIES,
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
