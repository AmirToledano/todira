"""ToDira public website (Phase 2) — FastAPI, server-rendered Jinja2 templates, reuses
common/dorin_common (same models/matching/db as the bot and scraper).

AUTH IS A TEMPORARY SHIM: pages take the user's Telegram numeric ID as a plain `?uid=` query
param — there is no real login yet. This is deliberately NOT secure (anyone who knows/guesses a
uid can view that user's filter/liked listings) and must be replaced before any real launch with
something like Dorin's signed/encrypted deep-link token (see PROJECT_STATE.md). Good enough for a
first browser-reachable milestone, not for production.
"""
from __future__ import annotations

from pathlib import Path

from dorin_common.db import get_session
from dorin_common.matching import evaluate
from dorin_common.models import Filter, Listing, User, UserListingAction
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

BASE_DIR = Path(__file__).parent

app = FastAPI(title="ToDira")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _get_user_by_uid(session, uid: int) -> User | None:
    return session.scalar(select(User).where(User.telegram_user_id == uid))


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {})


@app.get("/apartments")
def apartments(request: Request, uid: int | None = None):
    if uid is None:
        return templates.TemplateResponse(request, "need_uid.html", {"target": "apartments"})

    with get_session() as session:
        user = _get_user_by_uid(session, uid)
        if user is None or user.filter is None:
            return templates.TemplateResponse(
                request, "no_filter.html", {"uid": uid}
            )

        listings = session.scalars(
            select(Listing)
            .where(Listing.is_delisted.is_(False))
            .order_by(Listing.scraped_at.desc())
            .limit(200)
        ).all()
        matches = [listing for listing in listings if evaluate(user.filter, listing).matched]

    return templates.TemplateResponse(
        request,
        "apartments.html",
        {"listings": matches, "uid": uid, "user": user},
    )


@app.get("/liked")
def liked(request: Request, uid: int | None = None):
    if uid is None:
        return templates.TemplateResponse(request, "need_uid.html", {"target": "liked"})

    with get_session() as session:
        user = _get_user_by_uid(session, uid)
        if user is None:
            return templates.TemplateResponse(request, "no_filter.html", {"uid": uid})

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

    return templates.TemplateResponse(
        request, "liked.html", {"listings": listings, "uid": uid, "user": user}
    )


@app.get("/filter")
def filter_view(request: Request, uid: int | None = None):
    if uid is None:
        return templates.TemplateResponse(request, "need_uid.html", {"target": "filter"})

    with get_session() as session:
        user = _get_user_by_uid(session, uid)
        if user is None or user.filter is None:
            return templates.TemplateResponse(request, "no_filter.html", {"uid": uid})
        filter_row = user.filter
        return templates.TemplateResponse(
            request, "filter.html", {"f": filter_row, "uid": uid, "user": user}
        )


@app.post("/filter")
def filter_update(
    uid: int = Form(...),
    cities: str = Form(""),
    price_min: str = Form(""),
    price_max: str = Form(""),
    rooms_min: str = Form(""),
    rooms_max: str = Form(""),
):
    with get_session() as session:
        user = _get_user_by_uid(session, uid)
        if user is None or user.filter is None:
            return RedirectResponse(f"/filter?uid={uid}", status_code=303)

        f: Filter = user.filter
        f.cities = [c.strip() for c in cities.split(",") if c.strip()]
        f.price_min = int(price_min) if price_min.strip() else None
        f.price_max = int(price_max) if price_max.strip() else None
        f.rooms_min = float(rooms_min) if rooms_min.strip() else None
        f.rooms_max = float(rooms_max) if rooms_max.strip() else None
        session.commit()

    return RedirectResponse(f"/filter?uid={uid}", status_code=303)
