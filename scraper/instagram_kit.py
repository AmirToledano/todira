"""A ready Instagram carousel for the owner, once a week (2026-11-05, owner: "manage the Instagram account I'm opening
for Todira, so it gets known and people come to the site and the bot").

Nothing is posted to Instagram from here. Thursday morning (09:00-11:59 Israel) the owner's inbox group gets an album
of 4 portrait slides (1080x1350) drawn from our own numbers, in the site's look, and the caption ready to copy:

1. the question (where is it cheapest to rent 3 rooms now),
2. the 3-room median of the biggest cities (the same picture as the Friday channel post, weekly_image.py),
3. the gap between the cheapest and the dearest of them, a month and a year,
4. what Todira does and where the link is (the bio, todira.app/?src=ig, counted as "src_ig").

Real numbers only: the same rows as the channel's Friday post (channel.weekly_prices). When there are fewer than 3
cities nothing is sent. The week sent is kept in app_flags. Main scraper only.
"""
from __future__ import annotations

import datetime as dt
import html
import io
import json
import logging
import os

import httpx
from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

import weekly_image as wi
from todira_common import alert_hours, app_flags, owner_inbox

logger = logging.getLogger(__name__)

THURSDAY = 3
FROM_HOUR, UNTIL_HOUR = 9, 12
_FLAG = "instagram_kit_sent"
MIN_CITIES = 3
BIO_LINK = "todira.app/?src=ig"
HASHTAGS = (
    "#דירות #דירהלהשכרה #דירותלהשכרה #שכירות #מחפשיםדירה #חיפושדירה #שוקהדירות #נדלן #שכרדירה "
    "#תלאביב #ירושלים #חיפה #בארשבע #סטודנטים #זוגצעיר"
)


def due(state: str | None, now: dt.datetime) -> str | None:
    """The week's label (ISO year-week) when the kit is due now, else None."""
    local = alert_hours.israel_now(now)
    if local.weekday() != THURSDAY or not FROM_HOUR <= local.hour < UNTIL_HOUR:
        return None
    year, week, _ = local.isocalendar()
    label = f"{year}-{week:02d}"
    return None if state == label else label


def _canvas():
    image = Image.new("RGB", (wi.WIDTH, wi.HEIGHT), wi.CREAM)
    return image, ImageDraw.Draw(image)


def _brand(draw, raqm: bool, page: int, pages: int) -> None:
    right = wi.WIDTH - wi.SIDE
    wi._draw_rtl(draw, (right, 92), "טודירה", wi._font("Bold", 34, raqm), wi.TEAL, raqm, anchor="rs")
    draw.rectangle((right - 64, 116, right, 122), fill=wi.GOLD)
    draw.text((wi.SIDE, 92), f"{page}/{pages}", font=wi._font("Regular", 30, raqm), fill=wi.MUTED, anchor="ls")


def _lines(draw, lines, top: int, raqm: bool, gap: int = 22) -> int:
    """Draws (text, weight, size, colour) lines right-aligned from top; returns the y under the last one."""
    right = wi.WIDTH - wi.SIDE
    y = top
    for text, weight, size, colour in lines:
        font = wi._fit(draw, text, weight, size, wi.WIDTH - 2 * wi.SIDE, raqm)
        y += font.size
        wi._draw_rtl(draw, (right, y), text, font, colour, raqm, anchor="rs")
        y += gap
    return y


def _png(image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def cover_png(raqm: bool) -> bytes:
    image, draw = _canvas()
    _brand(draw, raqm, 1, 4)
    _lines(draw, [
        ("איפה הכי זול", "Bold", 120, wi.DARK_TEAL),
        ("לשכור 3 חדרים", "Bold", 120, wi.TEAL),
        ("עכשיו?", "Bold", 120, wi.DARK_TEAL),
    ], 330, raqm, gap=34)
    _lines(draw, [
        ("לפי הדירות להשכרה שעלו בחודש האחרון", "Regular", 40, wi.MUTED),
        ("בערים עם הכי הרבה דירות", "Regular", 40, wi.MUTED),
    ], 860, raqm)
    wi._draw_rtl(draw, (wi.WIDTH - wi.SIDE, 1260), "החליקו לתשובה", wi._font("Bold", 40, raqm), wi.TEAL, raqm,
                 anchor="rs")
    return _png(image)


def gap_png(cheap: tuple[str, int], dear: tuple[str, int], raqm: bool) -> bytes:
    image, draw = _canvas()
    _brand(draw, raqm, 3, 4)
    month = dear[1] - cheap[1]
    y = _lines(draw, [
        ("ההפרש בין העיר הזולה", "Bold", 64, wi.DARK_TEAL),
        ("ליקרה ביותר", "Bold", 64, wi.DARK_TEAL),
    ], 250, raqm)
    right = wi.WIDTH - wi.SIDE
    y += 60
    for city, price, colour in ((cheap[0], cheap[1], wi.TEAL), (dear[0], dear[1], wi.GOLD)):
        draw.rounded_rectangle((wi.SIDE, y, right, y + 130), radius=20, fill="#ffffff", outline=wi.LINE, width=2)
        wi._draw_rtl(draw, (right - 36, y + 65), city, wi._fit(draw, city, "Bold", 52, 520, raqm), wi.DARK_TEAL,
                     raqm, anchor="rm")
        draw.text((wi.SIDE + 36, y + 65), wi._money(price), font=wi._font("Bold", 56, raqm), fill=colour, anchor="lm")
        y += 160
    y += 50
    y = _lines(draw, [
        (f"{wi._money(month)} בחודש", "Bold", 96, wi.TEAL),
        (f"{wi._money(month * 12)} בשנה", "Bold", 64, wi.DARK_TEAL),
    ], y, raqm, gap=28)
    wi._draw_rtl(draw, (right, 1260), "המחיר האמצעי של 3 חדרים לחודש", wi._font("Regular", 32, raqm), wi.MUTED, raqm,
                 anchor="rs")
    return _png(image)


def cta_png(raqm: bool) -> bytes:
    image, draw = _canvas()
    _brand(draw, raqm, 4, 4)
    y = _lines(draw, [
        ("דירה טובה במחיר טוב", "Bold", 76, wi.DARK_TEAL),
        ("לא מחכה לאף אחד", "Bold", 76, wi.TEAL),
    ], 300, raqm, gap=30)
    _lines(draw, [
        ("טודירה שולחת לכם לטלגרם כל דירה חדשה", "Regular", 44, wi.DARK_TEAL),
        ("שמתאימה לחיפוש שלכם, ברגע שהיא עולה.", "Regular", 44, wi.DARK_TEAL),
        ("יש תקופת ניסיון בחינם.", "Regular", 44, wi.DARK_TEAL),
    ], y + 70, raqm, gap=26)
    right = wi.WIDTH - wi.SIDE
    draw.rounded_rectangle((wi.SIDE, 1040, right, 1180), radius=70, fill=wi.TEAL)
    wi._draw_rtl(draw, (wi.WIDTH // 2, 1110), "הקישור בביו", wi._font("Bold", 56, raqm), "#ffffff", raqm, anchor="mm")
    draw.text((wi.WIDTH // 2, 1265), "todira.app", font=wi._font("Bold", 40, raqm), fill=wi.TEAL, anchor="ms")
    return _png(image)


def slides(rows: list[tuple[str, int]], now: dt.datetime, raqm: bool | None = None) -> list[bytes]:
    raqm = wi.use_raqm() if raqm is None else raqm
    end = alert_hours.israel_now(now).date()
    cheap = min(rows, key=lambda row: row[1])
    dear = max(rows, key=lambda row: row[1])
    return [
        cover_png(raqm),
        wi.render_weekly_png(rows, end - dt.timedelta(days=30), end, raqm=raqm),
        gap_png(cheap, dear, raqm),
        cta_png(raqm),
    ]


def caption(rows: list[tuple[str, int]]) -> str:
    cheap = min(rows, key=lambda row: row[1])
    dear = max(rows, key=lambda row: row[1])
    return "\n".join([
        "איפה הכי זול לשכור 3 חדרים עכשיו? 👇",
        "",
        f"עברנו על הדירות להשכרה שעלו בחודש האחרון ב-{len(rows)} הערים עם הכי הרבה דירות.",
        f"הכי זול: {cheap[0]}, {wi._money(cheap[1])} בחודש.",
        f"הכי יקר: {dear[0]}, {wi._money(dear[1])} בחודש.",
        "",
        "באיזו עיר אתם מחפשים? ספרו בתגובות.",
        "",
        "רוצים לשמוע על כל דירה חדשה ברגע שהיא עולה? הקישור בביו.",
        "",
        HASHTAGS,
    ])


def _send(token: str, chats: list[str], pngs: list[bytes], text: str) -> bool:
    files = {f"s{n}": (f"todira-{n + 1}.png", png, "image/png") for n, png in enumerate(pngs)}
    media = [{"type": "photo", "media": f"attach://s{n}"} for n in range(len(pngs))]
    note = (
        "<b>קרוסלה לאינסטגרם לשבוע הזה</b>\n"
        "להעלות את 4 התמונות לפי הסדר, ולהדביק את הכיתוב (לחיצה עליו מעתיקה):\n\n"
        f"<code>{html.escape(text)}</code>"
    )
    for chat_id in chats:
        try:
            album = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMediaGroup",
                data={"chat_id": chat_id, "media": json.dumps(media)},
                files=files,
                timeout=60.0,
            )
            if album.status_code != 200:
                continue
            httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": note, "parse_mode": "HTML"},
                timeout=10.0,
            )
            return True
        except httpx.HTTPError:
            logger.warning("instagram kit: sending to the owner failed", exc_info=True)
    return False


def run_instagram_kit(session: Session, now: dt.datetime | None = None) -> dict[str, str]:
    from channel import weekly_prices  # the Friday post's own numbers

    now = now or dt.datetime.now(dt.timezone.utc)
    label = due(app_flags.get_flag(session, _FLAG), now)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if label is None or not token:
        return {}
    rows = weekly_prices(session, now)
    if len(rows) < MIN_CITIES:
        return {}
    chats = owner_inbox.owner_chat_ids(os.environ.get("OWNER_TELEGRAM_USER_ID"))
    if not chats or not _send(token, chats, slides(rows, now), caption(rows)):
        return {}
    app_flags.set_flag(session, _FLAG, label)
    return {"instagram_kit": label}
