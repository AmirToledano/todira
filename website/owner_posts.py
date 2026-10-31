"""Free posting for flat owners (2026-10-31, owner approved the draft).

An owner fills a form on /post: city, street, rooms, price, size, floor, entry date, a description, up to MAX_PHOTOS
photos, a name and a phone. Nothing goes up on its own: the post waits as "pending", the owner gets a note in his inbox
group and approves or rejects it on /admin/posts. An approved post becomes a Listing with source "owner" (its photos
served from /owner-photos/<id>.jpg), so it matches searches and is alerted by the next scraper run like any new ad. The
poster's name and phone are shown only to people with access, on /owner-ad/<post id> (the same gate as the original-ad
link of every other listing). The poster can take the flat down any time from the private link they get after posting,
and an owner listing is taken down by itself after POST_DAYS (scraper/main.py).
"""
from __future__ import annotations

import datetime as dt
import io
import re
import secrets
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select

from todira_common.enums import DealType, Source
from todira_common.models import Listing, OwnerPost, OwnerPostPhoto

MAX_PHOTOS = 6
MAX_PHOTO_BYTES = 12 * 1024 * 1024
PHOTO_MAX_SIDE = 1600
POSTS_PER_VISITOR_PER_DAY = 3
POST_DAYS = 30
_PHONE_RE = re.compile(r"^0(5\d|[2-489]|7\d)\d{7}$")


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"[\s\-()]", "", raw or "")
    if digits.startswith("+972"):
        digits = "0" + digits[4:]
    elif digits.startswith("972"):
        digits = "0" + digits[3:]
    return digits if _PHONE_RE.match(digits) else None


def _int(raw: str, low: int, high: int) -> int | None:
    try:
        value = int(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return value if low <= value <= high else None


def parse(form: dict, localities: set[str], today: dt.date) -> tuple[dict, list[str]]:
    """The cleaned fields and the names of the fields that are wrong (empty list = fine)."""
    errors: list[str] = []
    fields: dict = {}
    city = (form.get("city") or "").strip()
    if city not in localities:
        errors.append("city")
    fields["city"] = city
    fields["street"] = (form.get("street") or "").strip()[:80] or None
    try:
        rooms = Decimal((form.get("rooms") or "").strip())
        if not (Decimal("1") <= rooms <= Decimal("12")) or rooms * 2 != int(rooms * 2):
            raise InvalidOperation
        fields["rooms"] = rooms
    except InvalidOperation:
        errors.append("rooms")
    price = _int(form.get("price"), 300, 100_000)
    if price is None:
        errors.append("price")
    fields["price"] = price
    fields["size_sqm"] = _int(form.get("size"), 8, 1000) if (form.get("size") or "").strip() else None
    if (form.get("size") or "").strip() and fields["size_sqm"] is None:
        errors.append("size")
    fields["floor"] = _int(form.get("floor"), -3, 60) if (form.get("floor") or "").strip() else None
    if (form.get("floor") or "").strip() and fields["floor"] is None:
        errors.append("floor")
    entry = (form.get("move_in") or "").strip()
    fields["move_in_date"] = None
    if entry:
        try:
            fields["move_in_date"] = dt.date.fromisoformat(entry)
        except ValueError:
            errors.append("move_in")
        else:
            if fields["move_in_date"] < today or fields["move_in_date"] > today + dt.timedelta(days=366):
                errors.append("move_in")
    description = (form.get("description") or "").strip()
    if not 20 <= len(description) <= 2000:
        errors.append("description")
    fields["description"] = description
    name = (form.get("name") or "").strip()
    if not 2 <= len(name) <= 60:
        errors.append("name")
    fields["contact_name"] = name
    phone = normalize_phone(form.get("phone") or "")
    if phone is None:
        errors.append("phone")
    fields["contact_phone"] = phone
    if form.get("confirm") != "1":
        errors.append("confirm")
    return fields, errors


def resize_photo(data: bytes) -> bytes | None:
    """A JPEG at most PHOTO_MAX_SIDE on its longer side, or None when the file is not a picture we can read."""
    from PIL import Image, ImageOps

    if not data or len(data) > MAX_PHOTO_BYTES:
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
            image.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE))
            out = io.BytesIO()
            image.save(out, "JPEG", quality=82, optimize=True)
            return out.getvalue()
    except Exception:
        return None


def posts_today(session, visitor: str, now: dt.datetime) -> int:
    return session.scalar(
        select(func.count()).select_from(OwnerPost).where(
            OwnerPost.visitor == visitor, OwnerPost.created_at >= now - dt.timedelta(days=1)
        )
    ) or 0


def create(session, fields: dict, photos: list[bytes], visitor: str) -> OwnerPost:
    post = OwnerPost(**fields, manage_token=secrets.token_urlsafe(24), visitor=visitor, status="pending")
    session.add(post)
    session.flush()
    for position, jpeg in enumerate(photos[:MAX_PHOTOS]):
        session.add(OwnerPostPhoto(post_id=post.id, position=position, jpeg=jpeg))
    session.commit()
    return post


def photo_ids(session, post_id: int) -> list[int]:
    return list(
        session.scalars(select(OwnerPostPhoto.id).where(OwnerPostPhoto.post_id == post_id).order_by(OwnerPostPhoto.position))
    )


def approve(session, post: OwnerPost, website_url: str, now: dt.datetime) -> Listing:
    """Makes the post a live Listing. The next scraper run alerts everyone it matches (its retry pass picks up listings
    nobody was told about yet)."""
    listing = Listing(
        source=Source.OWNER,
        external_id=str(post.id),
        url=f"{website_url}/owner-ad/{post.id}",
        deal_type=DealType.RENT,
        price=post.price,
        rooms=post.rooms,
        floor=post.floor,
        size_sqm=post.size_sqm,
        city=post.city,
        street=post.street,
        move_in_date=post.move_in_date,
        move_in_note=None if post.move_in_date else "מיידית",
        description=post.description,
        image_urls=[f"{website_url}/owner-photos/{photo_id}.jpg" for photo_id in photo_ids(session, post.id)],
        is_broker_listing=False,
        posted_at=now,
        scraped_at=now,
        first_seen_at=now,
        details_fetched_at=now,
    )
    session.add(listing)
    session.flush()
    post.status, post.reviewed_at, post.listing_id = "approved", now, listing.id
    session.commit()
    return listing


def reject(session, post: OwnerPost, now: dt.datetime) -> None:
    post.status, post.reviewed_at = "rejected", now
    session.commit()


def take_down(session, post: OwnerPost, now: dt.datetime) -> None:
    """The poster removed the flat (or it expired): its listing stops being shown and matched."""
    post.status = "removed"
    if post.listing_id is not None:
        listing = session.get(Listing, post.listing_id)
        if listing is not None and not listing.is_delisted:
            listing.is_delisted, listing.delisted_at = True, now
    session.commit()
