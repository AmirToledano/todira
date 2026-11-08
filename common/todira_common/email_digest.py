"""The morning email of the flats that matched someone's search since the last one (2026-11-08, owner: "Dorin also emails
the flats that matched that day, by the user's own settings").

Built here, sent by scraper/email_digest.py, stopped by the link at its bottom (website /email/stop). Only the public
share page of each flat is linked (todira_common.share), never the original ad, and the sites ads come from are never
named. Hebrew, right to left, plain tables so every mail app shows it the same.
"""
from __future__ import annotations

import html
import os

from itsdangerous import BadSignature, URLSafeSerializer

from todira_common.share import share_url

SITE_URL = os.environ.get("WEBSITE_URL", "https://todira.app").rstrip("/")
BOT_URL = "https://t.me/AmirDirotBot?start=email_digest"
OFF_FLAG = "email_digest_off"  # app_flags: JSON list of user ids who stopped the email
MAX_CARDS = 10
_serializer = URLSafeSerializer(os.environ.get("SESSION_SECRET_KEY", "dev-only-insecure-session-key"), salt="email-digest-stop")


def stop_token(user_id: int) -> str:
    return _serializer.dumps(user_id)


def user_from_stop_token(token: str) -> int | None:
    try:
        value = _serializer.loads(token)
    except BadSignature:
        return None
    return value if isinstance(value, int) else None


def stop_url(user_id: int) -> str:
    return f"{SITE_URL}/email/stop?t={stop_token(user_id)}"


def _money(value) -> str:
    return f"₪{int(value):,}" if value else "מחיר לא צוין"


def _facts(listing) -> str:
    parts = []
    if listing.rooms:
        rooms = float(listing.rooms)
        parts.append(f"{rooms:g} חדרים")
    if listing.floor is not None:
        parts.append("קרקע" if listing.floor == 0 else f"קומה {listing.floor}")
    if listing.size_sqm:
        parts.append(f"{int(listing.size_sqm)} מ״ר")
    return ", ".join(parts)


def _place(listing) -> str:
    return ", ".join(p for p in (listing.street, listing.neighborhood, listing.city) if p)


def _card(listing) -> str:
    link = html.escape(f"{share_url(listing.id)}?src=email_digest")
    photo = next((u for u in (listing.image_urls or []) if isinstance(u, str) and u.startswith("https://")), None)
    image = (
        f'<a href="{link}"><img src="{html.escape(photo)}" width="520" alt="" '
        'style="display:block;width:100%;max-width:520px;height:auto;border-radius:12px 12px 0 0"></a>'
        if photo else ""
    )
    return (
        '<tr><td style="padding:0 0 18px">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="background:#ffffff;border:1px solid #e6e1d4;border-radius:12px">'
        f"<tr><td>{image}</td></tr>"
        '<tr><td style="padding:14px 16px;text-align:right">'
        f'<div style="font-size:22px;font-weight:700;color:#173c40">{_money(listing.price)}</div>'
        f'<div style="font-size:15px;color:#1e2a29;margin-top:4px">{html.escape(_facts(listing))}</div>'
        f'<div style="font-size:14px;color:#66787c;margin-top:2px">{html.escape(_place(listing))}</div>'
        f'<a href="{link}" style="display:inline-block;margin-top:12px;background:#0e8a82;color:#ffffff;'
        'text-decoration:none;font-weight:700;padding:10px 20px;border-radius:999px">לפרטי הדירה</a>'
        "</td></tr></table></td></tr>"
    )


def subject(count: int, city: str | None) -> str:
    where = f" ב{city}" if city else ""
    return f"{count} דירות חדשות{where} שמתאימות לך" if count > 1 else f"דירה חדשה{where} שמתאימה לך"


def build(listings: list, user_id: int, first_name: str | None, city: str | None, total: int) -> tuple[str, str, str]:
    """(subject, html, text) for `listings` (newest first, up to MAX_CARDS shown) out of `total` new matches."""
    shown = listings[:MAX_CARDS]
    hello = f"היי {html.escape(first_name)}," if first_name else "היי,"
    more = total - len(shown)
    more_html = (
        f'<p style="margin:0 0 18px;text-align:center"><a href="{SITE_URL}/apartments?src=email_digest" '
        f'style="color:#0e8a82;font-weight:700">ועוד {more} דירות באתר</a></p>' if more > 0 else ""
    )
    page = (
        '<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"></head>'
        '<body style="margin:0;background:#fbf7ef;font-family:Heebo,Arial,sans-serif;direction:rtl">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#fbf7ef">'
        '<tr><td align="center" style="padding:24px 12px">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:540px">'
        '<tr><td style="text-align:right;padding:0 0 6px;font-size:20px;font-weight:800;color:#0e8a82">טודירה</td></tr>'
        f'<tr><td style="text-align:right;padding:0 0 18px;font-size:16px;color:#1e2a29;line-height:1.6">{hello}<br>'
        "אלה הדירות החדשות שעלו מאז המייל הקודם ומתאימות לחיפוש שלך.</td></tr>"
        + "".join(_card(listing) for listing in shown)
        + f"<tr><td>{more_html}</td></tr>"
        '<tr><td style="background:#eaf5f3;border-radius:12px;padding:16px;text-align:center;font-size:15px;color:#173c40">'
        "רוצה לקבל כל דירה ברגע שהיא עולה, ולא פעם ביום?<br>"
        f'<a href="{BOT_URL}" style="color:#0e8a82;font-weight:700">התראות מיידיות בטלגרם</a></td></tr>'
        '<tr><td style="padding:18px 0 0;text-align:center;font-size:12px;color:#66787c;line-height:1.6">'
        "קיבלת את המייל כי נרשמת לטודירה עם החשבון הזה.<br>"
        f'<a href="{html.escape(stop_url(user_id))}" style="color:#66787c">להפסיק לקבל את המייל הזה</a>'
        "</td></tr></table></td></tr></table></body></html>"
    )
    lines = [f"היי {first_name}," if first_name else "היי,", "אלה הדירות החדשות שעלו מאז המייל הקודם ומתאימות לחיפוש שלך.", ""]
    for listing in shown:
        lines += [f"{_money(listing.price)} | {_facts(listing)} | {_place(listing)}", f"{share_url(listing.id)}?src=email_digest", ""]
    if more > 0:
        lines.append(f"ועוד {more} דירות באתר: {SITE_URL}/apartments")
    lines += ["", f"להפסיק לקבל את המייל הזה: {stop_url(user_id)}"]
    return subject(total, city), page, "\n".join(lines)
