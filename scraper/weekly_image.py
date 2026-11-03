"""The Friday channel post as a picture (2026-11-04 (owner): a plain text list is not something people forward; one
designed image of the 3-room prices is easy to share, the links stay in its caption).

render_weekly_png(rows, start, end) -> PNG bytes, 1080x1350 (Instagram/Telegram portrait), in the site's look: cream
background, dark teal text, teal bars, a gold accent. Font: Rubik (OFL, scraper/fonts/OFL.txt), bundled so the image
looks the same everywhere.

Hebrew right to left: Pillow lays out RTL text by itself when its RAQM layout engine is available (the wheel brings it,
but it needs the system's libfribidi, installed in scraper/Dockerfile*). Without it, _visual() puts each line into
display order by hand, which is enough for the short lines drawn here (Hebrew words, numbers, dates, ₪ prices).
"""
from __future__ import annotations

import datetime as dt
import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

WIDTH, HEIGHT = 1080, 1350
CREAM = "#fbf7ef"
TEAL = "#0e8a82"
DARK_TEAL = "#173c40"
GOLD = "#d9a441"
MUTED = "#5d6f70"
LINE = "#e6dccb"
BAR_BACK = "#efe7d8"
FONTS = Path(__file__).resolve().parent / "fonts"
SIDE = 84


def use_raqm() -> bool:
    return features.check("raqm")


@lru_cache(maxsize=None)
def _font(weight: str, size: int, raqm: bool) -> ImageFont.FreeTypeFont:
    engine = ImageFont.Layout.RAQM if raqm else ImageFont.Layout.BASIC
    return ImageFont.truetype(str(FONTS / f"Rubik-{weight}.ttf"), size, layout_engine=engine)


def _is_rtl(char: str) -> bool:
    return "֐" <= char <= "ࣿ" or "יִ" <= char <= "﷿"


def _is_ltr(char: str) -> bool:
    return char.isascii() and char.isalnum()


_MIRROR = str.maketrans("()[]<>", ")(][><")


def _visual(text: str) -> str:
    """A right-to-left line in the order its characters appear on screen, for when Pillow cannot lay it out itself.
    Runs of Hebrew are reversed, runs of digits/Latin (with the . , : / ₪ between or next to them, like 7.10.2026 or
    ₪4,000) keep their order, and the runs themselves go right to left. A space between two Latin runs stays with them."""
    kinds = []
    for char in text:
        if _is_rtl(char):
            kinds.append("R")
        elif _is_ltr(char):
            kinds.append("L")
        else:
            kinds.append(None)
    # neutrals take a direction from their neighbours: L only when both sides are L, else R (the line's own direction).
    # ₪ and a sign stuck to a number count as part of it.
    for index, kind in enumerate(kinds):
        if kind is not None:
            continue
        before = next((k for k in reversed(kinds[:index]) if k is not None), None)
        after = next((k for k in kinds[index + 1:] if k is not None), None)
        stuck = text[index] in "₪%$-+" and (
            (index + 1 < len(text) and _is_ltr(text[index + 1])) or (index > 0 and _is_ltr(text[index - 1]))
        )
        kinds[index] = "N" if not (before == after == "L" or stuck) else "l"
    runs: list[tuple[bool, str]] = []
    for char, kind in zip(text, kinds):
        ltr = kind in ("L", "l")
        if runs and runs[-1][0] == ltr:
            runs[-1] = (ltr, runs[-1][1] + char)
        else:
            runs.append((ltr, char))
    return "".join(chunk if ltr else chunk[::-1].translate(_MIRROR) for ltr, chunk in reversed(runs))


def _draw_rtl(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, raqm: bool, anchor: str = "ra") -> None:
    if raqm:
        draw.text(xy, text, font=font, fill=fill, anchor=anchor, direction="rtl")
    else:
        draw.text(xy, _visual(text), font=font, fill=fill, anchor=anchor)


def _width(draw, text: str, font, raqm: bool) -> float:
    if raqm:
        return draw.textlength(text, font=font, direction="rtl")
    return draw.textlength(_visual(text), font=font)


def _fit(draw, text: str, weight: str, size: int, max_width: int, raqm: bool):
    """The biggest font up to size that fits text in max_width (a long city name gets a little smaller, never cut)."""
    while size > 20 and _width(draw, text, _font(weight, size, raqm), raqm) > max_width:
        size -= 2
    return _font(weight, size, raqm)


def _money(value: int) -> str:
    return f"₪{int(value):,}"


def date_range(start: dt.date, end: dt.date) -> str:
    first = f"{start.day}.{start.month}" + (f".{start.year}" if start.year != end.year else "")
    return f"{first} עד {end.day}.{end.month}.{end.year}"


def render_weekly_png(rows: list[tuple[str, int]], start: dt.date, end: dt.date, *, raqm: bool | None = None) -> bytes:
    """rows: (city, 3-room median), most listings first, up to 10."""
    if not rows:
        raise ValueError("no cities to draw")
    raqm = use_raqm() if raqm is None else raqm
    image = Image.new("RGB", (WIDTH, HEIGHT), CREAM)
    draw = ImageDraw.Draw(image)
    right = WIDTH - SIDE

    _draw_rtl(draw, (right, 92), "טודירה", _font("Bold", 34, raqm), TEAL, raqm, anchor="rs")
    draw.rectangle((right - 64, 116, right, 122), fill=GOLD)

    _draw_rtl(draw, (right, 222), "כמה עולה היום לשכור", _font("Bold", 74, raqm), DARK_TEAL, raqm, anchor="rs")
    _draw_rtl(draw, (right, 314), "דירת 3 חדרים", _font("Bold", 74, raqm), TEAL, raqm, anchor="rs")
    small = _font("Regular", 32, raqm)
    _draw_rtl(draw, (right, 378), "המחיר האמצעי לחודש, לפי הדירות שעלו", small, MUTED, raqm, anchor="rs")
    _draw_rtl(draw, (right, 422), date_range(start, end), _font("Bold", 32, raqm), DARK_TEAL, raqm, anchor="rs")

    top, bottom = 488, 1188
    rows = rows[:10]
    row_height = min(70, (bottom - top) // len(rows))
    highest = max(price for _, price in rows)
    city_width, price_width = 300, 190
    bar_right = right - city_width - 24
    bar_left = SIDE + price_width + 24
    for number, (city, price) in enumerate(rows):
        y = top + number * row_height
        middle = y + row_height // 2
        if number:
            draw.line((SIDE, y, right, y), fill=LINE, width=2)
        _draw_rtl(draw, (right, middle), city, _fit(draw, city, "Regular", 40, city_width, raqm), DARK_TEAL, raqm,
                  anchor="rm")
        draw.text((SIDE, middle), _money(price), font=_font("Bold", 40, raqm), fill=DARK_TEAL, anchor="lm")
        length = max(12, round((bar_right - bar_left) * price / highest))
        draw.rounded_rectangle((bar_left, middle - 9, bar_right, middle + 9), radius=9, fill=BAR_BACK)
        draw.rounded_rectangle((bar_right - length, middle - 9, bar_right, middle + 9), radius=9,
                               fill=GOLD if price == highest else TEAL)

    draw.line((SIDE, 1232, right, 1232), fill=LINE, width=2)
    _draw_rtl(draw, (right, 1286), "כל הערים והשכונות באתר", small, MUTED, raqm, anchor="rm")
    draw.text((SIDE, 1286), "todira.app", font=_font("Bold", 36, raqm), fill=TEAL, anchor="lm")

    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
