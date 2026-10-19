"""ToDira public website (Phase 2) — FastAPI, server-rendered Jinja2 templates, reuses
common/todira_common (same models/matching/db as the bot and scraper).

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
     product (the reference bot) treats "Continue with Telegram": open the bot directly, no OAuth handshake
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
import html
import json
import logging
import math
import mimetypes
import os
import secrets
import threading
import time
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote as url_quote, urlencode
from zoneinfo import ZoneInfo

import httpx
from todira_common import listing_enrichment
from todira_common.access import (
    CANCELLATION_WINDOW,
    SUBSCRIPTION_PLAN,
    PASS_PLANS,
    TEST_PASS_PLAN,
    cancellation_quote,
    PLAN_DURATIONS,
    PLAN_PRICES_ILS,
    plan_for_amount,
    test_amount_from_env,
    extend_paid_until,
    ACCESS_TRIAL_ENDED,
    access_state,
    has_full_access,
    has_paid_access,
)
from todira_common.channel_link import generate_link_code
from todira_common.public_text import is_room_in_shared_flat, public_description
from todira_common.cities import CITIES, LOCALITIES, LOCALITY_SET, REGIONS, SECOND_NAMES
from todira_common.db import get_session
from todira_common.google_link import generate_google_link_token
from todira_common.listing_matches import load_listings, mark_recent_matches_seen, matching_listing_rows, shown_listing_id
from todira_common.models import ContactMessage, Filter, Listing, Payment, User, UserListingAction
from todira_common.uid_token import generate_handoff_token, verify_handoff_token, verify_uid_token
from fastapi import FastAPI, Form, Request

import takbull_client
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import Float, case, cast, delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer
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

# 2026-09-24 real bug found live: /static/style.css (linked with no cache-busting query string at
# all, unlike todira-brand.webp's own ?v=4) got rewritten heavily across several deploys in one
# night — the owner's own real mobile browser kept showing stale/broken layouts a fresh Playwright
# browser (no prior cache) never reproduced. GIT_SHA is set to the same git commit SHA already
# used as this deploy's own image tag (charts/todira/templates/website-deployment.yaml) — already
# unique per deploy, so appending it as ?v=<sha> to style.css (see base.html) forces every browser
# to fetch the new file instead of serving a stale cached one after a deploy. "dev" outside a real
# deploy (local run, tests) is harmless — it's just a stable cache key, not a real version.
GIT_SHA = os.environ.get("GIT_SHA", "dev")

# 2026-09-25: the home page's marketing content (hero/features/FAQ/etc, NOT any other route —
# login, /apartments, payments, admin, webhooks are all untouched, still plain Jinja2/vanilla
# CSS+JS) is now a small isolated React+Framer Motion build (website/landing-react/), chosen
# deliberately as a scoped, low-risk way to try the framework rather than a full-site rewrite —
# see the owner conversation this came from. `npm run build` there emits hashed asset filenames
# into static/landing/ plus a Vite-generated manifest.json mapping the source entry to those
# hashed names (they change on every rebuild) — read once and cached here so home() never needs a
# disk read per request, and so nobody has to hand-edit a hashed filename after a future rebuild.
_LANDING_MANIFEST_PATH = BASE_DIR / "static" / "landing" / ".vite" / "manifest.json"
_landing_assets_cache: dict[str, dict[str, str]] | None = None


def _landing_react_assets(entry_name: str = "index.html") -> dict[str, object]:
    """Returns {"js": "/static/landing/...", "css": ["/static/landing/...", ...]} for the built
    landing-react bundle's given entry (Vite's manifest.json key, e.g. "index.html" for home,
    "about.html" for About — see landing-react/vite.config.js's multi-page rollupOptions.input),
    or {} if it hasn't been built (e.g. a fresh checkout before `npm run build` — callers fall
    back to rendering nothing in that slot rather than a broken tag).

    `css` is a LIST, not a single URL — real bug found live once a second entry existed: Vite's
    manifest only lists an entry's own DIRECTLY-imported CSS on the entry itself; CSS that reaches
    an entry via a shared chunk (Blob.jsx, imported by both index.html and about.html once About
    was added) is listed on that CHUNK's own manifest entry instead, not the entry's — confirmed by
    reading the real manifest.json after a real build, not assumed from Vite's docs. Walking each
    entry's own "imports" (recursively, in case a future shared chunk itself imports another) and
    collecting their css is what a real multi-entry Vite app actually requires.

    Cached per entry_name — real bug found in review, back when this only ever served one entry:
    caching {} on failure too meant starting uvicorn before running `npm run build` (exactly the
    scenario this function's own fallback anticipates) permanently wedged every request into the
    "not built yet" fallback, even after the build finished, until the process was restarted. A
    missing/broken manifest is cheap to keep retrying (these routes aren't hot), so only the
    success path is worth avoiding a repeat disk read for."""
    global _landing_assets_cache
    if _landing_assets_cache is None:
        _landing_assets_cache = {}
    if entry_name in _landing_assets_cache:
        return _landing_assets_cache[entry_name]
    try:
        manifest = json.loads(_LANDING_MANIFEST_PATH.read_text(encoding="utf-8"))
        entry = manifest[entry_name]
        css_files = list(entry.get("css") or [])
        seen_chunks: set[str] = set()

        def _collect_chunk_css(chunk_key: str) -> None:
            if chunk_key in seen_chunks:
                return
            seen_chunks.add(chunk_key)
            chunk = manifest.get(chunk_key)
            if not chunk:
                return
            css_files.extend(chunk.get("css") or [])
            for imported_key in chunk.get("imports") or []:
                _collect_chunk_css(imported_key)

        for imported_key in entry.get("imports") or []:
            _collect_chunk_css(imported_key)

        assets = {
            "js": f"/static/landing/{entry['file']}",
            "css": [f"/static/landing/{f}" for f in dict.fromkeys(css_files)],
        }
        _landing_assets_cache[entry_name] = assets
        return assets
    except (OSError, KeyError, json.JSONDecodeError):
        logger.warning("landing-react manifest not found/unreadable for %r at %s", entry_name, _LANDING_MANIFEST_PATH)
        return {}

# 2026-09-24 real production bug, confirmed live via a real headless-browser diagnostic against
# todira.app itself (not guessed): StaticFiles guesses each served file's Content-Type from
# Python's own mimetypes module, which reads its registry from the underlying OS's /etc/mime.types
# — and the production container's own copy doesn't know .webp at all, so every .webp under
# /static (the site's own brand/logo image included) was served as generic
# application/octet-stream instead of image/webp. A browser that can't recognize a response's
# content-type falls back to offering it as a raw file download rather than rendering it — which
# is the real, confirmed mechanism behind the owner's own screenshot of a phone Safari download
# prompt for a todira.app resource. Registering the type explicitly in code removes the dependency
# on whatever mimetypes database happens to ship in a given base image entirely, so it can't
# silently regress again on a future image/OS change. .webmanifest (base.html's own PWA manifest
# link) is the other modern/niche extension actually worth defending the same way — every other
# extension under /static (.css/.ico/.jpg/.png) is old enough to be universally present in any
# real mimetypes database, confirmed unaffected by this same production gap.
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("application/manifest+json", ".webmanifest")

app = FastAPI(title="טודירה")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY, same_site="lax")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
# 2026-10-17: listing cards printed "2.0 חדרים" (rooms is NUMERIC(3,1)) and "4900 ₪" with no thousands separator,
# while the bot's cards and the home page already say "2 חדרים" / "4,900 ₪".
templates.env.filters["rooms_label"] = lambda rooms: f"{float(rooms):g}" if rooms else "?"
# 2026-10-19 (owner): an ad's text never shows who posted it or how to reach them - see todira_common.public_text.
templates.env.filters["public_desc"] = public_description
templates.env.filters["shared_room"] = is_room_in_shared_flat
templates.env.filters["ils"] = lambda amount: f"{int(amount):,} ₪"


def _israel_date(value, fmt: str = "%d.%m.%Y") -> str:
    """2026-10-19 (bug sweep): dates were printed in UTC, so an end time after 21:00/22:00 UTC showed the PREVIOUS day on
    /account and /upgrade while the bot and the notice showed the right one (one page said 03.11, another 04.11). Every
    shown date goes through here: Israel time, one format."""
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        value = value.astimezone(ZoneInfo("Asia/Jerusalem"))
    return value.strftime(fmt)


templates.env.filters["il_date"] = _israel_date
templates.env.filters["il_datetime"] = lambda value: _israel_date(value, "%d.%m.%Y %H:%M")

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
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://todira.app")

# Informal Bit/PayBox payment (2026-09-05 — the owner's click-trust fallback while no real gateway is configured, see
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
    # name/email/message are all attacker-controlled (anyone can submit the /contact form) —
    # escaped before going into an HTML-parsed Telegram message so they can't break the owner
    # notification's formatting or inject a fake link/tag into what the owner reads as trusted
    # app text. Found live 2026-09-07, same bug class fixed in support.py.
    lines = ["📬 <b>הודעה חדשה מהאתר (טודירה)</b>"]
    if name:
        lines.append(f"שם: {html.escape(name)}")
    if email:
        lines.append(f"אימייל: {html.escape(email)}")
    if telegram_user_id:
        lines.append(f"Telegram user ID: {telegram_user_id}")
    lines.append("")
    lines.append(html.escape(message))
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
            select(
                User.telegram_user_id, User.first_name, User.telegram_username, User.created_at,
                User.trial_ends_at, User.paid_until, User.free_access_granted,
            ).where(User.id == user_id)
        ).first()
    if row is None:
        return None
    return {
        "telegram_user_id": row.telegram_user_id,
        "first_name": row.first_name,
        "telegram_username": row.telegram_username,
        "trial_gift_until": _trial_gift_until(row),
    }


# 2026-10-18 (owner): the free trial went from 3 to 10 days, and everyone already registered got 7 more days
# (migration 0030). Telegram users hear it from the bot (bot/announce_trial_extension.py); signed-in visitors of the
# site - including Google-only accounts the bot can't reach - see a notice with their new end date until this date.
TRIAL_GIFT_CUTOFF = dt.datetime(2026, 10, 19, 0, 0, tzinfo=dt.timezone.utc)  # accounts created before the change
TRIAL_GIFT_NOTICE_UNTIL = dt.datetime(2026, 10, 29, tzinfo=dt.timezone.utc)


def _trial_gift_until(row) -> str | None:
    """The new trial end date (dd.mm.yyyy, Israel time) to show in the notice, or None: only for an account created
    before the change, still in its trial, without a paid pass or free access, and only until the notice period ends."""
    now = dt.datetime.now(dt.timezone.utc)
    created_at = getattr(row, "created_at", None)
    trial_ends_at = getattr(row, "trial_ends_at", None)
    paid_until = getattr(row, "paid_until", None)
    if (
        now >= TRIAL_GIFT_NOTICE_UNTIL
        or not isinstance(created_at, dt.datetime) or created_at >= TRIAL_GIFT_CUTOFF
        or not isinstance(trial_ends_at, dt.datetime) or trial_ends_at <= now
        or (isinstance(paid_until, dt.datetime) and paid_until > now)
        or getattr(row, "free_access_granted", False) is True
    ):
        return None
    return trial_ends_at.astimezone(ZoneInfo("Asia/Jerusalem")).strftime("%d.%m.%Y")


# 2026-10-17 (owner, launch day: the site is linked from his Instagram bio). Apps that open links in their own
# built-in browser keep their own cookies, apart from Safari/Chrome; Google also refuses its sign-in inside them.
# Visitors in one get a banner with a button that opens the same page in their real browser - still signed in,
# through a short-lived one-time handoff link (/auth/handoff).
_IN_APP_BROWSER_MARKERS = (
    ("Instagram", "Instagram"),
    ("FBAN", "Facebook"),
    ("FBAV", "Facebook"),
    ("FB_IAB", "Facebook"),
    ("BytedanceWebview", "TikTok"),
    ("musical_ly", "TikTok"),
    ("TikTok", "TikTok"),
    ("Snapchat", "Snapchat"),
    ("LinkedInApp", "LinkedIn"),
    (" Line/", "LINE"),
)


def _in_app_browser(request: Request) -> dict | None:
    """{"app", "open_url", "copy_url", "platform"} when the page is open inside a social app's built-in browser, else
    None. open_url opens this page in the real browser: Chrome through an Android intent, Safari through iOS's x-safari-
    scheme. A signed-in visitor's link goes through /auth/handoff so the new browser is signed in too.

    2026-10-18 (owner: "the open in browser button doesn't work"): Instagram's and Facebook's iOS browser ignore the
    x-safari- scheme since 2025, and iOS has no supported way for a web page to leave an app's browser. So the button
    also copies copy_url (the plain https link), and when the page is still showing a moment later the banner shows the
    steps that always work: the app's own menu, or pasting the copied link into the browser."""
    user_agent = request.headers.get("user-agent", "")
    app_name = next((name for marker, name in _IN_APP_BROWSER_MARKERS if marker in user_agent), None)
    if app_name is None:
        return None
    path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    user_id = request.session.get("user_id")
    if user_id is not None and _current_user_summary(request) is not None:
        path = f"/auth/handoff?h={generate_handoff_token(user_id)}&next={url_quote(path, safe='/')}"
    target = f"https://{request.url.netloc}{path}"
    if "Android" in user_agent:
        platform = "android"
        open_url = (
            f"intent://{request.url.netloc}{path}#Intent;scheme=https;package=com.android.chrome;"
            f"S.browser_fallback_url={url_quote(target, safe='')};end"
        )
    elif any(device in user_agent for device in ("iPhone", "iPad", "iPod")):
        platform = "ios"
        open_url = f"x-safari-{target}"
    else:
        platform = "other"
        open_url = target
    return {"app": app_name, "open_url": open_url, "copy_url": target, "platform": platform}


def _render(
    request: Request,
    template_name: str,
    context: dict,
    status_code: int = 200,
    known_lang: str | None = None,
) -> Response:
    """Every page goes through this: resolves the viewer's language (?lang= > cookie > known_lang
    > Accept-Language > Hebrew — see i18n.get_lang's own docstring for why known_lang exists),
    injects lang/dir/t/lang switcher data into the template context, and — only when the request
    explicitly asked for a language via ?lang= — persists it to a cookie so it survives to the
    next page without every internal link needing to carry ?lang= itself (uid already has to be
    threaded through links for auth, but lang is a site-wide preference, a cookie fits better).
    Also injects `current_user` (or None) so the header's login/logout UI is correct on every page,
    not just the ones that already resolve a full user for their own content.

    known_lang: pass `user.language` here whenever the caller already resolved a real user (via
    uid) before calling this — lets an identified visitor's own on-file language preference
    win over a guess from their browser's Accept-Language header, which is often wrong for that
    specific case (e.g. Telegram's in-app browser sends the phone's system language, not the
    language the person actually chose for the bot). Omit it for routes with no resolved user.
    """
    lang = get_lang(request, known_lang)
    current_user = _current_user_summary(request)
    is_real_owner = current_user is not None and _is_owner_id(current_user["telegram_user_id"])
    response = templates.TemplateResponse(
        request,
        template_name,
        {
            **context,
            "lang": lang,
            "dir": "rtl" if lang in RTL_LANGS else "ltr",
            "t": make_translator(lang),
            # 2026-09-27 real owner request: base.html's og:title/og:description (and their
            # twitter: mirrors) used to follow `t` — i.e. whatever language THIS request's own
            # Accept-Language resolved to. That's meaningless for a link-preview card specifically:
            # Telegram/Facebook fetch the page ONCE with their own crawler's Accept-
            # Language (confirmed live — resolves to English), cache that single result, and show
            # the SAME cached card to every recipient regardless of the sharer's or viewer's own
            # phone language. So `t` was never actually personalizing the preview per-viewer; it
            # was just picking whatever language the crawler happened to send. Fixed to Hebrew
            # (this product's primary audience) instead — the ACTUAL page content a visitor lands
            # on after tapping the link is completely unaffected, still resolved via `t`/`lang`
            # above from THEIR OWN real request the normal way.
            "og_t": make_translator(DEFAULT_LANG),
            "posted_ago": lambda posted_at: relative_time_label(posted_at, lang),
            "supported_langs": SUPPORTED_LANGS,
            "lang_labels": LANG_LABELS,
            "current_user": current_user,
            "in_app_browser": _in_app_browser(request),
            "static_version": GIT_SHA,
            "is_owner": is_real_owner and not _preview_as_free(request),
            "is_real_owner": is_real_owner,
            "preview_as_free": _preview_as_free(request),
            # footer.copyright's own {year} placeholder (base.html) — was a hardcoded "© 2026"
            # that would've silently gone stale every January 1st; now resolved fresh on every
            # request instead of needing a manual edit once a year.
            "current_year": dt.datetime.now(dt.timezone.utc).year,
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
    # 2026-10-02 SECURITY: a bare ?uid=<telegram id> is NO LONGER trusted (a Telegram id is public
    # knowledge and the repo is public: anyone could open another user's pages, edit their filter, and
    # take the account over via /auth/google/start?uid=). The bot/notifier now link with ?t=<signed
    # token> (todira_common/uid_token.py); a valid token proves the visitor was sent this link, and
    # establishes the normal signed session cookie. It takes priority over an existing session, so
    # tapping a bot link always lands on the account that link belongs to. The `uid` argument stays
    # in the signature only because every route and template still passes it along; it is ignored.
    signed_token = request.query_params.get("t")
    if signed_token:
        telegram_user_id = verify_uid_token(signed_token)
        if telegram_user_id is not None:
            user = _get_user_by_uid(session, telegram_user_id)
            if user is not None:
                pending_google_sub = request.session.get("pending_google_sub")
                if pending_google_sub and user.google_sub is None:
                    user.google_sub = pending_google_sub
                    session.commit()
                    request.session.pop("pending_google_sub", None)
                request.session["user_id"] = user.id
                return user
    session_user_id = request.session.get("user_id")
    if session_user_id is not None:
        user = session.get(User, session_user_id)
        if user is not None:
            return user
    return None


def _trusted_link_uid(request: Request, uid: int | None) -> int | None:
    """The Telegram id a page may use to LINK a Google account to an existing account (the Google
    sign-in's `?uid=`), or None. Trusted only when it is proven: a valid signed ?t= token on this
    request, or a uid that matches the account the visitor is already signed in as. A bare number
    from the query string is never enough — it would let anyone link their own Google account to a
    victim's account (the takeover this whole change closes)."""
    signed_token = request.query_params.get("t")
    if signed_token:
        verified = verify_uid_token(signed_token)
        if verified is not None:
            return verified
    session_user_id = request.session.get("user_id")
    if uid is None or session_user_id is None:
        return None
    with get_session() as session:
        user = session.get(User, session_user_id)
        return uid if user is not None and user.telegram_user_id == uid else None


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


@app.get("/healthz")
def healthz() -> Response:
    """Kubernetes liveness/readiness probe target (see website-deployment.yaml) — added 2026-09-08
    as part of a pre-launch reliability pass. Before this, NO Deployment in this chart had any
    probe at all, meaning a hung-but-still-running process (an event loop deadlock, a lost DB
    connection that never recovers) would sit "Running" forever with zero automatic recovery, and
    a still-starting pod could receive traffic before it was actually ready. Checks a real DB
    round-trip, not just "the process is up" — a website that's running but can't reach Postgres
    is not actually healthy, and this is exactly the kind of failure a liveness probe exists to
    catch and restart out of."""
    try:
        with get_session() as session:
            session.execute(select(1))
    except Exception:
        logger.exception("Healthcheck failed: could not query the database")
        return Response(status_code=503, content="db unreachable")
    return Response(status_code=200, content="ok")


# 2026-10-15 (owner): real numbers on the home page, always current, instead of fixed claims (one of which, "scans every two
# hours", had gone stale - it scans every hour). Counted from the listings table: new listings in the last 24 hours, live
# listings now, cities with a live listing, and minutes since a scrape last confirmed a listing. Cross-site duplicates of one
# flat count once. Cached briefly: every visitor shares one query every two minutes. None when the database can't answer,
# so the page falls back to its fixed stats instead of failing.
_HOME_STATS_TTL_SECONDS = 120
_home_stats_cache: dict = {"at": 0.0, "value": None}
_home_stats_lock = threading.Lock()


def _home_live_stats() -> dict | None:
    with _home_stats_lock:
        if _home_stats_cache["value"] is not None and time.monotonic() - _home_stats_cache["at"] < _HOME_STATS_TTL_SECONDS:
            return _home_stats_cache["value"]
    try:
        with get_session() as session:
            canonical = Listing.duplicate_of_id.is_(None)
            live = [canonical, Listing.is_delisted.is_(False)]
            new_24h = session.scalar(
                select(func.count()).select_from(Listing).where(
                    canonical, Listing.first_seen_at >= func.now() - dt.timedelta(hours=24)
                )
            )
            active, cities = session.execute(
                select(func.count(), func.count(func.distinct(Listing.city))).select_from(Listing).where(*live)
            ).one()
            last_scan = session.scalar(select(func.max(Listing.scraped_at)))
    except Exception:
        logger.warning("could not count the home page's live stats", exc_info=True)
        return None
    minutes = None
    if last_scan is not None:
        if last_scan.tzinfo is None:
            last_scan = last_scan.replace(tzinfo=dt.timezone.utc)
        minutes = max(0, int((dt.datetime.now(dt.timezone.utc) - last_scan).total_seconds() // 60))
    value = {"new_24h": int(new_24h or 0), "active": int(active or 0), "cities": int(cities or 0), "last_scan_minutes": minutes}
    with _home_stats_lock:
        _home_stats_cache.update(at=time.monotonic(), value=value)
    return value


@app.get("/api/home-stats")
def home_stats():
    """The home page refreshes its live numbers from here every minute while it is open."""
    stats = _home_live_stats()
    if stats is None:
        return JSONResponse({"error": "unavailable"}, status_code=503, headers={"Cache-Control": "no-store"})
    return JSONResponse(stats, headers={"Cache-Control": "public, max-age=60"})


# 2026-10-19 (owner approved the redesign, and asked to keep the old home page ready to come back): the new page is
# templates/home.html; HOME_DESIGN=classic serves the previous React page (templates/home_classic.html) to everyone,
# and ?design=classic shows it to whoever opens that link.
_HOME_DESIGN_ENV_VAR = "HOME_DESIGN"
_HOME_MAP_TTL_SECONDS = 600
_home_map_cache: dict = {"at": 0.0, "value": None}
_home_map_lock = threading.Lock()
# Map labels for the five places the home page names; the dots themselves come from the listings.
_HOME_MAP_CITIES = (
    ("landing.city_haifa", 32.79, 34.99), ("landing.city_tel_aviv", 32.08, 34.78),
    ("landing.city_jerusalem", 31.77, 35.21), ("landing.city_beer_sheva", 31.25, 34.79),
    ("landing.city_eilat", 29.56, 34.95),
)
_LANDING_STRING_KEYS = ("notif_title", "notif_detail", "rooms_n", "rooms_1", "map_label")


def _home_map_data() -> dict | None:
    """What the home page's live map shows, counted from the listings and cached for ten minutes: how many live
    listings sit in each map square of about 2.5 km (and how many of those came in during the last 24 hours), the
    24-hour totals, and the newest rentals (city, rooms, price and a position rounded to about 1 km). Aggregates and
    listing basics only. None when the database can't be read."""
    with _home_map_lock:
        if _home_map_cache["value"] is not None and time.monotonic() - _home_map_cache["at"] < _HOME_MAP_TTL_SECONDS:
            return _home_map_cache["value"]
    try:
        with get_session() as session:
            live = (Listing.is_delisted.is_(False), Listing.duplicate_of_id.is_(None))
            fresh = Listing.first_seen_at >= func.now() - dt.timedelta(hours=24)
            lat_cell = func.round(Listing.latitude * 40) / 40
            lng_cell = func.round(Listing.longitude * 40) / 40
            grid = session.execute(
                select(lat_cell, lng_cell, func.count(), func.count().filter(fresh))
                .where(*live, Listing.latitude.between(29.4, 33.4), Listing.longitude.between(34.2, 35.9))
                .group_by(text("1"), text("2"))
            ).all()
            new_24h, cities_24h = session.execute(
                select(func.count(), func.count(func.distinct(Listing.city))).where(*live, fresh)
            ).one()
            recent = session.execute(
                select(Listing.city, Listing.rooms, Listing.price, Listing.latitude, Listing.longitude)
                .where(
                    *live, Listing.deal_type == "rent", Listing.price >= 1000, Listing.rooms.is_not(None),
                    Listing.latitude.is_not(None), Listing.city.is_not(None),
                )
                .order_by(Listing.first_seen_at.desc())
                .limit(30)
            ).all()
    except Exception:
        logger.warning("could not read the home page's map data", exc_info=True)
        return None
    value = {
        "grid": [[round(float(a), 3), round(float(b), 3), int(c), int(d)] for a, b, c, d in grid if a is not None],
        "new_24h": int(new_24h or 0),
        "cities_24h": int(cities_24h or 0),
        "recent": [
            {"city": city, "rooms": float(rooms), "price": int(price),
             "lat": round(float(lat), 2), "lng": round(float(lng), 2)}
            for city, rooms, price, lat, lng in recent
        ],
    }
    with _home_map_lock:
        _home_map_cache.update(at=time.monotonic(), value=value)
    return value


@app.get("/api/home-map")
def home_map():
    data = _home_map_data()
    if data is None:
        return JSONResponse({"error": "unavailable"}, status_code=503, headers={"Cache-Control": "no-store"})
    return JSONResponse(data, headers={"Cache-Control": "public, max-age=300"})


def _landing_plans() -> list[dict]:
    plans = []
    for plan, days, name_key in (("pass_7", 7, "upgrade.pass_name_7"), ("pass_14", 14, "upgrade.pass_name_14"),
                                 ("pass_30", 30, "upgrade.pass_name_30")):
        price = PLAN_PRICES_ILS[plan]
        plans.append({"name_key": name_key, "price": f"{price:.2f}", "per_day": f"{price / days:.2f}"})
    return plans


def _landing_js(lang: str) -> dict:
    t = make_translator(lang)
    return {
        "lang": lang,
        "strings": {key: t(f"landing.{key}") for key in _LANDING_STRING_KEYS},
        "cities": [{"name": t(key), "lat": lat, "lng": lng} for key, lat, lng in _HOME_MAP_CITIES],
        "demos": [
            {
                "ask": t(f"landing.demo{n}_ask"), "chips": t(f"landing.demo{n}_chips").split("|"),
                "title": t(f"landing.demo{n}_title"), "price": t(f"landing.demo{n}_price"),
                "detail": t(f"landing.demo{n}_detail"), "street": t(f"landing.demo{n}_street"),
            }
            for n in range(1, 6)
        ],
    }


@app.get("/")
def home(request: Request):
    classic = (
        request.query_params.get("design") == "classic"
        or os.environ.get(_HOME_DESIGN_ENV_VAR, "").strip().lower() == "classic"
    )
    if classic:
        landing_assets = _landing_react_assets()
        return _render(
            request,
            "home_classic.html",
            {
                "landing_js_url": landing_assets.get("js", ""),
                "landing_css_urls": landing_assets.get("css", []),
                "live_stats": _home_live_stats(),
            },
        )
    lang = get_lang(request)
    return _render(request, "home.html", {"landing_plans": _landing_plans(), "landing_js": _landing_js(lang)})


@app.get("/robots.txt")
def robots_txt(request: Request) -> PlainTextResponse:
    """No robots.txt at all before this (2026-09-07 audit) meant crawlers had no signal to stay
    out of personalized/behind-auth pages (a search result linking straight into someone's own
    /apartments?uid=... would be both useless to searchers and a minor privacy smell) and no
    pointer to sitemap.xml for the pages that ARE worth indexing."""
    disallowed = (
        "/admin",
        "/account",
        "/apartments",
        "/liked",
        "/hidden",
        "/upgrade",
        "/filter",
        "/webhooks",
        "/auth",
        "/preview",
        "/react",
    )
    lines = ["User-agent: *"]
    lines += [f"Disallow: {path}" for path in disallowed]
    lines.append("")
    lines.append(f"Sitemap: {request.base_url}sitemap.xml")
    return PlainTextResponse("\n".join(lines))


# 2026-10-16 (owner wants Apple Pay): Takbull's provider settings ask to verify the site's domain before Apple Pay can
# be used. Apple fetches this exact file from this exact path over HTTPS; it is the file the owner downloaded from
# Takbull, served byte for byte. Public by design (anyone can fetch it from any Apple Pay merchant's domain).
_APPLE_PAY_DOMAIN_ASSOCIATION = BASE_DIR / "apple-pay" / "apple-developer-merchantid-domain-association"


@app.get("/.well-known/apple-developer-merchantid-domain-association")
def apple_pay_domain_association() -> Response:
    return Response(content=_APPLE_PAY_DOMAIN_ASSOCIATION.read_bytes(), media_type="text/plain")


# Public, unauthenticated, content pages worth a search engine indexing — kept in sync by hand
# since the set of genuinely public marketing/legal pages changes rarely; every one of these
# already renders in all 5 languages via base.html's own hreflang alternates (added alongside
# this), so the sitemap itself only needs to list each page once, not once per language.
_SITEMAP_PATHS = ("/", "/login", "/contact", "/about", "/terms", "/privacy", "/accessibility")


@app.get("/sitemap.xml")
def sitemap_xml(request: Request) -> Response:
    urls = "".join(
        f"<url><loc>{request.base_url}{path.lstrip('/')}</loc></url>" for path in _SITEMAP_PATHS
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + "</urlset>"
    )
    return Response(content=body, media_type="application/xml")


@app.get("/login")
def login(request: Request, next: str = "/apartments", uid: int | None = None):
    """A dedicated screen (2026-09-05 request) instead of the header's own small Google-only
    button — Google/Telegram shown as separate, equally prominent "continue with"
    options, matching the reference product's own login screen. Already-logged-in visitors skip
    straight past it. Telegram still just opens the bot directly (there's no
    "sign in with Telegram" that logs into THIS site without leaving it — Telegram's own
    Login Widget exists (see _verify_telegram_auth below) but was pulled from the UI after a real
    iOS Safari reliability complaint, see this file's module docstring); the payoff for choosing
    Google here shows up once you're actually signed in with it — see _resolve_user's own comment
    on why coming back from either of those two also finishes a pending Google link automatically.

    `uid` (2026-09-05 fix): forwarded into the Google button exactly like /account already does,
    so arriving here WITH a uid in flight (e.g. a bot deep link that happens to route through
    /login instead of straight to /account) still performs a real link on the first try, instead
    of silently falling back to the contextless "we don't recognize this Google account yet" path
    — found live: base.html's header only ever links to THIS route when it has no uid at all (see
    its own template), so a visitor with zero context (no uid, no session — the ordinary case for
    "hamburger menu → login") still can't be linked automatically; that part is inherent to how
    OAuth works, not a bug — Google alone can't tell us which existing Telegram account
    it belongs to. See google_pending.html for the recovery path in that case."""
    uid = _trusted_link_uid(request, uid)
    if request.query_params.get("t") and uid is not None:
        # A valid signed bot link: sign this browser in as that account (see _resolve_user).
        with get_session() as session:
            linked_user = _get_user_by_uid(session, uid)
            if linked_user is not None:
                request.session["user_id"] = linked_user.id
    if request.session.get("user_id") is not None:
        return RedirectResponse(_safe_next(next), status_code=303)
    # 2026-09-25: seventh page moved into a React island (website/landing-react/login.html), same
    # pattern as about()/accessibility()/privacy()/terms()/contact() above. `next` is still
    # resolved through _safe_next() here, server-side, before being injected into
    # window.__TODIRA_PAGE__ — Login.jsx builds the Google OAuth start link straight from that
    # already-sanitized value, never re-deriving or re-validating it client-side.
    login_assets = _landing_react_assets("login.html")
    return _render(
        request,
        "login.html",
        {
            "landing_js_url": login_assets.get("js", ""),
            "landing_css_urls": login_assets.get("css", []),
            "next": _safe_next(next),
            "uid": uid,
        },
    )


@app.get("/about")
def about(request: Request):
    """2026-09-25: second page moved into a React island (website/landing-react/about.html),
    same pattern as home() above — see landing-react/vite.config.js's own comment on the
    multi-page build this and home() now share."""
    about_assets = _landing_react_assets("about.html")
    return _render(
        request,
        "about.html",
        {
            "landing_js_url": about_assets.get("js", ""),
            "landing_css_urls": about_assets.get("css", []),
        },
    )


@app.get("/terms")
def terms(request: Request):
    """2026-09-25: fifth page moved into a React island (website/landing-react/terms.html),
    same pattern as about()/accessibility()/privacy() above."""
    terms_assets = _landing_react_assets("terms.html")
    return _render(
        request,
        "terms.html",
        {
            "landing_js_url": terms_assets.get("js", ""),
            "landing_css_urls": terms_assets.get("css", []),
        },
    )


@app.get("/privacy")
def privacy(request: Request):
    """2026-09-25: fourth page moved into a React island (website/landing-react/privacy.html),
    same pattern as about()/accessibility() above."""
    privacy_assets = _landing_react_assets("privacy.html")
    return _render(
        request,
        "privacy.html",
        {
            "landing_js_url": privacy_assets.get("js", ""),
            "landing_css_urls": privacy_assets.get("css", []),
        },
    )


@app.get("/accessibility")
def accessibility(request: Request):
    """2026-09-25: third page moved into a React island (website/landing-react/
    accessibility.html), same pattern as about() above."""
    a11y_assets = _landing_react_assets("accessibility.html")
    return _render(
        request,
        "accessibility.html",
        {
            "landing_js_url": a11y_assets.get("js", ""),
            "landing_css_urls": a11y_assets.get("css", []),
        },
    )


def _safe_next(next: str) -> str:
    # 2026-10-15 (security): "/\\evil.example" also passed the old check, and browsers treat a backslash like a slash -
    # "//evil.example" - so the redirect left the site. A backslash or any control character is never a page of ours.
    if not next.startswith("/") or next.startswith("//") or "\\" in next or any(ord(ch) < 32 for ch in next):
        return "/apartments"
    return next


# Handoff tokens already turned into a session (token -> when it was used); each one works once. In memory: one
# website replica, and a token lives only ten minutes anyway.
_USED_HANDOFF_TOKENS: dict[str, float] = {}


@app.get("/auth/handoff")
def auth_handoff(request: Request, h: str = "", next: str = "/"):
    """Signs this browser in as the user a fresh handoff token belongs to (see _in_app_browser), then goes on to
    `next`. A forged, expired or already used token just goes on, signed out."""
    now = time.time()
    for token, used_at in list(_USED_HANDOFF_TOKENS.items()):
        if now - used_at > 15 * 60:
            _USED_HANDOFF_TOKENS.pop(token, None)
    user_id = verify_handoff_token(h) if h else None
    if user_id is not None and h not in _USED_HANDOFF_TOKENS:
        _USED_HANDOFF_TOKENS[h] = now
        with get_session() as session:
            if session.get(User, user_id) is not None:
                request.session["user_id"] = user_id
    return RedirectResponse(_safe_next(next), status_code=303)


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

    uid = _trusted_link_uid(request, uid)
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
        userinfo = userinfo_resp.json()
        google_sub = userinfo["sub"]
        google_first_name = userinfo.get("given_name") or userinfo.get("name") or ""
        google_email = userinfo.get("email") or None
    except (httpx.HTTPError, KeyError):
        logger.exception("Failed to complete the Google OAuth token/userinfo exchange")
        return _render(request, "auth_error.html", {}, status_code=400)

    session_user_id = request.session.get("user_id")
    with get_session() as session:
        user = session.scalar(select(User).where(User.google_sub == google_sub))
        matched_via = "google_sub" if user is not None else None
        if user is not None and user.google_email != google_email:
            # Refreshed on every login, not just at link/creation time, so /account's own display
            # of "which Google account is this" stays correct if the person's email ever changes.
            user.google_email = google_email
            session.commit()
        if user is None and link_uid is not None:
            # First time this Google account signs in while viewing a page via the visitor's own
            # ?uid= deep link — link it to that SAME existing Telegram-created account so
            # every later "Sign in with Google" resolves straight back to it. Same
            # already-linked-to-someone-else guard as the session_user_id branch right below:
            # without it, anyone who knows/guesses a victim's uid could open this route, sign in
            # with their OWN Google account, and silently overwrite the victim's existing
            # google_sub — locking the victim out of their own Google login and letting the
            # attacker's Google account resolve straight to the victim's user row on every future
            # sign-in (real account takeover, found via a live code-review pass).
            candidate = _get_user_by_uid(session, link_uid)
            if candidate is not None and candidate.google_sub is None:
                candidate.google_sub = google_sub
                candidate.google_email = google_email
                session.commit()
                user = candidate
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
                    user.google_email = google_email
                    session.commit()
                    matched_via = "session_user_id"
                else:
                    # Already linked to a different Google account — don't silently overwrite it.
                    user = None
        user_pk = user.id if user is not None else None
        google_link_token = None if user_pk is not None else generate_google_link_token(session, google_sub)
        logger.info(
            "Google OAuth callback resolved: matched_via=%s link_uid=%s session_user_id=%s user_pk=%s",
            matched_via,
            link_uid,
            session_user_id,
            user_pk,
        )

    if user_pk is None:
        # A real Google account, but not yet linked to any Telegram-created user, and no
        # ?uid= was in flight right now to link it to. Two real possibilities from here, so
        # google_pending.html now offers both explicitly instead of assuming one:
        #  (a) this person already has a Telegram-created account, just not reachable
        #      from this browser/session right now — they should LINK, not duplicate. The
        #      google_link_token (todira_common/google_link.py) below completes that the instant
        #      they do /start in the bot, entirely server-side, regardless of which browser/app
        #      they're in when they get there (found live 2026-09-05: the session-cookie-only
        #      version alone never actually worked for this, since Telegram's own in-app browser
        #      is a separate cookie jar from whatever browser started the sign-in).
        #  (b) this is a genuinely first-time visitor with no bot account at all — 2026-09-05
        #      request: the website should be a first-class, standalone way in, not force a
        #      Telegram detour just to browse. /auth/google/create-account below creates a real
        #      standalone account (google_sub only, blank filter — matches everything until they
        #      narrow it on /filter) and logs them in on the SAME page load, same browser tab.
        # pending_google_sub/first_name/email are also stashed in the session for the lucky
        # same-browser case (_resolve_user above completes a pending link instantly if a real uid
        # shows up here later) and are what /auth/google/create-account reads to build the new
        # account.
        request.session["pending_google_sub"] = google_sub
        request.session["pending_google_first_name"] = google_first_name
        request.session["pending_google_email"] = google_email
        return _render(request, "google_pending.html", {"google_link_token": google_link_token})

    request.session["user_id"] = user_pk
    return RedirectResponse(_safe_next(next_url), status_code=303)


@app.post("/auth/google/create-account")
def auth_google_create_account(request: Request, next: str = "/apartments"):
    """The "this is a new account, start right here" half of google_pending.html (see
    auth_google_callback's own comment on why both options exist). Reads the pending_google_sub
    stashed by the callback — never trusts a client-supplied google_sub, since that would let
    anyone claim an arbitrary Google identity by just POSTing here directly. Creates a real
    standalone user (no telegram_user_id at all — it stays nullable, see
    User's own docstring) with a blank Filter (empty cities/no restrictions at all matches EVERY
    listing per matching.py's own `if filter_row.cities:` check). Telegram stays fully
    optional afterward, addable anytime via /account's existing channel-link-code flow for whoever
    wants push notifications there too.

    2026-09-06: a brand-new account is sent to /filter?welcome=1 instead of `next` — landing
    straight on /apartments showed every listing in the country unfiltered, which read as noise
    rather than value on a real user's first visit (see PROJECT_STATE.md). An *existing* account
    signing back in below still honors `next` as before; this only changes the true first-run."""
    pending_google_sub = request.session.pop("pending_google_sub", None)
    first_name = request.session.pop("pending_google_first_name", "")
    pending_google_email = request.session.pop("pending_google_email", None)
    if not pending_google_sub:
        return _render(request, "auth_error.html", {}, status_code=400)

    with get_session() as session:
        # Someone could double-submit this form (double click, back-button resubmit) — the
        # google_sub is already consumed from the session above (single use), but also guard the
        # DB's own unique constraint on google_sub so a genuine race doesn't 500.
        existing = session.scalar(select(User).where(User.google_sub == pending_google_sub))
        if existing is not None:
            request.session["user_id"] = existing.id
            return RedirectResponse(_safe_next(next), status_code=303)

        # 2026-09-24 real bug fix: the SELECT above only rules out the common case — two requests
        # racing this same double-click can BOTH pass it (neither sees the other's row yet), then
        # both try to INSERT the same google_sub and one hits the DB's unique constraint, which
        # used to bubble up as an unhandled 500 instead of the graceful "log them into the account
        # the other request just created" this whole function is otherwise built for. Catching it
        # here closes that actual race window, not just the comment above claiming to.
        user = User(
            google_sub=pending_google_sub, first_name=first_name or None,
            google_email=pending_google_email,
        )
        session.add(user)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(select(User).where(User.google_sub == pending_google_sub))
            if existing is None:
                raise  # some other integrity error — don't silently swallow it
            request.session["user_id"] = existing.id
            return RedirectResponse(_safe_next(next), status_code=303)
        session.add(Filter(user_id=user.id))
        session.commit()
        user_pk = user.id

    request.session["user_id"] = user_pk
    return RedirectResponse("/filter?welcome=1", status_code=303)


@app.get("/auth/logout")
def auth_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.get("/contact")
def contact(request: Request, uid: int | None = None):
    """2026-09-25: sixth page moved into a React island (website/landing-react/contact.html) —
    same pattern as about()/accessibility()/privacy()/terms() above, but unlike those (read-only
    legal/info content), this page has a real form that must reach the server. Unlike a native
    <form method=post>, which only makes sense targeting a server-rendered page, the React form
    below submits via fetch to POST /api/contact (JSON in/out — see that route's own docstring),
    so there's no server-rendered error/success/sent state to carry here across a page reload
    anymore, and the old form-encoded POST /contact endpoint was removed along with it. `uid` (the
    visitor's Telegram user id, when logged in via Telegram Login — see base.html's nav links
    building `/contact?uid=...`) is still accepted as a query param and forwarded into
    window.__TODIRA_PAGE__ so the React form can still send it along on submit, correlating the
    message with their account exactly as before."""
    contact_assets = _landing_react_assets("contact.html")
    return _render(
        request,
        "contact.html",
        {
            "landing_js_url": contact_assets.get("js", ""),
            "landing_css_urls": contact_assets.get("css", []),
            "uid": uid,
        },
    )


class ContactSubmission(BaseModel):
    name: str = ""
    email: str = ""
    message: str = ""
    uid: str = ""
    consent: bool = False


async def _process_contact_message(name: str, email: str, message: str, uid_raw: str, consent: bool) -> dict:
    """Validates, saves to ContactMessage, and best-effort notifies the owner via Telegram — the
    core of the old form-encoded POST /contact, now the body of POST /api/contact below (the only
    caller once /contact became a React island). Returns {"ok": True} on success, or
    {"ok": False, "error": "empty"|"consent"}. Message-emptiness is checked before consent —
    matching the original form-encoded route's precedence, so someone who DID write a message but
    forgot the checkbox is told about the checkbox, not that their message was empty."""
    message = message.strip()
    if not message:
        return {"ok": False, "error": "empty"}
    # 2026-09-25: explicit consent checkbox (compliance pass) — see this function's own docstring
    # for why this is checked after the empty-message case, not before.
    if not consent:
        return {"ok": False, "error": "consent"}

    telegram_user_id = int(uid_raw) if uid_raw.strip().isdigit() else None

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
    # regardless of whether this succeeds.
    notified = await asyncio.to_thread(
        _notify_owner_sync, name.strip(), email.strip(), message, telegram_user_id
    )
    if notified:
        await asyncio.to_thread(_mark_notified_sync, contact_message_id)

    return {"ok": True}


@app.post("/api/contact")
async def contact_submit(payload: ContactSubmission) -> dict:
    """JSON API the /contact React island's form submits to via fetch, replacing the old
    form-encoded POST /contact once that page became a React island (see contact() above). Always
    200 — validation failures are reported via {"ok": false, "error": ...} in the body rather than
    an HTTP error status, so the client only needs to branch on `ok`, not also juggle non-2xx
    responses for expected, recoverable input errors (an actual 5xx still means something
    unexpected broke)."""
    return await _process_contact_message(
        payload.name, payload.email, payload.message, payload.uid, payload.consent
    )


def _listing_action_ids(session, user_id: int, action: str) -> set[int]:
    """Same query as bot/handlers/apartments.py's find_matching_listings and bot/handlers/
    liked.py — shared here so the website reads the exact same UserListingAction rows: a listing
    liked/hidden from the Telegram bot's ❤️/🙈 buttons shows that state on the website instantly,
    and vice versa via POST /react below."""
    return set(
        session.scalars(
            select(UserListingAction.listing_id).where(
                UserListingAction.user_id == user_id, UserListingAction.action == action
            )
        ).all()
    )


APARTMENTS_PAGE_SIZE = 24

# The ordered ids of a user's current matches, per (user, filter contents, hidden listings), for _MATCH_IDS_TTL seconds
# - long enough that scrolling and coming back to /apartments doesn't redo the full scan, short enough that a listing
# scraped a moment ago shows up within a couple of minutes. A filter save or a hide changes the key, so it never shows
# stale results for the new filter.
_MATCH_IDS_TTL = 120.0
_MATCH_IDS_MAX_ENTRIES = 64
_match_ids_cache: "OrderedDict[tuple, tuple[float, list[int]]]" = OrderedDict()
_match_ids_lock = threading.Lock()


def _filter_fingerprint(filter_row) -> tuple:
    return tuple((column.key, repr(getattr(filter_row, column.key, None))) for column in Filter.__table__.columns)


def _cached_match_ids(session, user_id: int, filter_row, hidden_ids: set[int]) -> list[int]:
    key = (user_id, _filter_fingerprint(filter_row), frozenset(hidden_ids))
    now = time.monotonic()
    with _match_ids_lock:
        hit = _match_ids_cache.get(key)
        if hit is not None and now - hit[0] < _MATCH_IDS_TTL:
            _match_ids_cache.move_to_end(key)
            return hit[1]
    ids = [row.id for row in matching_listing_rows(session, filter_row, hidden_ids)]
    with _match_ids_lock:
        _match_ids_cache[key] = (now, ids)
        _match_ids_cache.move_to_end(key)
        while len(_match_ids_cache) > _MATCH_IDS_MAX_ENTRIES:
            _match_ids_cache.popitem(last=False)
    return ids


def _fill_missing_descriptions_in_background(listings: list[Listing]) -> None:
    """2026-10-05: fills in the details (description, floor, parking, elevator, balcony, safe room, future move-in) of
    the Yad2 listings shown on THIS page that never got them, in the background so the page never waits — see
    todira_common/listing_enrichment.py (Gemini URL-context only, serialised, deduplicated, bounded). Callers pass only
    the listings actually being shown (APARTMENTS_PAGE_SIZE for /apartments, the liked list for /liked). The page renders
    now with what exists; a filled-in listing shows its details on the NEXT view, by any viewer.

    History: 2026-09-07 first version (Bright Data DCA collector, later Web Unlocker, description only); replaced
    2026-10-05 — the owner decided listing details come only from Gemini (no paid fallback)."""
    listing_enrichment.fill_missing_in_background(listings)


_SOURCE_DISPLAY_NAMES = {
    "yad2": {"he": "יד2", "default": "Yad2"},
    "komo": {"he": "קומו", "default": "Komo"},
    "homeless": {"he": "הומלס", "default": "Homeless"},
    "facebook_marketplace": {"he": "פייסבוק", "default": "Facebook"},
    "facebook_groups": {"he": "פייסבוק", "default": "Facebook"},
}


def _attach_also_on(session, listings, lang: str | None) -> None:
    """2026-10-05 real owner request (matching dorin.app): the detail view says where ELSE the same
    apartment was posted. Cross-source duplicates are already detected at scrape time (Listing.
    duplicate_of_id points a duplicate at its canonical row, see scraper/dedup.py) but only the
    canonical row is ever shown, so its other sites were invisible. For every listing in `listings`
    this sets `.also_on` = [{"n": display name, "u": "/go/<id>"}, ...] for the OTHER still-active rows
    of the same apartment (the canonical row and/or its duplicates, never the listing itself; one entry
    per source). The link goes through /go/{id} like every other outbound link, so a real source URL
    never sits in the page HTML. Purely decorative, so it never breaks the page: any failure just
    leaves the line out."""
    items = [listing for listing in listings if listing is not None]
    if not items:
        return
    try:
        canonical_of = {item.id: (item.duplicate_of_id or item.id) for item in items}
        canon_ids = set(canonical_of.values())
        rows = session.execute(
            select(Listing.id, Listing.source, Listing.duplicate_of_id).where(
                Listing.is_delisted.is_(False),
                or_(Listing.id.in_(canon_ids), Listing.duplicate_of_id.in_(canon_ids)),
            )
        ).all()
        group: dict[int, list[tuple[int, str]]] = {}
        for row_id, source, dup_of in rows:
            group.setdefault(dup_of or row_id, []).append((row_id, source))
        key = lang if lang == "he" else "default"
        for item in items:
            seen = {item.source}
            entries = []
            for row_id, source in sorted(group.get(canonical_of[item.id], [])):
                if row_id == item.id or source in seen:
                    continue
                seen.add(source)
                names = _SOURCE_DISPLAY_NAMES.get(source)
                if names is None:
                    continue
                entries.append({"n": names.get(key, names["default"]), "u": f"/go/{row_id}"})
            item.also_on = entries
    except Exception:
        logger.warning("could not work out the 'also posted on' sites for a listing page", exc_info=True)


# 2026-10-14 owner request: "when you click a listing, the page itself should be rich and full, not look exactly like
# the card before I clicked". The detail view (apartments.html's openListingDetail) now loads this fragment: every
# fact we hold, laid out as a property sheet, the amenities we know either way, how the price compares with the same
# kind of flat around it, its price history, when we found it and when we last saw it live, every site it was posted
# on, a small map, and similar listings nearby. Only real data: a section with nothing to show is left out.
_ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")
_SIMILAR_LISTINGS_SHOWN = 4
_AREA_COMPARE_MIN_LISTINGS = 5
# Below this many comparable listings the page says the comparison rests on little data.
_AREA_COMPARE_SOLID_LISTINGS = 10
_AREA_COMPARE_WINDOW = dt.timedelta(days=30)
# Yad2's catch-all "rest of the city" bucket is not a real neighborhood, so it is compared with the whole city.
_NOT_A_NEIGHBORHOOD = {"שאר העיר"}
# Sizes outside this range are typos; they are left out of the price-per-m² median.
_PLAUSIBLE_SQM = (15, 500)


def _area_price_comparison(session, listing: Listing) -> dict | None:
    """How this listing's asking price compares with the same kind of listing around it - computed only from listings we
    collected ourselves, nothing estimated or looked up elsewhere (2026-10-14 owner request: "as real and honest as it
    can be").

    The peers: other listings (never this one, never a cross-site duplicate of the same flat) with the same deal type and
    room count, seen live in the last _AREA_COMPARE_WINDOW (so ones taken down recently - often because they were let -
    still count), a shared room only against shared rooms. In the same neighborhood when it has at least
    _AREA_COMPARE_MIN_LISTINGS of them, otherwise the whole city; fewer than that anywhere and there's no comparison.
    The median, not the average, so one mistyped price can't drag it. When this listing has a size, the median price per
    m² of the same peers (those with a plausible size) is returned too: a big flat can cost more and still be cheaper
    per m². These are asking prices from the ads, not the prices flats were finally let or sold for."""
    if not listing.price or not listing.city:
        return None
    conditions = [
        Listing.duplicate_of_id.is_(None),
        Listing.deal_type == listing.deal_type,
        Listing.price.is_not(None),
        Listing.price > 0,
        Listing.id != listing.id,
        Listing.city == listing.city,
        Listing.scraped_at >= func.now() - _AREA_COMPARE_WINDOW,
    ]
    if listing.duplicate_of_id is not None:
        conditions.append(Listing.id != listing.duplicate_of_id)
    if listing.rooms is not None:
        conditions.append(Listing.rooms == listing.rooms)
    if listing.property_type == "shared_room":
        conditions.append(Listing.property_type == "shared_room")
    else:
        conditions.append(or_(Listing.property_type.is_(None), Listing.property_type != "shared_room"))
    scopes = []
    if listing.neighborhood and listing.neighborhood not in _NOT_A_NEIGHBORHOOD:
        scopes.append((listing.neighborhood, [*conditions, Listing.neighborhood == listing.neighborhood]))
    scopes.append((listing.city, conditions))
    for area, where in scopes:
        median, count = session.execute(
            select(func.percentile_cont(0.5).within_group(Listing.price), func.count()).where(*where)
        ).one()
        if not median or count < _AREA_COMPARE_MIN_LISTINGS:
            continue
        median = float(median)
        result = {
            "area": area,
            "median": int(round(median, -1)),
            "count": count,
            "diff_pct": int(round((listing.price - median) / median * 100)),
            "solid": count >= _AREA_COMPARE_SOLID_LISTINGS,
            "sqm_median": None,
        }
        low, high = _PLAUSIBLE_SQM
        if listing.size_sqm and low <= listing.size_sqm <= high:
            per_sqm = cast(Listing.price, Float) / Listing.size_sqm
            sqm_median, sqm_count = session.execute(
                select(func.percentile_cont(0.5).within_group(per_sqm), func.count()).where(
                    *where, Listing.size_sqm.between(low, high)
                )
            ).one()
            if sqm_median and sqm_count >= _AREA_COMPARE_MIN_LISTINGS:
                result["sqm_median"] = int(round(float(sqm_median)))
                result["sqm_count"] = sqm_count
        return result
    return None


def _similar_listings(session, listing: Listing, hidden_ids: set[int]) -> list[Listing]:
    """Up to _SIMILAR_LISTINGS_SHOWN other live listings like this one: same city and deal type, rooms within half a
    room, price within 20%, the same neighborhood first, newest first."""
    if not listing.city:
        return []
    query = (
        select(Listing)
        .options(defer(Listing.raw_payload))
        .where(
            Listing.is_delisted.is_(False),
            Listing.duplicate_of_id.is_(None),
            Listing.deal_type == listing.deal_type,
            Listing.city == listing.city,
            Listing.id != listing.id,
        )
    )
    if listing.duplicate_of_id is not None:
        query = query.where(Listing.id != listing.duplicate_of_id)
    if listing.rooms is not None:
        query = query.where(Listing.rooms.between(listing.rooms - Decimal("0.5"), listing.rooms + Decimal("0.5")))
    if listing.price:
        query = query.where(Listing.price.between(int(listing.price * 0.8), int(listing.price * 1.2)))
    if hidden_ids:
        query = query.where(Listing.id.not_in(hidden_ids))
    order = [Listing.first_seen_at.desc(), Listing.id.desc()]
    if listing.neighborhood:
        order.insert(0, case((Listing.neighborhood == listing.neighborhood, 0), else_=1))
    return list(session.scalars(query.order_by(*order).limit(_SIMILAR_LISTINGS_SHOWN)))


def _local_time(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(_ISRAEL_TZ)


@app.get("/apartments/listing/{listing_id}/details")
def listing_details(request: Request, listing_id: int, uid: int | None = None):
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return Response(status_code=401)
        listing = session.get(Listing, listing_id)
        if listing is None:
            return Response(status_code=404)
        lang = get_lang(request, user.language)
        _attach_also_on(session, [listing], lang)
        hidden_ids = _listing_action_ids(session, user.id, "hidden")
        try:
            area = _area_price_comparison(session, listing)
        except Exception:
            logger.warning("could not compare listing %s with its area", listing_id, exc_info=True)
            area = None
        try:
            similar = _similar_listings(session, listing, hidden_ids)
        except Exception:
            logger.warning("could not find listings similar to %s", listing_id, exc_info=True)
            similar = []
        source_names = _SOURCE_DISPLAY_NAMES.get(listing.source) or {}
        context = {
            "l": listing,
            "area": area,
            "similar": similar,
            "source_name": source_names.get("he" if lang == "he" else "default", listing.source),
            "posted_on": _local_time(listing.posted_at),
            "first_seen": _local_time(listing.first_seen_at),
            "last_seen": _local_time(listing.scraped_at),
            "price_changed_on": _local_time(listing.price_changed_at),
            "delisted_on": _local_time(listing.delisted_at),
            "price_per_sqm": (
                int(round(listing.price / listing.size_sqm)) if listing.price and listing.size_sqm else None
            ),
        }
    return _render(request, "_listing_details.html", context, known_lang=user.language)


@app.get("/go/{listing_id}")
def go_to_listing_source(request: Request, listing_id: int):
    """Redirects to a listing's original source page, so _listing_card.html and the "also posted on" links never put
    the real URL in a page's HTML. Resolved server-side, one listing at a time, on the click.

    2026-10-18 (owner): this route used to be open to everyone - the paywall popup had a "view the original listing"
    link through it, so the poster could be reached without paying and nobody upgraded. Now it needs the same access
    as the card's own "view listing" link (has_access); anyone else goes to /upgrade."""
    with get_session() as session:
        user = _resolve_user(request, session, None)
        if user is None or not _effective_access(request, user):
            return RedirectResponse("/upgrade", status_code=303)
        listing = session.get(Listing, listing_id)
        if listing is None:
            raise StarletteHTTPException(status_code=404)
        return RedirectResponse(listing.url, status_code=302)


@app.get("/apartments")
def apartments(
    request: Request,
    uid: int | None = None,
    offset: int = 0,
    fragment: bool = False,
    listing: int | None = None,
):
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "apartments"})
        # See i18n.get_lang's own docstring: an identified visitor's own on-file language
        # preference wins over guessing from Accept-Language (2026-09-29 real bug — Telegram's
        # in-app browser sends the phone's system language, not the bot's own chosen language).
        lang = get_lang(request, user.language)
        if user.filter is None:
            return _render(request, "no_filter.html", {"uid": user.telegram_user_id}, known_lang=user.language)

        hidden_ids = _listing_action_ids(session, user.id, "hidden")
        # 2026-10-14: measured live at 16-27 s per page (and per infinite-scroll batch) - see listing_matches.py's
        # MATCH_COLUMNS comment. The match scan now reads light rows only, and its result (just the ordered ids) is
        # kept for a couple of minutes per user + filter + hidden set, so scrolling loads only the next 24 listings.
        match_ids = _cached_match_ids(session, user.id, user.filter, hidden_ids)
        page_items = [
            listing
            for listing in load_listings(session, match_ids[offset : offset + APARTMENTS_PAGE_SIZE])
            if not listing.is_delisted  # taken down since the ids were cached
        ]
        next_offset = offset + APARTMENTS_PAGE_SIZE
        has_more = next_offset < len(match_ids)
        liked_ids = _listing_action_ids(session, user.id, "liked")
        # Only true when this page was actually reached via the real, signed session cookie — the
        # "insecure temporary access" notice below must not show for a real login just because a
        # stale ?uid= also happens to be sitting in the URL from an older bookmark/deep link.
        via_session = request.session.get("user_id") == user.id
        has_access = _effective_access(request, user)
        has_paid_access = _effective_paid_access(request, user)
        # 2026-09-27 real owner request, matching dorin.app: the "view apartment" link sent in a
        # Telegram match notification should land straight on THAT listing's own detail
        # view, not just the generic /apartments grid. The listing that matched at send time might
        # no longer be in `matches` by the time it's clicked (filter changed, or it's since fallen
        # off the paginated window — matches is ordered newest-first with no guaranteed position),
        # so this is fetched independently of the filter/pagination above, same as /go/{id}'s own
        # direct-by-id lookup. Still behind the normal has_access gate below (via listing_card's own
        # {% if has_access %} checks) — a deep link doesn't bypass the contact-info paywall.
        deep_link_listing = session.get(Listing, listing) if listing is not None else None
        _attach_also_on(session, [*page_items, deep_link_listing], lang)

    if has_access:
        _fill_missing_descriptions_in_background(page_items)

    context = {
        "listings": page_items,
        "total_count": len(match_ids),
        "next_offset": next_offset,
        "has_more": has_more,
        "uid": user.telegram_user_id,
        "user": user,
        "via_session": via_session,
        "has_access": has_access,
        "has_paid_access": has_paid_access,
        "access_state": _effective_access_state(request, user),
        "liked_ids": liked_ids,
        "hidden_ids": set(),
        "deep_link_listing": deep_link_listing,
    }
    if fragment:
        # AJAX "load more" request (see apartments.html's own script) — just the next batch of
        # cards plus a fresh sentinel, no base.html layout at all.
        return _render(request, "_listing_cards_fragment.html", context, known_lang=user.language)

    # 2026-09-24: sidebar filter panel (dorin.app-style layout the owner asked for) reuses the
    # SAME field partial /filter's own full-page form does (_filter_form_fields.html) — needs the
    # same label dicts that route already builds, see filter_view above.
    context.update(
        {
            "f": user.filter,
            "cities_list": sorted(CITIES),
            **_LOCALITY_PICKER_CONTEXT,
            "property_type_labels": PROPERTY_TYPE_LABELS.get(lang, PROPERTY_TYPE_LABELS[DEFAULT_LANG]),
            "safe_room_labels": SAFE_ROOM_LABELS.get(lang, SAFE_ROOM_LABELS[DEFAULT_LANG]),
            "furniture_labels": FURNITURE_LABELS.get(lang, FURNITURE_LABELS[DEFAULT_LANG]),
        }
    )

    return _render(
        request,
        "apartments.html",
        context,
        known_lang=user.language,
    )


@app.get("/liked")
def liked(request: Request, uid: int | None = None):
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "liked"})

        liked_ids = _listing_action_ids(session, user.id, "liked")
        listings = (
            session.scalars(select(Listing).where(Listing.id.in_(liked_ids))).all()
            if liked_ids
            else []
        )
        has_access = _effective_access(request, user)
        has_paid_access = _effective_paid_access(request, user)
        _attach_also_on(session, listings, get_lang(request, user.language))

    if has_access:
        _fill_missing_descriptions_in_background(listings)

    return _render(
        request,
        "liked.html",
        {
            "listings": listings,
            "uid": user.telegram_user_id,
            "user": user,
            "has_access": has_access,
            "has_paid_access": has_paid_access,
            "access_state": _effective_access_state(request, user),
            "liked_ids": liked_ids,
            "hidden_ids": set(),
        },
        known_lang=user.language,
    )


@app.get("/hidden")
def hidden(request: Request, uid: int | None = None):
    """Mirrors /liked exactly, for action="hidden" — the website equivalent of the Telegram bot's
    /hidden command (bot/handlers/liked.py), added so a listing hidden from either channel can also
    be brought back (🙈 toggles) from either channel, not just the one it was hidden from."""
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "hidden"})

        hidden_ids = _listing_action_ids(session, user.id, "hidden")
        listings = (
            session.scalars(select(Listing).where(Listing.id.in_(hidden_ids))).all()
            if hidden_ids
            else []
        )
        has_access = _effective_access(request, user)
        has_paid_access = _effective_paid_access(request, user)
        _attach_also_on(session, listings, get_lang(request, user.language))

    return _render(
        request,
        "hidden.html",
        {
            "listings": listings,
            "uid": user.telegram_user_id,
            "user": user,
            "has_access": has_access,
            "has_paid_access": has_paid_access,
            "access_state": _effective_access_state(request, user),
            "liked_ids": set(),
            "hidden_ids": hidden_ids,
        },
        known_lang=user.language,
    )


@app.post("/react")
def react_toggle(
    request: Request,
    listing_id: int = Form(...),
    action: str = Form(...),
    uid: int | None = Form(None),
    next: str = Form("/apartments"),
):
    """Website equivalent of the Telegram bot's ❤️/🙈 inline buttons (bot/handlers/liked.py's
    _apply_reaction_sync) — same UserListingAction table and the same toggle-on-repeat semantics
    (press again to undo), so liking/hiding a listing from either channel is reflected in both."""
    if action not in ("like", "hide"):
        raise StarletteHTTPException(status_code=404)
    db_action = "liked" if action == "like" else "hidden"

    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "apartments"})
        listing_id = shown_listing_id(session, listing_id)

        existing_id = session.scalar(
            select(UserListingAction.id).where(
                UserListingAction.user_id == user.id,
                UserListingAction.listing_id == listing_id,
                UserListingAction.action == db_action,
            )
        )
        if existing_id is not None:
            session.execute(delete(UserListingAction).where(UserListingAction.id == existing_id))
            session.commit()
        else:
            # 2026-09-24 real bug fix: a genuine double-click/double-tap fires two near-simultaneous
            # POSTs for the SAME listing_id+action — both can pass the existing_id SELECT above
            # before either commits (neither sees the other's row yet), so the second one to commit
            # hits UserListingAction's own unique constraint (uq_user_listing_actions) and used to
            # 500 instead of just... the action already being on, which is exactly what the user
            # wanted from either click. A DELETE never has this problem (deleting an already-deleted
            # row is a normal no-op, not an error), so only this INSERT branch needs the guard.
            session.add(UserListingAction(user_id=user.id, listing_id=listing_id, action=db_action))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()

    # same-origin relative path only — `next` is attacker-controllable form input, never redirect
    # anywhere else with it.
    return RedirectResponse(_safe_next(next), status_code=303)


@app.post("/apartments/no-brokers")
def toggle_no_brokers(
    request: Request, uid: int | None = Form(None)
):
    """Quick shortcut for Filter.no_brokers — the field already existed (a full checkbox on
    /filter), just had no one-click way to flip it from /apartments itself, unlike the reference
    product's own quick broker-filter link. A plain form POST, matching /account/notifications."""
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None or user.filter is None:
            return _render(request, "need_uid.html", {"target": "apartments"})
        user.filter.no_brokers = not user.filter.no_brokers
        session.commit()

    return RedirectResponse(_identity_redirect_url("/apartments", uid), status_code=303)


def _mark_matches_seen_in_background(user_id: int) -> None:
    """After a filter change on the website: what already matches is recorded as sent, so the scraper's next run does
    not push a week of older listings at once (listing_matches.mark_recent_matches_seen has the bug this fixes).
    Off the request thread - the page never waits for it."""
    def _run() -> None:
        try:
            with get_session() as session:
                filter_row = session.scalar(select(Filter).where(Filter.user_id == user_id))
                if filter_row is not None:
                    mark_recent_matches_seen(session, user_id, filter_row)
        except Exception:
            logger.exception("could not record the current matches as seen after a filter change")

    threading.Thread(target=_run, daemon=True).start()


@app.post("/filter/region")
def filter_set_region(
    request: Request,
    uid: int | None = Form(None),
    kind: str = Form(...),
    sw_lat: float | None = Form(None),
    sw_lng: float | None = Form(None),
    ne_lat: float | None = Form(None),
    ne_lng: float | None = Form(None),
    center_lat: float | None = Form(None),
    center_lng: float | None = Form(None),
    radius_m: int | None = Form(None),
):
    """Map-drawn region filter (real owner request, backlog #79) — a rectangle or circle the
    visitor draws directly on /apartments' own map (apartments.html's own draw-mode script)
    narrows the listing set to that area ON TOP OF the existing city filter (both apply — AND, not
    OR), the same "further narrows, never widens" relationship city/price/rooms already have with
    each other. Persisted on Filter (not session-only) so it survives a reload, and since
    matching.evaluate() is the SAME matcher /apartments and the bot's proactive Telegram
    notifications both use, a saved region also narrows which NEW listings notify the visitor —
    not just what /apartments shows on load."""
    if kind not in ("rect", "circle", "clear"):
        raise StarletteHTTPException(status_code=400)

    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None or user.filter is None:
            return _render(request, "need_uid.html", {"target": "apartments"})

        f = user.filter
        if kind == "clear":
            f.map_region_kind = None
            f.map_center_lat = f.map_center_lng = f.map_radius_m = None
            f.map_sw_lat = f.map_sw_lng = f.map_ne_lat = f.map_ne_lng = None
        elif kind == "rect":
            if None in (sw_lat, sw_lng, ne_lat, ne_lng):
                raise StarletteHTTPException(status_code=400)
            f.map_region_kind = "rect"
            f.map_sw_lat, f.map_sw_lng = sw_lat, sw_lng
            f.map_ne_lat, f.map_ne_lng = ne_lat, ne_lng
            f.map_center_lat = f.map_center_lng = f.map_radius_m = None
        else:  # circle
            if None in (center_lat, center_lng, radius_m) or radius_m <= 0:
                raise StarletteHTTPException(status_code=400)
            f.map_region_kind = "circle"
            f.map_center_lat, f.map_center_lng = center_lat, center_lng
            f.map_radius_m = radius_m
            f.map_sw_lat = f.map_sw_lng = f.map_ne_lat = f.map_ne_lng = None
        session.commit()
        _mark_matches_seen_in_background(user.id)

    return RedirectResponse(_identity_redirect_url("/apartments", uid), status_code=303)


def _is_owner_id(telegram_user_id: int | None) -> bool:
    """Gate for /admin/messages — deliberately keyed off the SAME OWNER_TELEGRAM_USER_ID secret
    that both the /contact form and the bot's contact-fallback handler already forward to, rather
    than a separate admin token/password: "who receives contact notifications" and "who can view
    the inbox on the website" should never be able to drift apart into two different people.
    String comparison (not int()) since OWNER_TELEGRAM_USER_ID is a raw secret string that could
    in principle contain non-numeric noise — this way a malformed secret just never matches
    instead of throwing."""
    return bool(OWNER_TELEGRAM_USER_ID) and str(telegram_user_id) == str(OWNER_TELEGRAM_USER_ID)


def _preview_as_free(request: Request) -> bool:
    """2026-09-05: a self-toggled, session-scoped flag (see /preview/toggle) that lets the owner
    see exactly what a brand-new, never-subscribed visitor sees — no owner bypass, no trial, no
    active subscription — without touching his own account's trial_ends_at/paid_until row or the
    OWNER_TELEGRAM_USER_ID secret. Off by default; never set for anyone but the owner, since the
    toggle route itself is owner-gated."""
    return bool(request.session.get("preview_as_free"))


def _display_is_owner(request: Request, telegram_user_id: int | None) -> bool:
    """Real owner status, minus the preview-as-regular-user override above — used wherever owner
    status is DISPLAYED (nav admin links, the upgrade page's "you're the owner" banner). Actual
    authorization (admin routes, _require_owner) always checks _is_owner_id directly instead, so
    admin functionality never actually goes away during a preview — only what's shown does."""
    return _is_owner_id(telegram_user_id) and not _preview_as_free(request)


def _effective_access(request: Request, user: User) -> bool:
    """has_full_access, minus the same preview override — forces "no access at all" regardless of
    the owner bypass or the account's real trial_ends_at/paid_until, so a preview reliably shows
    the real paywall even if the owner's own trial happens to still be technically valid."""
    if _preview_as_free(request):
        return False
    return has_full_access(user, is_owner=_is_owner_id(user.telegram_user_id))


def _effective_access_state(request: Request, user: User) -> str:
    """todira_common.access.access_state, with the same preview override as _effective_access: the cards and the
    /apartments notice say WHY the original listing is locked - the free trial ended, or a paid period ended
    (2026-10-19, owner)."""
    if _preview_as_free(request):
        return ACCESS_TRIAL_ENDED
    return access_state(user, is_owner=_is_owner_id(user.telegram_user_id))


def _effective_paid_access(request: Request, user: User) -> bool:
    """Same preview-override pattern as _effective_access, but backed by has_paid_access — a real
    subscription only, the free trial doesn't count (2026-09-27 owner decision, see that
    function's own docstring). Used only for the listing card's contact button; every other access-gated surface keeps using _effective_access
    above, unchanged."""
    if _preview_as_free(request):
        return False
    return has_paid_access(user, is_owner=_is_owner_id(user.telegram_user_id))


@app.get("/preview/toggle")
def preview_toggle(request: Request, next: str = "/account"):
    """Owner-only. Flips the session-scoped preview_as_free flag so the owner can see the site
    exactly as a regular, trial-expired, never-subscribed user would — the real gated listing
    cards and the real /upgrade paywall — then flip it back once done. No DB writes, nothing
    touches OWNER_TELEGRAM_USER_ID; a plain visitor hitting this route (not logged in as the
    owner) gets a 404, same posture as the other /admin/* routes."""
    current_user = _current_user_summary(request)
    if current_user is None or not _is_owner_id(current_user["telegram_user_id"]):
        return _render(request, "404.html", {}, status_code=404)
    request.session["preview_as_free"] = not _preview_as_free(request)
    return RedirectResponse(_safe_next(next), status_code=303)


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
    user, from any device, regardless of which channel they signed up through (Telegram/Google are
    both just columns on the same `users` row) — a real, explicit request (2026-09-04), not
    something Google/Telegram each need their own separate tool for."""
    with get_session() as session:
        if _require_owner(request, session) is None:
            return _render(request, "404.html", {}, status_code=404)

        users = session.scalars(select(User).order_by(User.created_at.desc()).limit(500)).all()
        now = dt.datetime.now(dt.timezone.utc)
        rows = [
            {
                "id": u.id,
                "label": u.first_name or u.telegram_username or f"#{u.id}",
                # 2026-10-19 (owner): split by sign-up channel on one page - Telegram only, Google only, or both (one card).
                "kind": ("both" if u.telegram_user_id and u.google_sub else "telegram" if u.telegram_user_id
                         else "google" if u.google_sub else "none"),
                "has_telegram": u.telegram_user_id is not None,
                "telegram_username": u.telegram_username,
                "has_google": u.google_sub is not None,
                "google_email": u.google_email,
                "created_at": u.created_at,
                "free_access_granted": u.free_access_granted,
                "has_access": has_full_access(u, is_owner=_is_owner_id(u.telegram_user_id)),
                "trial_ends_at": u.trial_ends_at,
                "paid_until": u.paid_until,
                "in_trial": u.trial_ends_at is not None and now < u.trial_ends_at,
            }
            for u in users
        ]

    counts = {kind: sum(1 for r in rows if r["kind"] == kind) for kind in ("telegram", "google", "both", "none")}
    return _render(request, "admin_users.html", {"rows": rows, "counts": counts})


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


@app.get("/upgrade")
def upgrade(request: Request, uid: int | None = None):
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "upgrade"})
        access = _effective_access(request, user)

    return _render(
        request,
        "upgrade.html",
        {
            "uid": user.telegram_user_id,
            "has_access": access,
            # named display_is_owner, not is_owner: _render() always overwrites an "is_owner" key
            # with the real session-based nav-admin-link check, so a route-supplied one was silently
            # dropped here — a pre-existing bug (the owner banner below never actually showed unless
            # already signed in with a real session) found while fixing the same collision on /account.
            "display_is_owner": _display_is_owner(request, user.telegram_user_id),
            "trial_ends_at": user.trial_ends_at,
            "paid_until": user.paid_until,
            "subscription_plan": SUBSCRIPTION_PLAN,
            "subscription_price": PLAN_PRICES_ILS[SUBSCRIPTION_PLAN],
            # 2026-09-24 real bug fix: this used to also require `not user.cancel_at_period_end`,
            # which meant a subscription the user had CANCELLED (but whose current paid period
            # hasn't lapsed yet — see account_cancel_subscription's own comment: Takbull's own
            # subscription stays live and billing until then, only a local flag changes) read as
            # "no active subscription" here. That let a user land back on this page and open a
            # SECOND new Takbull recurring order while the first one was still actively billing —
            # the webhook below then overwrites user.takbull_subscription_uniqid with the new
            # order's id, permanently losing the only reference this app had to the still-live old
            # one (no uniqid on file, so the daily housekeeping job that's supposed to cancel it
            # once the period ends has nothing to call Takbull's CancelSubscription API with) —
            # real, unrecoverable double-billing. /account's own has_active_subscription (below,
            # unchanged) never had this exception — this brings /upgrade in line with it.
            "has_active_subscription": user.takbull_subscription_uniqid is not None,
            "recurring_configured": takbull_client.recurring_api_configured(),
            "hosted_page_configured": takbull_client.hosted_page_configured(),
            # 2026-10-06: the free hosted-page flow sells three one-time passes (no auto-renewal) - see upgrade.html.
            "one_time_mode": (
                takbull_client.hosted_page_configured() and not takbull_client.recurring_api_configured()
            ),
            "pass_plans": _pass_plan_cards(),
            # 2026-10-13 (owner decision): one button to Takbull's shared page, where the pass is picked - see
            # takbull_client.pass_is_picked_on_takbull.
            "pass_picked_on_takbull": takbull_client.pass_is_picked_on_takbull(),
            "pass_choice_value": _PASS_PICKED_ON_TAKBULL,
        },
        known_lang=user.language,
    )


# What the single /upgrade button posts as `plan` when the customer picks the pass on Takbull's shared page. The pending
# Payment is stored as the longest pass until the webhook rewrites plan and amount from what was actually charged.
_PASS_PICKED_ON_TAKBULL = "pass_choice"


# 2026-10-13 (owner request: every city, moshav, kibbutz, village and area): the filter form's city picker shows the
# major cities as before; every other locality, and every area (a click selects all its localities), appears when the
# search box matches it (_filter_form_fields.html). Built once - the lists are static.
_LOCALITY_PICKER_CONTEXT = {
    "extra_localities_list": sorted(name for name in LOCALITIES if name not in CITIES),
    # 2026-10-19: a place's second name ("זרעית" for "כפר רוזנואלד") finds it too.
    "other_locality_names": sorted(SECOND_NAMES.items()),
    "city_regions_list": sorted(REGIONS.items()),
}


def _pass_plan_cards() -> list[dict]:
    """The one-time access passes shown on /upgrade, cheapest first: plan key, days, price and price per day. The
    longest pass is flagged as the best value."""
    cards = []
    for plan in PASS_PLANS:
        days = PLAN_DURATIONS[plan].days
        price = PLAN_PRICES_ILS[plan]
        cards.append(
            {
                "plan": plan,
                "days": days,
                "price": price,
                "per_day": (price / days).quantize(Decimal("0.01")),
                "best": plan == PASS_PLANS[-1],
            }
        )
    return cards


@app.post("/upgrade")
def upgrade_submit(
    request: Request,
    plan: str = Form(...),
    uid: int | None = Form(None),
    terms_agreed: bool = Form(False),
):
    """Plan selection — 2026-09-21: the only real plan is the recurring ₪49.90/month subscription
    (SUBSCRIPTION_PLAN); the earlier one-time weekly/biweekly/monthly plans are no longer offered
    (their PLAN_PRICES_ILS/PLAN_DURATIONS entries stay only so historical Payment rows still
    resolve). Tries the real gateway first, falling back to the informal model:
    1. Takbull's real recurring API (2026-09-21) once TAKBULL_WEBHOOK_SECRET/TAKBULL_API_KEY/
       TAKBULL_API_SECRET are all configured — see takbull_client.py's module docstring for the
       real API this is built from. Creates a pending Payment, calls Takbull to open a NEW
       recurring order, and redirects to that order's own checkout URL; access is granted (and
       User.takbull_subscription_uniqid set) only once /webhooks/takbull below confirms the first
       real charge. Every later month's charge is Takbull's own recurring engine firing
       automatically, not anything this route does again.
    2. The earlier informal click-trust model (2026-09-04 decision: the click itself IS the
       payment signal, a Bit transfer happens outside this system) whenever Takbull isn't
       configured yet.
    The owner's /admin/users free-access toggle remains the remedy for a click/payment that turns
    out not to have actually happened, under either model.

    2026-09-17: terms_agreed is a real, required field now (see upgrade.html's own checkbox) — the
    payment processor's own compliance requirement is active, explicit consent to the Terms of Use
    (which now covers the cancellation/refund policy, see terms.html) before proceeding to
    checkout, not just a passive footer link. The HTML5 `required` attribute already blocks a
    normal browser submission without it; this is the server-side backstop for a tampered/
    non-browser request, same "don't trust the client alone" pattern as the plan check below."""
    one_time_mode = takbull_client.hosted_page_configured() and not takbull_client.recurring_api_configured()
    if one_time_mode and plan == SUBSCRIPTION_PLAN:
        plan = PASS_PLANS[-1]  # an old page / bookmark still posting the monthly plan: the 30-day pass
    # The single button (the pass is picked on Takbull's shared page): no page of a specific pass, and a placeholder plan.
    page_plan: str | None = plan
    if one_time_mode and plan == _PASS_PICKED_ON_TAKBULL and takbull_client.pass_is_picked_on_takbull():
        plan, page_plan = PASS_PLANS[-1], None
    allowed_plans = PASS_PLANS if one_time_mode else (SUBSCRIPTION_PLAN,)
    if plan not in allowed_plans or not terms_agreed:
        return _render(request, "auth_error.html", {}, status_code=400)

    amount = PLAN_PRICES_ILS[plan]

    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "upgrade"})

        # 2026-09-24 real bug fix, server-side backstop for the same reason as the terms_agreed
        # check above ("don't trust the client alone") — the GET /upgrade page already hides this
        # form once has_active_subscription is true (see that route's own comment for the full
        # incident), but a stale page, a direct POST, or a race could still reach here. A user with
        # ANY existing takbull_subscription_uniqid — cancelled-but-not-lapsed included — already has
        # a real, still-billing Takbull subscription; opening a second one here is exactly the
        # orphaned-subscription double-billing bug this whole comment chain documents. Redirect to
        # /account, where resume/cancel for the EXISTING subscription already live.
        if user.takbull_subscription_uniqid is not None:
            redirect_uid = user.telegram_user_id
            uid_qs = f"?uid={redirect_uid}" if redirect_uid else ""
            return RedirectResponse(f"/account{uid_qs}", status_code=303)

        if takbull_client.recurring_api_configured():
            payment = Payment(
                user_id=user.id, plan=plan, amount_ils=amount, status="pending", gateway="takbull"
            )
            session.add(payment)
            session.commit()
            payment_id = payment.id
            redirect_uid = user.telegram_user_id
            uid_qs = f"&uid={redirect_uid}" if redirect_uid else ""
            secret = os.environ.get(takbull_client.WEBHOOK_SECRET_ENV_VAR, "").strip()
            result = takbull_client.create_subscription_checkout_url(
                payment_id=payment_id,
                amount_ils=str(amount),
                customer_full_name=user.first_name,
                customer_email=None,
                redirect_address=f"{WEBSITE_URL}/upgrade/success?payment_id={payment_id}{uid_qs}",
                cancel_address=(
                    f"{WEBSITE_URL}/upgrade?{uid_qs.lstrip('&')}"
                    if redirect_uid
                    else f"{WEBSITE_URL}/upgrade"
                ),
                ipn_address=f"{WEBSITE_URL}/webhooks/takbull/{secret}",
            )
            if result is None:
                payment.status = "failed"
                session.commit()
                return _render(request, "auth_error.html", {}, status_code=502)
            checkout_url, uniqid = result
            payment.subscription_uniqid = uniqid
            session.commit()
            return RedirectResponse(checkout_url, status_code=303)

        if takbull_client.hosted_page_configured():
            # 2026-10-05: the FREE flow (owner decision: no paid Takbull package for now) — one hosted payment page,
            # ₪49.90 = 30 days of access, no auto-renewal, confirmed by Takbull's free automation webhook
            # (POST /webhooks/takbull/<secret>); see takbull_client.hosted_page_configured. The Payment row is pending
            # until that webhook matches a real charge back to it.
            payment = Payment(
                user_id=user.id, plan=plan, amount_ils=amount, status="pending", gateway="takbull"
            )
            session.add(payment)
            session.commit()
            checkout_url = takbull_client.build_hosted_checkout_url(
                payment_id=payment.id, email=user.google_email, plan=page_plan
            )
            if checkout_url is None:
                return _render(request, "auth_error.html", {}, status_code=502)
            return RedirectResponse(checkout_url, status_code=303)

        payment = Payment(
            user_id=user.id, plan=plan, amount_ils=amount, status="pending", gateway=None
        )
        session.add(payment)
        session.commit()
        payment_id = payment.id
        redirect_uid = user.telegram_user_id
        qs = f"?payment_id={payment_id}" + (f"&uid={redirect_uid}" if redirect_uid else "")
        return RedirectResponse(f"/upgrade/pay{qs}", status_code=303)


@app.get("/upgrade/success")
def upgrade_success(request: Request, payment_id: int | None = None, uid: int | None = None):
    """Landing page for every payment path: where the payment gateway redirects the browser after checkout
    (access is granted server-to-server by /webhooks/takbull below, which may land slightly before or
    after this redirect — this just reports the payment's CURRENT status, never grants anything
    itself), where /upgrade/pay/confirm below sends the browser after the informal Bit/PayBox flow
    (there access WAS already granted by that POST, so this always shows "paid" immediately), and
    Takbull's own static "דף תודה" (thank-you page) redirect — 2026-09-18 real request, configured
    directly in Takbull's dashboard (Payment Page settings), NOT per-transaction like a success_url,
    so it never carries payment_id/uid at all. payment_id is optional for exactly that
    case: landing here with no payment_id at all means "Takbull's own thank-you redirect, which
    only ever fires after a real successful charge on their side" — shown as paid immediately
    rather than looked up, since there's nothing to look up."""
    if payment_id is None:
        # 2026-10-05: when we can tell WHO is looking (a signed session or link), report that user's real latest
        # Takbull payment instead of assuming — the thank-you page can open a few seconds before the webhook lands,
        # and upgrade_success.html refreshes itself every 4s until it reads "paid". Unknown visitor: keep the old
        # behaviour (this redirect only fires after a real charge on Takbull's side; nothing is granted here).
        with get_session() as session:
            user = _resolve_user(request, session, uid)
            if user is None:
                return _render(request, "upgrade_success.html", {"uid": uid, "paid": True})
            latest = session.scalar(
                select(Payment)
                .where(Payment.user_id == user.id, Payment.gateway == "takbull")
                .order_by(Payment.id.desc())
                .limit(1)
            )
            paid = latest is None or latest.status == "paid"
            redirect_uid = user.telegram_user_id
        return _render(request, "upgrade_success.html", {"uid": redirect_uid, "paid": paid})
    with get_session() as session:
        payment = session.get(Payment, payment_id)
    paid = payment is not None and payment.status == "paid"
    return _render(request, "upgrade_success.html", {"uid": uid, "paid": paid})


@app.get("/upgrade/pay")
def upgrade_pay(request: Request, payment_id: int | None = None, uid: int | None = None):
    """Informal Bit/PayBox payment instructions (2026-09-05) — no verified "open the app
    pre-filled" deep link exists for either (see OWNER_BIT_PHONE's own comment), so this just
    shows the exact amount + the owner's Bit phone / PayBox link plainly, with a self-service
    "I paid" confirmation below. Same honesty tradeoff as the old instant-grant-on-click flow —
    still trusted, not verified — just made into an explicit, visible step instead of an invisible
    side effect of clicking a plan button."""
    if payment_id is None:  # an old or cut-off link: back to the plans, not a raw validation error
        return RedirectResponse("/upgrade", status_code=303)
    with get_session() as session:
        payment = session.get(Payment, payment_id)
        user = _resolve_user(request, session, uid)
        if user is None or payment is None or payment.user_id != user.id or payment.gateway is not None:
            return _render(request, "404.html", {}, status_code=404)
        redirect_uid = user.telegram_user_id

    return _render(
        request,
        "upgrade_pay.html",
        {
            "uid": redirect_uid,
            "payment_id": payment.id,
            "amount": payment.amount_ils,
            "plan": payment.plan,
            "already_paid": payment.status == "paid",
            "bit_phone": OWNER_BIT_PHONE,
            "paybox_url": OWNER_PAYBOX_URL,
        },
        known_lang=user.language,
    )


@app.post("/upgrade/pay/confirm")
def upgrade_pay_confirm(request: Request, payment_id: int = Form(...), uid: int | None = Form(None)):
    """Self-service "I paid" confirmation for the informal flow ONLY (gateway=None). A pending
    Takbull payment must never be confirmable from here: its own gateway webhook is the only
    thing allowed to mark it paid, otherwise anyone could POST /upgrade (creating their own
    pending gateway payment) and then confirm it themselves for free access — found 2026-09-30 in
    a code-review pass, unexploitable only while no real gateway is configured."""
    with get_session() as session:
        payment = session.get(Payment, payment_id)
        user = _resolve_user(request, session, uid)
        if user is None or payment is None or payment.user_id != user.id or payment.gateway is not None:
            return _render(request, "404.html", {}, status_code=404)

        if payment.status == "pending":
            extend_paid_until(user, payment.plan)
            payment.status = "paid"
            payment.paid_at = dt.datetime.now(dt.timezone.utc)
            session.commit()
        redirect_uid = user.telegram_user_id

    uid_qs = f"&uid={redirect_uid}" if redirect_uid else ""
    return RedirectResponse(f"/upgrade/success?payment_id={payment_id}{uid_qs}", status_code=303)


def _looks_like_a_successful_takbull_payload(body: dict) -> bool:
    """Per Takbull's own published Webhook guide's example payload for the order-success event
    (Id/uniqId/OrderNumber/order_reference/CustomerFullName/CustomerEmail/CustomerPhone/
    OrderStatus/StatusCode/StatusDescription/OrderTotalSum/Action/IsSubscriptionPayment) —
    confirmed from their docs, not guessed. StatusDescription=="Success" is the clearest signal;
    StatusCode==0 backs it up in case wording ever changes.

    2026-09-21: takbull.co.il's own official API docs site (found live, separately from the PDF
    above) documents a DIFFERENT example shape for the same IPN/ValidateNotification concept —
    {"Status": "Approved", "Amount": ..., "TransactionId": ..., ...} — genuinely a third
    inconsistent shape alongside the PDF's own two (see create_subscription_checkout_url's own
    2026-09-21 comment for the same pattern on a different endpoint). Recognized here too rather
    than betting on only one source being the real one."""
    status_description = str(body.get("StatusDescription", "")).strip().lower()
    if status_description == "success":
        return True
    if str(body.get("Status", "")).strip().lower() == "approved":
        return True
    return body.get("StatusCode") == 0 and body.get("OrderStatus") is not None


def _check_takbull_secret(secret: str) -> bool:
    expected_secret = os.environ.get(takbull_client.WEBHOOK_SECRET_ENV_VAR, "").strip()
    return bool(expected_secret) and hmac.compare_digest(secret, expected_secret)


@app.get("/webhooks/takbull/{secret}")
async def webhooks_takbull_get(request: Request, secret: str):
    """The REAL Takbull IPN mechanism — found live 2026-09-21 (owner: "האם זה קשור בכלל לGET?"),
    confirmed against the PDF's own Authentication/IPN section, word for word: "GET — IPN —
    Instant Payment Notification... Takbull calls your IPNAddress..." with a real example URL
    shaped as query params (uniqId/order_reference/statusCode/statusDescription/takbullAction/
    transactionInternalNumber), NOT a POST with a JSON body. The @app.post handler below was built
    on an assumed payload shape that was never actually confirmed against this section — almost
    certainly the real reason the webhook "never fires" was reported earlier: every real GET from
    Takbull would have hit this same path as a POST-only route and been rejected outright (405),
    silently, this whole time. Every "successful" test before this was a manual POST simulating a
    payload shape this project guessed at, not a real Takbull-triggered call.

    The GET ping itself carries no amount/subscription info — the PDF is explicit: "On receiving
    the IPN, call ValidateNotification with the uniqId to confirm payment details" — so this calls
    takbull_client.validate_notification for the authoritative amount/IsSubscriptionPayment, but
    trusts THIS request's own statusCode==0 (confirmed-documented meaning, at three separate points
    in the PDF) for the actual success signal, never a guessed-at field from ValidateNotification's
    own response shape (its real "success" encoding isn't confirmed anywhere in the docs).

    NOT YET LIVE-VERIFIED against a real Takbull-triggered call — recurring_api_configured() is
    still False in production (TAKBULL_API_KEY/TAKBULL_API_SECRET never set, see
    set-takbull-api-key-secret.yaml), itself blocked on Upay's pending KYC approval for this
    account. Real end-to-end confirmation has to wait for that."""
    if not _check_takbull_secret(secret):
        return Response(status_code=404)

    params = dict(request.query_params)
    logger.info("Takbull GET IPN raw query params: %r", params)

    uniq_id = params.get("uniqId")
    order_reference = params.get("order_reference")
    status_code = params.get("statusCode")

    if not uniq_id or not order_reference:
        logger.warning(
            "Takbull GET IPN missing uniqId/order_reference (got %r) — nothing usable to process",
            params,
        )
        return Response(status_code=200)

    if status_code != "0":
        logger.info(
            "Takbull GET IPN for order_reference=%s had statusCode=%r (not '0') — not a success "
            "signal, ignoring",
            order_reference, status_code,
        )
        return Response(status_code=200)

    # 2026-09-25 real bug fix, found via a live code-review pass: validate_notification is a
    # blocking sync call (plain httpx.post, 15s timeout) — calling it directly here would run it
    # ON the single asyncio event loop this whole site uses (uvicorn with no --workers flag,
    # replicas: 1 — see website/Dockerfile / charts/todira/templates/website-deployment.yaml),
    # freezing every other concurrent request (page loads, every other webhook) for up to 15
    # seconds whenever Takbull's own API is slow. Currently dormant — recurring_api_configured()
    # is still False in production, so validate_notification returns None immediately without
    # ever reaching the network call — but fixing it now, before TAKBULL_API_KEY/SECRET ever go
    # live, avoids a real launch-week outage the first time this path actually fires for real.
    validated = await asyncio.to_thread(takbull_client.validate_notification, uniq_id)
    if validated is None:
        logger.warning(
            "Takbull GET IPN for order_reference=%s had statusCode=0 but ValidateNotification "
            "didn't return usable data (see the error logged above) — left pending, no amount to "
            "safely trust",
            order_reference,
        )
        return Response(status_code=200)

    body = {
        "order_reference": order_reference,
        "uniqId": uniq_id,
        "OrderNumber": params.get("transactionInternalNumber"),
        "StatusDescription": "Success",
        "OrderTotalSum": validated.get("amount"),
        "IsSubscriptionPayment": validated.get("isSubscriptionPayment"),
    }
    return await _process_takbull_payload(body)


@app.post("/webhooks/takbull/{secret}")
async def webhooks_takbull_post(request: Request, secret: str):
    """Kept as a defensive fallback alongside the real GET flow above (see that handler's own
    docstring) — in case a future Takbull event genuinely does POST a rich payload directly, or for
    the existing diagnose-takbull-webhook-manual-post.yaml-style manual reconciliation. Same
    always-200-except-bad-secret contract."""
    if not _check_takbull_secret(secret):
        return Response(status_code=404)

    try:
        body = dict(await request.json())
    except Exception:
        body = dict(await request.form())
    logger.info("Takbull POST webhook raw payload: %r", body)
    return await _process_takbull_payload(body)


_TAKBULL_WAITING_WINDOW = dt.timedelta(hours=3)


def _match_takbull_payment(session, body: dict, payment_id: int | None):
    """Which Payment does this Takbull webhook confirm? Returns (payment, is_renewal) or (None, False).

    A webhook that CARRIES our order_reference (a parseable payments.id) is matched only by it: a pending payment
    (first charge), or a paid one that owns a Takbull recurring subscription when the payload says
    IsSubscriptionPayment (a renewal — see the long comment in _process_takbull_payload). Anything else with a
    reference (a replay, a stray id) is NOT guessed at.

    A webhook WITHOUT any usable reference — what the free hosted payment page may send, since order_reference passing
    through that page is documented by Takbull but not yet confirmed end to end — is matched, most reliable first:
    1. the payer's email (CustomerEmail) equals a user's linked Google email -> that user's newest pending Payment;
    2. the charge is a real pass price and exactly ONE pending hosted-page payment was started in the last 3 hours ->
       that one, whatever amount it was stored with (since 2026-10-13 the customer usually picks the pass on Takbull's
       page, so the pending row only holds a placeholder). With several waiting, the single one stored with exactly
       the charged amount (a pass clicked on its own page); otherwise we refuse to guess and the owner is alerted
       instead (the unmatched branch of _process_takbull_payload).
    A transaction id we already recorded is never matched again (a replay cannot credit a newer pending payment).
    The amount is verified again by the caller against OrderTotalSum before anything is granted."""
    if payment_id is not None:
        payment = session.scalar(
            select(Payment).where(
                Payment.id == payment_id, Payment.gateway == "takbull", Payment.status == "pending"
            )
        )
        if payment is not None:
            return payment, False
        original = session.scalar(
            select(Payment).where(
                Payment.id == payment_id,
                Payment.gateway == "takbull",
                Payment.status == "paid",
                Payment.subscription_uniqid.is_not(None),
            )
        )
        if original is not None and bool(body.get("IsSubscriptionPayment")):
            return original, True
        return None, False

    transaction_id = str(body.get("uniqId") or body.get("OrderNumber") or "")
    if transaction_id and session.scalar(
        select(Payment.id).where(Payment.gateway_transaction_id == transaction_id).limit(1)
    ) is not None:
        return None, False

    email = str(body.get("CustomerEmail") or body.get("customerEmail") or "").strip().lower()
    if email:
        user = session.scalar(select(User).where(func.lower(User.google_email) == email).limit(1))
        if user is not None:
            payment = session.scalar(
                select(Payment)
                .where(
                    Payment.user_id == user.id,
                    Payment.gateway == "takbull",
                    Payment.status == "pending",
                    Payment.subscription_uniqid.is_(None),
                )
                .order_by(Payment.id.desc())
                .limit(1)
            )
            if payment is not None:
                return payment, False

    try:
        total = Decimal(str(body.get("OrderTotalSum")))
    except (InvalidOperation, TypeError, ValueError):
        return None, False
    if plan_for_amount(total, test_amount_from_env()) is None:
        return None, False
    waiting = session.scalars(
        select(Payment).where(
            Payment.gateway == "takbull",
            Payment.status == "pending",
            Payment.subscription_uniqid.is_(None),
            Payment.created_at >= dt.datetime.now(dt.timezone.utc) - _TAKBULL_WAITING_WINDOW,
        )
    ).all()
    if len(waiting) == 1:
        return waiting[0], False
    same_amount = [p for p in waiting if p.amount_ils == total]
    return (same_amount[0], False) if len(same_amount) == 1 else (None, False)


def _alert_owner_unmatched_takbull_payment(body: dict) -> None:
    """A real-looking Takbull charge arrived that we could not tie to exactly one waiting user: tell the owner (private
    Telegram) so he can grant access by hand from /admin/users — never silently drop a paid customer."""
    try:
        amount = body.get("OrderTotalSum")
        payer_email = str(body.get("CustomerEmail") or "-")
        _notify_owner_sync(
            "Takbull",
            payer_email,
            f"תשלום של ₪{amount} התקבל בתקבול ולא הותאם למשתמש אחד (אין התאמה לפי הפניה, אימייל או 'היחיד שממתין'). "
            "יש לתת גישה ידנית דרך /admin/users.",
            None,
        )
    except Exception:
        logger.exception("Could not alert the owner about an unmatched Takbull payment")


def _alert_owner_pending_takbull_payment(body: dict, reason: str) -> None:
    """A successful Takbull charge matched a waiting payment but was NOT credited (amount is no pass, or no amount at
    all): tell the owner so a paying customer is never left without access unnoticed. Aggregate facts only."""
    try:
        amount = body.get("OrderTotalSum")
        _notify_owner_sync(
            "Takbull",
            str(body.get("CustomerEmail") or "-"),
            f"תשלום של ₪{amount} התקבל בתקבול אבל לא זוכה אוטומטית ({reason}). אם זה לקוח אמיתי - לתת גישה ידנית דרך /admin/users.",
            None,
        )
    except Exception:
        logger.exception("Could not alert the owner about a pending Takbull payment")


async def _process_takbull_payload(body: dict) -> Response:
    """Shared by both the real GET IPN flow and the defensive POST fallback above — everything
    past secret-checking and payload-shape-normalization was already correct and tested (16 tests
    in test_website_takbull_payments.py), so this is an extraction, not a rewrite of the actual
    matching/crediting logic."""
    order_reference = body.get("order_reference")
    try:
        payment_id = int(order_reference)
    except (TypeError, ValueError):
        payment_id = None

    with get_session() as session:
        # Renewals (month 2+ of a Takbull RECURRING subscription — the paid-package flow, dormant until API keys
        # exist): per Takbull's docs IsSubscriptionPayment=true marks such an event and order_reference still points
        # at the ORIGINAL (now already "paid") Payment row, since that row IS the subscription from Takbull's point of
        # view. Genuinely NOT live-verified yet — see takbull_client.py's module docstring.
        payment, is_renewal = _match_takbull_payment(session, body, payment_id)
        if payment is None and _already_credited_takbull_charge(session, body, payment_id):
            # 2026-10-16: the owner's Takbull account has the same webhook set up twice, so every charge arrives twice.
            # The first credits it; the second used to fall through to "did not match" and alert the owner about a
            # payment that was in fact credited. A repeat of a credited charge is now quietly acknowledged.
            logger.info("Takbull webhook repeats a charge already credited (order_reference=%r) - ignored", order_reference)
            return Response(status_code=200)
        if payment is None:
            logger.warning(
                "Takbull webhook (order_reference=%r) did not match any pending Takbull payment, user email or "
                "renewal-eligible subscription — ignoring; see the raw payload logged above for manual reconciliation",
                order_reference,
            )
            if _looks_like_a_successful_takbull_payload(body):
                await asyncio.to_thread(_alert_owner_unmatched_takbull_payment, body)
            return Response(status_code=200)

        if not _looks_like_a_successful_takbull_payload(body):
            logger.warning(
                "Takbull webhook for payment_id=%s had no recognizable success signal — left "
                "pending, see the raw payload logged above",
                payment.id,
            )
            # 2026-10-16 (owner asked about Bit): only card payments were tested live. If a Bit charge ever reports
            # success in a shape this does not recognize, the customer paid and got nothing - the owner hears about it.
            status = body.get("StatusDescription") or body.get("Status") or body.get("StatusCode")
            await asyncio.to_thread(
                _alert_owner_pending_takbull_payment, body, f"לא זוהה בהודעה שהתשלום הצליח, סטטוס: {status!r}"
            )
            return Response(status_code=200)

        # The customer picks their item themselves on Takbull's one shared multi-plan page (see
        # takbull_client.py) — nothing stops them from adding a different plan than the one they
        # clicked on our own /upgrade first. OrderTotalSum is Takbull's own record of what was
        # actually charged, so it's trusted over our own pre-recorded payment.amount_ils: if they
        # don't match, grant nothing rather than risk crediting the wrong plan — left pending for
        # manual reconciliation via /admin/users, same conservative stance as an unrecognized
        # payload above.
        order_total = body.get("OrderTotalSum")
        if not is_renewal and not payment.subscription_uniqid and order_total is not None:
            # One-time hosted-page payment (2026-10-06 passes): the AMOUNT Takbull actually charged decides the pass -
            # 19.90 = 7 days, 29.90 = 14, 49.90 = 30 - even if the customer picked a different item than the plan
            # they clicked on our site. An amount that is no pass (a test payment, a stale price) falls through to
            # the mismatch handling below and is left pending.
            try:
                paid_plan = plan_for_amount(Decimal(str(order_total)), test_amount_from_env())
            except (InvalidOperation, TypeError, ValueError):
                paid_plan = None
            if paid_plan is not None:
                payment.plan = paid_plan
                payment.amount_ils = PLAN_PRICES_ILS[paid_plan]
        try:
            # Decimal, not int (2026-09-21) — the recurring plan's ₪49.90 isn't a whole number, so
            # OrderTotalSum arrives as e.g. "49.90"; int("49.90") raises ValueError, which used to
            # get silently treated as "leave pending" here, meaning every real recurring charge
            # would have gone uncredited forever under the old comparison.
            order_total_matches = order_total is not None and Decimal(str(order_total)) == payment.amount_ils
        except (InvalidOperation, TypeError, ValueError):
            order_total_matches = False
        if order_total is not None and not order_total_matches:
            logger.warning(
                "Takbull webhook for payment_id=%s reported OrderTotalSum=%r but the payment was "
                "for ₪%s — leaving pending rather than guessing which plan to grant",
                payment.id, order_total, payment.amount_ils,
            )
            await asyncio.to_thread(_alert_owner_pending_takbull_payment, body, "הסכום אינו תואם לאף חבילה")
            return Response(status_code=200)
        if order_total is None:
            # Takbull's own documented order-success payload always includes OrderTotalSum (see
            # this function's own docstring) — a payload missing it entirely is itself suspicious
            # rather than something to silently trust our own pre-recorded amount for, same
            # conservative stance as a mismatched amount above.
            logger.warning(
                "Takbull webhook for payment_id=%s had no OrderTotalSum at all — leaving pending "
                "rather than trusting our own pre-recorded amount unconditionally",
                payment.id,
            )
            await asyncio.to_thread(_alert_owner_pending_takbull_payment, body, "לא נשלח סכום")
            return Response(status_code=200)

        user = session.get(User, payment.user_id)
        if user is None:
            logger.error("Takbull webhook for payment_id=%s references a deleted user", payment.id)
            return Response(status_code=200)

        transaction_id = str(body.get("uniqId") or body.get("OrderNumber") or payment.id)

        if is_renewal:
            # A NEW Payment row per renewal cycle (not overwriting the original) — keeps the
            # per-charge audit trail the class docstring promises, and gateway_transaction_id's
            # own unique constraint is what stops a replayed webhook for the SAME cycle from
            # double-crediting (a real new cycle always carries a transaction id we haven't seen).
            existing = session.scalar(
                select(Payment).where(Payment.gateway_transaction_id == transaction_id)
            )
            if existing is not None:
                logger.info(
                    "Takbull renewal webhook transaction_id=%s already processed — ignoring replay",
                    transaction_id,
                )
                return Response(status_code=200)
            if user.cancel_at_period_end:
                logger.warning(
                    "Takbull renewal charge for user_id=%s arrived after cancel_at_period_end was "
                    "set — Takbull's own CancelSubscription call may not have taken effect; "
                    "granting the paid period regardless since a real charge happened",
                    user.id,
                )
            renewal_payment = Payment(
                user_id=user.id,
                plan=payment.plan,
                amount_ils=payment.amount_ils,
                status="paid",
                gateway="takbull",
                gateway_transaction_id=transaction_id,
                subscription_uniqid=payment.subscription_uniqid,
                paid_at=dt.datetime.now(dt.timezone.utc),
            )
            session.add(renewal_payment)
            extend_paid_until(user, payment.plan)
            session.commit()
            return Response(status_code=200)

        payment.status = "paid"
        payment.paid_at = dt.datetime.now(dt.timezone.utc)
        payment.gateway_transaction_id = transaction_id
        if payment.subscription_uniqid:
            user.takbull_subscription_uniqid = payment.subscription_uniqid
            user.cancel_at_period_end = False
        extend_paid_until(user, payment.plan)
        try:
            session.commit()
        except IntegrityError:
            # The same charge delivered twice at the same moment: the other request already credited it (the unique
            # gateway_transaction_id stopped this one) - nothing is granted twice.
            session.rollback()
            logger.info("Takbull webhook for payment_id=%s lost a race with its own repeat - already credited", payment.id)

    return Response(status_code=200)


def _already_credited_takbull_charge(session, body: dict, payment_id: int | None) -> bool:
    """True when this webhook is a repeat of a charge we already credited: its transaction id is on a paid payment, or
    its order reference names a payment that is already paid by that very charge."""
    transaction_id = str(body.get("uniqId") or body.get("OrderNumber") or "")
    if transaction_id and session.scalar(
        select(Payment.id).where(Payment.gateway_transaction_id == transaction_id, Payment.status == "paid").limit(1)
    ) is not None:
        return True
    if payment_id is not None and not transaction_id:
        paid = session.scalar(select(Payment).where(Payment.id == payment_id, Payment.status == "paid"))
        return paid is not None and paid.gateway_transaction_id == str(payment_id)
    return False


# 2026-10-13 (owner asked what the "ממתין" rows on /account were): every press of the checkout button records a pending
# Payment before the visitor reaches Takbull's page, so a checkout that was opened and never paid stayed in the history as
# "pending" forever. The history now shows a pending row only while that checkout can still be paid.
_PENDING_PAYMENT_SHOWN_FOR = dt.timedelta(hours=1)
_PAYMENT_HISTORY_SIZE = 10


def _payment_history(payments) -> list:
    cutoff = dt.datetime.now(dt.timezone.utc) - _PENDING_PAYMENT_SHOWN_FOR
    shown = []
    for payment in payments:
        created_at = payment.created_at
        if created_at is not None and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=dt.timezone.utc)
        if payment.status == "pending" and (created_at is None or created_at < cutoff):
            continue  # an abandoned checkout, not a payment
        shown.append(payment)
    return shown[:_PAYMENT_HISTORY_SIZE]


@app.get("/account")
def account(request: Request, uid: int | None = None):
    """Cross-channel linking (todira_common/channel_link.py) — same uid/session resolution as
    /apartments, /liked, /upgrade, /filter. Shows which channels are already linked to this user,
    and — when Telegram isn't — a fresh 15-minute link code plus a ready-to-use Telegram deep link
    to send it from there, matching the reference product's own confirmed UX.

    2026-09-06: also surfaces subscription status, a notifications on/off toggle, and payment
    history — all backed by data that already existed (trial_ends_at/paid_until/
    notifications_enabled on User, the Payment table) but was never rendered anywhere on the
    website before tonight, prompted by the owner's own side-by-side look at the reference
    product's fuller account page."""
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "account"})

        has_telegram = user.telegram_user_id is not None
        has_google = user.google_sub is not None

        code = None
        if not has_telegram:
            # 2026-09-27: real bug, live-confirmed — this used to call generate_link_code()
            # unconditionally on every single page load. generate_link_code REPLACES whatever
            # code was already stored (see its own docstring), so simply reloading /account after
            # sending a code — a completely natural thing to do while checking whether the link
            # worked — silently orphaned the code already sent, with no error surfaced anywhere:
            # resolve_link_code just treats an unmatched code as "not a link code" and falls
            # through. Now reuses the existing code as long as it's still live (unexpired);
            # generate_link_code only runs for a genuinely first-time or truly-expired code.
            still_valid = (
                user.channel_link_code is not None
                and user.channel_link_code_expires_at is not None
                and dt.datetime.now(dt.timezone.utc) < user.channel_link_code_expires_at
            )
            code = user.channel_link_code if still_valid else generate_link_code(session, user)
        redirect_uid = user.telegram_user_id

        access = _effective_access(request, user)
        notifications_enabled = user.notifications_enabled
        payments = _payment_history(
            session.scalars(
                select(Payment)
                .where(Payment.user_id == user.id)
                .order_by(Payment.created_at.desc())
                .limit(30)
            )
        )
        cancel_pass = _cancel_pass_config(session, user)
    cancelled_refund_ils = request.session.pop("cancelled_refund_ils", None)

    # 2026-09-25: eighth page moved into a React island (website/landing-react/account.html) —
    # same pattern as about()/accessibility()/.../login() above, but unlike those, the POST
    # actions below (cancel/resume-subscription, notifications) are
    # deliberately UNCHANGED — still plain form-encoded POSTs redirecting back to /account, not
    # fetch. A full page reload after a subscription/notification change is completely fine UX
    # (that's exactly what already happens), so there's no reason to widen this into the
    # fetch-based rewrite /contact needed for its own real-time-feeling submit; Account.jsx's own
    # <form>s just reskin the presentation around the exact same native POSTs, with the same
    # hidden uid field. Dates are pre-formatted server-side (dd/mm/yyyy, matching the
    # template's own strftime calls exactly) rather than passed as raw datetimes for React to
    # reformat — one less thing that could drift from the original rendering. payment.plan/.status
    # are passed as their raw slugs (not translated here) — Account.jsx does the same
    # slug->translated-label lookup the original template's own inline dict did, via its own t(),
    # matching how every other converted page translates client-side rather than server-side.
    account_assets = _landing_react_assets("account.html")
    return _render(
        request,
        "account.html",
        {
            "landing_js_url": account_assets.get("js", ""),
            "landing_css_urls": account_assets.get("css", []),
            "account_config": {
                "uid": redirect_uid,
                # 2026-09-26 real owner report: logged in with Google, then had no way to log out
                # short of an incognito window — /auth/logout already existed (used by base.html's
                # own hamburger-menu link) but was never surfaced anywhere on /account itself.
                # Gated on a REAL signed session (not just a ?uid= deep link, which has no
                # session to end) — same check apartments()'s own via_session already uses.
                "isLoggedInViaSession": request.session.get("user_id") == user.id,
                "hasTelegram": has_telegram,
                "hasGoogle": has_google,
                # 2026-09-26 real owner request: show WHICH identity each connected channel is,
                # not just a bare "connected" checkmark — a user with several channels linked
                # couldn't tell them apart otherwise. Purely informational display text on the
                # user's OWN account page (they already know their own username/email).
                "telegramUsername": user.telegram_username,
                "googleEmail": user.google_email,
                "code": code,
                "telegramLink": f"https://t.me/AmirDirotBot?start={code}" if code else None,
                # named displayIsOwner, not isOwner: _render() always overwrites an "is_owner" key
                # with the real session-based nav-admin-link check, so a route-supplied one would
                # be silently dropped if it kept that name.
                "displayIsOwner": _display_is_owner(request, user.telegram_user_id),
                "hasAccess": access,
                "trialEndsAt": _israel_date(user.trial_ends_at) or None,
                "paidUntil": _israel_date(user.paid_until) or None,
                # 2026-10-13 (owner): how many days of access are left, counting today (None when none is running).
                "daysLeft": _days_left(max((d for d in (user.paid_until, user.trial_ends_at) if d is not None), default=None)),
                "notificationsEnabled": notifications_enabled,
                "payments": [
                    {
                        "plan": payment.plan,
                        # 2026-09-26 real crash found live: Payment.amount_ils is a real Decimal
                        # (Numeric(10,2) column) — Python's json.dumps (which `| tojson` uses
                        # internally) has no default encoding for Decimal and raises
                        # `TypeError: Object of type Decimal is not JSON serializable`, a genuine
                        # 500 for any user with real payment history (the account_config | tojson
                        # dict is built once, so one bad field crashes the whole page — Safari
                        # then offers FastAPI's default plain-text 500 body as a download instead
                        # of rendering it, same "apartments.txt" symptom as the earlier incident).
                        # str(), not float() — 49.90 must stay "49.90", not become 49.9.
                        "amountIls": str(payment.amount_ils),
                        "date": _israel_date(payment.paid_at or payment.created_at),
                        "status": payment.status,
                    }
                    for payment in payments
                ],
                "hasActiveSubscription": user.takbull_subscription_uniqid is not None,
                "cancelAtPeriodEnd": user.cancel_at_period_end,
                # 2026-10-13 (owner request): the small "cancel purchase" link for a one-time pass still inside the
                # 14-day window (terms section 10), with the refund already worked out; None hides it.
                "cancelPass": cancel_pass,
                # Set for one page view right after a cancellation (see account_cancel_pass).
                "cancelledRefundIls": cancelled_refund_ils,
            },
        },
        known_lang=user.language,
    )


def _days_left(ends_at: dt.datetime | None) -> int | None:
    """Days of access left for /account's "N days left" line, counting a started day as a whole one; None when nothing
    is running."""
    if ends_at is None:
        return None
    remaining = ends_at - dt.datetime.now(dt.timezone.utc)
    if remaining.total_seconds() <= 0:
        return None
    return remaining.days + (1 if remaining.seconds or remaining.microseconds else 0)


_PASS_NAMES_HE = {"pass_7": "שבוע", "pass_14": "שבועיים", "pass_30": "חודש", TEST_PASS_PLAN: "בדיקה"}


def _cancellable_pass_payment(session, user: User, now: dt.datetime) -> Payment | None:
    """The one-time pass this user can still cancel under terms section 10: their newest paid Takbull pass bought in the
    last 14 days, while their paid access is still running. None otherwise (a recurring subscription has its own
    cancel-auto-renewal flow above)."""
    if user.paid_until is None or user.paid_until <= now:
        return None
    return session.scalar(
        select(Payment)
        .where(
            Payment.user_id == user.id,
            Payment.gateway == "takbull",
            Payment.status == "paid",
            Payment.subscription_uniqid.is_(None),
            Payment.plan.in_((*PASS_PLANS, TEST_PASS_PLAN)),
            Payment.paid_at.is_not(None),
            Payment.paid_at >= now - CANCELLATION_WINDOW,
        )
        .order_by(Payment.paid_at.desc())
        .limit(1)
    )


def _cancel_pass_config(session, user: User) -> dict | None:
    """What /account shows behind its small "cancel purchase" link (Account.jsx): the pass and what cancelling it now
    refunds. Amounts are strings so 49.90 stays "49.90" in JSON."""
    now = dt.datetime.now(dt.timezone.utc)
    payment = _cancellable_pass_payment(session, user, now)
    if payment is None:
        return None
    quote = cancellation_quote(payment.amount_ils, payment.paid_at, now)
    return {
        "plan": payment.plan,
        "paidIls": str(payment.amount_ils),
        "elapsedDays": quote["elapsed_days"],
        "coveringIls": str(quote["covering_ils"]),
        "feeIls": str(quote["fee_ils"]),
        "refundIls": str(quote["refund_ils"]),
    }


@app.post("/account/cancel-pass")
def account_cancel_pass(
    request: Request,
    uid: int | None = Form(None),
    confirm: str | None = Form(None),
):
    """Cancels a one-time pass under terms section 10 (2026-10-13 owner request). Recomputes everything server-side
    (nothing from the page is trusted): ends the cancelled pass's access now, marks the payment "cancelled", and tells
    the owner on Telegram exactly how much to refund by hand in Takbull and for which transaction. Only the days this
    pass added are taken back, so an earlier pass's or the trial's remaining time is not lost."""
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "account"})
        now = dt.datetime.now(dt.timezone.utc)
        payment = _cancellable_pass_payment(session, user, now) if confirm == "yes" else None
        if payment is None:
            return RedirectResponse(_identity_redirect_url("/account", uid), status_code=303)
        quote = cancellation_quote(payment.amount_ils, payment.paid_at, now)
        remaining = user.paid_until - PLAN_DURATIONS[payment.plan]
        user.paid_until = remaining if remaining > now else now
        payment.status = "cancelled"
        session.commit()
        logger.info(
            "Pass cancelled: payment_id=%s plan=%s paid=%s elapsed_days=%s refund=%s",
            payment.id, payment.plan, payment.amount_ils, quote["elapsed_days"], quote["refund_ils"],
        )
        request.session["cancelled_refund_ils"] = str(quote["refund_ils"])
        covering = _PASS_NAMES_HE.get(quote["covering_plan"], "כל הסכום")
        lines = [
            "🔴 ביטול רכישה",
            f"חבילה: {_PASS_NAMES_HE.get(payment.plan, payment.plan)} (₪{payment.amount_ils}), "
            f"נרכשה ב-{_israel_date(payment.paid_at)}",
            f"עברו {quote['elapsed_days']} ימים: מקוזז מחיר {covering} ₪{quote['covering_ils']} "
            f"ודמי ביטול ₪{quote['fee_ils']}",
            f"להחזיר בתקבול: ₪{quote['refund_ils']}" if quote["refund_ils"] > 0 else "לא מגיע החזר, רק לידיעה.",
            f"מספר עסקה: {payment.gateway_transaction_id or '-'}",
        ]
        name, email, telegram_user_id = user.first_name or "-", user.google_email or "-", user.telegram_user_id

    _notify_owner_sync(name, email, "\n".join(lines), telegram_user_id)
    return RedirectResponse(_identity_redirect_url("/account", uid), status_code=303)


@app.post("/account/cancel-subscription")
def account_cancel_subscription(
    request: Request, uid: int | None = Form(None)
):
    """Stops future auto-renewal — the user KEEPS access until paid_until (the period already
    charged for isn't clawed back), same as any standard SaaS cancellation. Deliberately does NOT
    call Takbull's CancelSubscription API here — Takbull has no documented "un-cancel" API
    counterpart, so calling it immediately would make /account/resume-subscription below unable to
    actually resume anything. Instead this only flips the local flag; the real Takbull-side cancel
    happens a few days BEFORE the period ends (website/subscription_housekeeping.py's daily job;
    before 2026-10-02 it waited until AFTER, which let one more renewal charge through), so a resume
    clicked before then needs no API call at all and the recurring order keeps working."""
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "account"})
        user.cancel_at_period_end = True
        session.commit()

    return RedirectResponse(_identity_redirect_url("/account", uid), status_code=303)


@app.post("/account/resume-subscription")
def account_resume_subscription(
    request: Request, uid: int | None = Form(None)
):
    """Undoes a cancel-subscription click made before the current period actually ran out. Pure
    local-state flip, no Takbull call needed — see account_cancel_subscription's own comment on
    why the real Takbull-side cancel is deliberately deferred until the period actually ends, so
    there's nothing to "un-cancel" on Takbull's side as long as this is clicked before then."""
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "account"})
        if user.takbull_subscription_uniqid is None:
            # The recurring order was already cancelled on Takbull's side (see
            # subscription_housekeeping.py: it cancels a few days BEFORE paid_until so a renewal can
            # never be charged after the customer cancelled). Takbull has no un-cancel, so there is
            # nothing to resume - the customer keeps access until paid_until and can subscribe again.
            return RedirectResponse(_identity_redirect_url("/account", uid), status_code=303)
        user.cancel_at_period_end = False
        session.commit()

    return RedirectResponse(_identity_redirect_url("/account", uid), status_code=303)


@app.post("/account/notifications")
def account_notifications_toggle(
    request: Request, uid: int | None = Form(None)
):
    """Flips User.notifications_enabled — the field already existed (used by scraper/notifier.py
    to skip a paused user) but had no UI anywhere to change it before tonight. A plain form POST,
    not a JS toggle-switch, matching this site's own mostly-server-rendered pattern elsewhere
    (/preview/toggle, /filter)."""
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "account"})
        user.notifications_enabled = not user.notifications_enabled
        session.commit()

    return RedirectResponse(_identity_redirect_url("/account", uid), status_code=303)


def _identity_redirect_url(path: str, uid: int | None) -> str:
    """A redirect target back to `path` carrying the low-trust uid that got the visitor there.
    Originally /filter-specific; generalized 2026-09-06 for /account's own notifications-toggle
    redirect rather than duplicating the same logic a second time."""
    if uid:
        return f"{path}?uid={uid}"
    return path


def _filter_redirect_url(uid: int | None) -> str:
    return _identity_redirect_url("/filter", uid)


@app.get("/filter")
def filter_view(
    request: Request, uid: int | None = None, welcome: bool = False,
    error: str | None = None,
):
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "filter"})
        # See i18n.get_lang's own docstring: an identified visitor's own on-file language
        # preference wins over guessing from Accept-Language (2026-09-29 real bug — Telegram's
        # in-app browser sends the phone's system language, not the bot's own chosen language).
        lang = get_lang(request, user.language)
        if user.filter is None:
            return _render(
                request, "no_filter.html", {"uid": user.telegram_user_id}, known_lang=user.language
            )
        filter_row = user.filter
        return _render(
            request,
            "filter.html",
            {
                "f": filter_row,
                "welcome": welcome,
                # 2026-09-26 dorin.app-style onboarding: set only by filter_update's own redirect,
                # after a welcome-flow save was rejected for having zero cities selected — see
                # filter.html's own cities-error-banner block and filter_update's docstring.
                "cities_error": error == "cities",
                "uid": user.telegram_user_id,
                "user": user,
                # sorted for display only — CITIES itself stays in its original order since other
                # code (matching, the bot's own city picker) reads it as-is.
                "cities_list": sorted(CITIES),
                **_LOCALITY_PICKER_CONTEXT,
                "property_type_labels": PROPERTY_TYPE_LABELS.get(lang, PROPERTY_TYPE_LABELS[DEFAULT_LANG]),
                "safe_room_labels": SAFE_ROOM_LABELS.get(lang, SAFE_ROOM_LABELS[DEFAULT_LANG]),
                "furniture_labels": FURNITURE_LABELS.get(lang, FURNITURE_LABELS[DEFAULT_LANG]),
            },
            known_lang=user.language,
        )


def _parse_int_or_none(raw: str) -> int | None:
    """2026-09-24 real bug fix: filter_update's numeric fields are deliberately plain `str = Form`
    (not `int = Form`) so an empty string means "no limit" instead of FastAPI 422ing the whole
    form — but that also means a non-numeric value (a stray character, a pasted "5,000" with a
    comma, a tampered/non-browser request) skipped FastAPI's own type coercion entirely and hit a
    bare `int(...)` below, which raised an uncaught ValueError → an unhandled 500 on every save,
    not just that one field. Trims the same way the call sites already did, but treats anything
    that still doesn't parse as "no limit" (None) rather than crashing — the same fallback an empty
    field already got, not silently rejecting the rest of the form the user just filled in."""
    raw = raw.strip().replace(",", "").replace("₪", "").strip()  # 2026-10-15: "5,000" / "₪5000" mean 5000, not "no limit"
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if abs(value) < 2**31 else None  # the columns are 32-bit; a bigger number was a 500


def _parse_float_or_none(raw: str) -> float | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    # "nan" / "inf" parse as floats but are no room count (and a 500 when the database refuses them)
    return value if math.isfinite(value) and 0 <= value < 100 else None


def _ordered(low, high):
    """A minimum above the maximum (typed the wrong way round) matches nothing at all - swap the two instead."""
    if low is not None and high is not None and low > high:
        return high, low
    return low, high


@app.post("/filter")
def filter_update(
    request: Request,
    uid: int | None = Form(None),
    cities: list[str] = Form([]),
    all_cities: str | None = Form(None),
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
    welcome: str | None = Form(None),
):
    """2026-09-26 dorin.app-style onboarding addition (real owner request, 33-page PDF walkthrough)
    — `welcome` is only ever present on a submit from the first-time welcome flow (filter.html's
    own hidden field, only rendered when `welcome` is true there). It does two things a normal
    filter save never does: (1) blocks the save entirely — nothing written, not even the other
    fields — when zero cities AND all_cities are both unset, matching dorin's own "חובה לבחור עיר
    אחת" hard block; outside onboarding, an empty cities list still means "all cities" exactly as
    before, completely unaffected by this. (2) chains into step 2 (/onboarding/notifications)
    instead of /apartments on a successful save, continuing the flow rather than dropping the new
    user straight into the results.

    2026-09-27 real bug fix (live owner report, confirmed via diagnose-city-filter-coverage-gap.yaml
    — 3,727 of 12,893 active listings, ~29%, have a real city outside CITIES' curated ~42-city
    whitelist): `f.cities = [c for c in cities if c in CITIES]` used to run unconditionally, so
    checking every individual box in the grid produced an exact-match filter against only those 42
    strings — NOT the same as "no city filter" (todira_common.matching skips the city check
    entirely only when filter.cities is empty). The only way to reach that real unfiltered state
    was leaving the whole grid unchecked, which the welcome block above makes impossible during
    onboarding — silently hiding ~29% of real inventory from every new user, forever, with no way
    back short of an admin/DB edit. all_cities is a first-class way to reach cities=[] for real:
    when set, it always wins over whatever was also submitted in `cities` (checked or not — the
    front end keeps them mutually exclusive, but the server doesn't trust that alone)."""
    with get_session() as session:
        # session-first (like every other page), uid as the low-trust fallback for a
        # bot-deep-link visitor with no real login yet — 2026-09-05 fix: this used to require uid
        # unconditionally (Form(...)), which a session-only Google-standalone account (no
        # telegram_user_id at all) could never satisfy, breaking their own filter form with a 422
        # on every save.
        user = _resolve_user(request, session, uid)
        if user is None or user.filter is None:
            return RedirectResponse(_filter_redirect_url(uid), status_code=303)

        if welcome is not None and all_cities is None and not any(c in LOCALITY_SET for c in cities):
            error_url = _identity_redirect_url("/filter", uid)
            error_url += ("&" if "?" in error_url else "?") + "welcome=1&error=cities"
            return RedirectResponse(error_url, status_code=303)

        f: Filter = user.filter
        f.cities = [] if all_cities is not None else [c for c in cities if c in LOCALITY_SET]
        f.price_min, f.price_max = _ordered(_parse_int_or_none(price_min), _parse_int_or_none(price_max))
        f.rooms_min, f.rooms_max = _ordered(_parse_float_or_none(rooms_min), _parse_float_or_none(rooms_max))
        f.property_types = [p for p in property_types if p in PROPERTY_TYPE_LABELS[DEFAULT_LANG]]
        f.floor_min, f.floor_max = _ordered(_parse_int_or_none(floor_min), _parse_int_or_none(floor_max))
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
        f.min_area_sqm = _parse_int_or_none(min_area_sqm)
        f.keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        f.flexible_match = flexible_match is not None
        session.commit()
        _mark_matches_seen_in_background(user.id)

    # 2026-09-08 UX fix (owner's own report): a successful save used to redirect back to /filter
    # itself, leaving the visitor staring at the same form with no visible feedback that anything
    # happened. Sending them to /apartments instead shows the results of what they just changed —
    # exactly the payoff of editing a filter. The error-recovery branch above (no resolvable user/
    # filter) still goes back to /filter, since there's nothing on /apartments to show them either.
    # 2026-09-26: a welcome-flow save continues the onboarding flow (step 2) instead — see this
    # function's own docstring.
    next_path = "/onboarding/notifications" if welcome is not None else "/apartments"
    return RedirectResponse(_identity_redirect_url(next_path, uid), status_code=303)


@app.get("/onboarding/notifications")
def onboarding_notifications(request: Request, uid: int | None = None):
    """Step 2 of 3 in the dorin.app-style first-time onboarding flow (real owner request, 33-page
    PDF walkthrough) — reached only via filter_update's own welcome-flow redirect, right after a
    new user saves their first filter. Optional, matching dorin exactly: a real CTA to connect the
    Telegram bot for instant notifications, and an equally real skip link that continues straight to
    step 3 without connecting anything. Reuses /account's own generate_link_code mechanism (same
    15-minute code, same deep link shape) rather than inventing a second connect flow."""
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "filter"})
        # Same fix as /account's own identical bug (see that route's own comment): reuse a still-
        # live code across reloads instead of generate_link_code's default replace-on-every-call
        # behavior, which silently orphaned an already-sent code on a simple page revisit.
        code = None
        if user.telegram_user_id is None:
            still_valid = (
                user.channel_link_code is not None
                and user.channel_link_code_expires_at is not None
                and dt.datetime.now(dt.timezone.utc) < user.channel_link_code_expires_at
            )
            code = user.channel_link_code if still_valid else generate_link_code(session, user)
        session.commit()
        return _render(
            request,
            "onboarding_notifications.html",
            {
                "uid": user.telegram_user_id,
                "already_connected": user.telegram_user_id is not None,
                "telegram_link": f"https://t.me/AmirDirotBot?start={code}" if code else None,
            },
            known_lang=user.language,
        )


@app.get("/onboarding/trial")
def onboarding_trial(request: Request, uid: int | None = None):
    """Step 3 of 3 — the free-trial-activated confirmation screen. No action needed from the user
    and nothing to activate here: every account already gets trial_ends_at = now() + 10 days
    automatically at creation (models.py's own server_default), matching dorin's own "שבוע פרימיום
    במתנה" auto-activation (dorin: 7 days; this project: 3, same mechanism, already live well
    before this onboarding flow existed) — this screen is purely the celebratory confirmation dorin
    itself shows right after its own step 2, using the account's real trial_ends_at date."""
    with get_session() as session:
        user = _resolve_user(request, session, uid)
        if user is None:
            return _render(request, "need_uid.html", {"target": "filter"})
        return _render(
            request,
            "onboarding_trial.html",
            {
                "uid": user.telegram_user_id,
                "trial_ends_at": user.trial_ends_at,
            },
            known_lang=user.language,
        )
