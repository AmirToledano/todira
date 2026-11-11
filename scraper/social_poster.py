"""A post a day on Todira's own Facebook Page and Instagram, from our own numbers (2026-11-11, owner: "build a social
media manager that runs everything, from Instagram to Facebook").

Once a day, in the morning (FROM_HOUR..UNTIL_HOUR Israel), the main scraper publishes one post on the Page and the
same images on Instagram (todira_common/meta_api.py, Meta's official API). Real numbers only, in the site's look:
  Thursday       the weekly carousel (instagram_kit.py: where renting 3 rooms is cheapest),
  Sun, Tue, Sat  the week's busiest cities (new flats in 7 days, rent and sale),
  Mon, Wed, Fri  the last 24 hours (new flats, rent and sale, and the cities with the most).
Every caption asks for a "דירה" comment, which the website answers with the link at once (social_replies.py). The
day posted is kept in app_flags. Nothing happens until the owner has set the Meta keys.
"""
from __future__ import annotations

import datetime as dt
import logging

import instagram_kit as ik
import weekly_image as wi
from PIL import Image, ImageDraw
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from todira_common import alert_hours, app_flags, meta_api
from todira_common.models import Listing

logger = logging.getLogger(__name__)

FROM_HOUR, UNTIL_HOUR = 10, 12
_FLAG = "social_posted"
THURSDAY = 3
HOT_DAYS = (6, 1, 5)  # Sunday, Tuesday, Saturday (Monday is 0)
MIN_CITIES = 3
ASK = "רוצים לקבל כל דירה חדשה שמתאימה לכם? כתבו \"דירה\" בתגובות ונשלח לכם קישור."
HASHTAGS = "#דירות #דירהלהשכרה #דירותלהשכרה #שכירות #מחפשיםדירה #חיפושדירה #נדלן #טודירה"


def due(state: str | None, now: dt.datetime) -> str | None:
    local = alert_hours.israel_now(now)
    if not FROM_HOUR <= local.hour < UNTIL_HOUR:
        return None
    label = local.date().isoformat()
    return None if state == label else label


def _counts(session: Session, since: dt.timedelta, limit: int = 8) -> tuple[dict, list[tuple[str, int, int]]]:
    live = (Listing.is_delisted.is_(False), Listing.duplicate_of_id.is_(None),
            Listing.first_seen_at >= func.now() - since)
    totals = dict(session.execute(select(Listing.deal_type, func.count()).where(*live).group_by(Listing.deal_type)).all())
    rows = session.execute(
        select(Listing.city, func.count().filter(Listing.deal_type == "rent"), func.count().filter(Listing.deal_type == "sale"))
        .where(*live, Listing.city.is_not(None))
        .group_by(Listing.city)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    return totals, [(city, int(rent or 0), int(sale or 0)) for city, rent, sale in rows]


def _num(n: int) -> str:
    return f"{n:,}"


def cities_png(title: tuple[str, str], subtitle: str, rows: list[tuple[str, int, int]], raqm: bool) -> bytes:
    """A ranked list of cities with a bar each and their rent / sale counts, in the weekly post's look."""
    image = Image.new("RGB", (wi.WIDTH, wi.HEIGHT), wi.CREAM)
    draw = ImageDraw.Draw(image)
    right = wi.WIDTH - wi.SIDE
    wi._draw_rtl(draw, (right, 92), "טודירה", wi._font("Bold", 34, raqm), wi.TEAL, raqm, anchor="rs")
    draw.rectangle((right - 64, 116, right, 122), fill=wi.GOLD)
    y = ik._lines(draw, [(title[0], "Bold", 84, wi.DARK_TEAL), (title[1], "Bold", 84, wi.TEAL)], 170, raqm, gap=20)
    y = ik._lines(draw, [(subtitle, "Regular", 36, wi.MUTED)], y + 6, raqm)
    top = max(r + s for _c, r, s in rows) or 1
    row_h = min(104, (1220 - y) // max(1, len(rows)))
    y += 24
    for n, (city, rent, sale) in enumerate(rows, 1):
        draw.text((right, y + 34), str(n), font=wi._font("Bold", 34, raqm), fill=wi.MUTED, anchor="rm")
        wi._draw_rtl(draw, (right - 52, y + 34), city, wi._fit(draw, city, "Bold", 44, 470, raqm), wi.DARK_TEAL, raqm,
                     anchor="rm")
        bar_right, bar_left = right - 52, right - 52 - 470
        draw.rounded_rectangle((bar_left, y + 66, bar_right, y + 78), radius=6, fill=wi.BAR_BACK)
        width = max(14, int(470 * (rent + sale) / top))
        draw.rounded_rectangle((bar_right - width, y + 66, bar_right, y + 78), radius=6, fill=wi.TEAL)
        parts = [p for p in (f"השכרה {_num(rent)}" if rent else "", f"מכירה {_num(sale)}" if sale else "") if p]
        label = "   ".join(parts)
        wi._draw_rtl(draw, (wi.SIDE + wi._width(draw, label, wi._font("Bold", 30, raqm), raqm), y + 36), label,
                     wi._font("Bold", 30, raqm), wi.TEAL, raqm, anchor="rm")
        y += row_h
    draw.text((wi.WIDTH // 2, 1290), "todira.app", font=wi._font("Bold", 36, raqm), fill=wi.TEAL, anchor="ms")
    return ik._png(image)


def week_post(session: Session, raqm: bool) -> tuple[list[bytes], str] | None:
    totals, rows = _counts(session, dt.timedelta(days=7))
    if len(rows) < MIN_CITIES:
        return None
    week = sum(totals.values())
    png = cities_png(("איפה הכי חם", "השבוע?"), f"{_num(week)} דירות חדשות ב־7 הימים האחרונים", rows, raqm)
    lead = rows[0]
    caption = "\n".join([
        f"השבוע נכנסו {_num(week)} דירות חדשות, והכי הרבה ב{lead[0]} 🔥",
        "",
        "העיר שלכם ברשימה? ספרו בתגובות איפה אתם מחפשים.",
        "",
        ASK,
        "",
        HASHTAGS,
    ])
    return [png], caption


def day_post(session: Session, raqm: bool) -> tuple[list[bytes], str] | None:
    totals, rows = _counts(session, dt.timedelta(hours=24), limit=6)
    if len(rows) < MIN_CITIES:
        return None
    rent, sale = int(totals.get("rent", 0)), int(totals.get("sale", 0))
    subtitle = f"{_num(rent)} להשכרה, {_num(sale)} למכירה"
    png = cities_png(("ביממה האחרונה", f"{_num(rent + sale)} דירות חדשות"), subtitle, rows, raqm)
    caption = "\n".join([
        f"ביממה האחרונה נכנסו {_num(rent + sale)} דירות חדשות. מי שראה אותן ראשון כבר מתאם ביקור 🏃",
        "",
        "טודירה שולחת לכם לטלגרם כל דירה חדשה שמתאימה לחיפוש שלכם, ברגע שהיא עולה.",
        "",
        ASK,
        "",
        HASHTAGS,
    ])
    return [png], caption


def thursday_post(session: Session, now: dt.datetime, raqm: bool) -> tuple[list[bytes], str] | None:
    from channel import (
        weekly_prices,  # the Friday channel post's own numbers, as instagram_kit uses
    )

    rows = weekly_prices(session, now)
    if len(rows) < ik.MIN_CITIES:
        return None
    caption = ik.caption(rows).replace("רוצים לשמוע על כל דירה חדשה ברגע שהיא עולה? הקישור בביו.", ASK)
    return ik.slides(rows, now, raqm), caption


def todays_post(session: Session, now: dt.datetime) -> tuple[list[bytes], str] | None:
    raqm = wi.use_raqm()
    weekday = alert_hours.israel_now(now).weekday()
    if weekday == THURSDAY:
        return thursday_post(session, now, raqm) or week_post(session, raqm)
    if weekday in HOT_DAYS:
        return week_post(session, raqm)
    return day_post(session, raqm)


def run_social_poster(session: Session, now: dt.datetime | None = None) -> dict[str, str]:
    now = now or dt.datetime.now(dt.timezone.utc)
    if not meta_api.page_enabled():
        return {}
    label = due(app_flags.get_flag(session, _FLAG), now)
    if label is None:
        return {}
    post = todays_post(session, now)
    if post is None:
        return {}
    pngs, caption = post
    # Marked first: a failure part-way must not post the same thing twice in the next run.
    app_flags.set_flag(session, _FLAG, label)
    result = {"social_post": label}
    try:
        _post_id, urls = meta_api.publish_page_photos(pngs, caption)
        result["social_facebook"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("social post: Facebook failed: %s", exc)
        return {**result, "social_facebook": "failed"}
    if meta_api.instagram_enabled() and urls:
        try:
            meta_api.publish_instagram(urls, caption)
            result["social_instagram"] = "ok"
        except Exception as exc:  # noqa: BLE001
            logger.warning("social post: Instagram failed: %s", exc)
            result["social_instagram"] = "failed"
    return result
