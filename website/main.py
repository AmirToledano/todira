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
from starlette.exceptions import HTTPException as StarletteHTTPException

BASE_DIR = Path(__file__).parent

app = FastAPI(title="טודירה")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# /filter form labels — kept here (not in enums.py) since these are Hebrew UI copy, not part of
# the shared schema the bot/scraper also depend on.
PROPERTY_TYPE_LABELS = {
    "apartment": "דירה",
    "garden_apartment": "דירת גן",
    "penthouse": "פנטהאוז",
    "studio": "סטודיו",
    "housing_unit": "יחידת דיור",
    "private_house": "בית פרטי",
    "shared_room": "חדר בדירת שותפים",
}
SAFE_ROOM_LABELS = {
    "any": "לא משנה",
    "safe_room_only": "רק ממ״ד",
    "safe_room_or_shelter": "ממ״ד או מקלט בבניין",
}
FURNITURE_LABELS = {
    "any": "לא משנה",
    "furnished": "מרוהטת",
    "unfurnished": "לא מרוהטת",
}


@app.exception_handler(404)
async def not_found(request: Request, exc: StarletteHTTPException):
    return templates.TemplateResponse(request, "404.html", {}, status_code=404)


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
            request,
            "filter.html",
            {
                "f": filter_row,
                "uid": uid,
                "user": user,
                "property_type_labels": PROPERTY_TYPE_LABELS,
                "safe_room_labels": SAFE_ROOM_LABELS,
                "furniture_labels": FURNITURE_LABELS,
            },
        )


@app.post("/filter")
def filter_update(
    uid: int = Form(...),
    cities: str = Form(""),
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
        f.cities = [c.strip() for c in cities.split(",") if c.strip()]
        f.price_min = int(price_min) if price_min.strip() else None
        f.price_max = int(price_max) if price_max.strip() else None
        f.rooms_min = float(rooms_min) if rooms_min.strip() else None
        f.rooms_max = float(rooms_max) if rooms_max.strip() else None
        f.property_types = [p for p in property_types if p in PROPERTY_TYPE_LABELS]
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
        f.safe_room_pref = safe_room_pref if safe_room_pref in SAFE_ROOM_LABELS else "any"
        f.furniture_pref = furniture_pref if furniture_pref in FURNITURE_LABELS else "any"
        f.min_area_sqm = int(min_area_sqm) if min_area_sqm.strip() else None
        f.keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        f.flexible_match = flexible_match is not None
        session.commit()

    return RedirectResponse(f"/filter?uid={uid}", status_code=303)
