"""The city behind the home page's hero (2026-11-13, owner: drawings of buildings and of Todi on the site).

One inline SVG, drawn once at import from a fixed seed so every visit sees the same street: a back row of towers in
outline and a front row of low blocks of flats with real window grids, solar water heaters on the roofs, a few on
pillars and a few palm trees. Everything is stroked with currentColor and the CSS decides the colours (home.css,
.lp-sky), so it follows light and dark. The windows carry class "w" so home.js can light one up whenever a new flat
comes in. Decoration only: the whole thing is aria-hidden."""
from __future__ import annotations

import random
from functools import lru_cache

from markupsafe import Markup

WIDTH, HEIGHT = 1440, 240
_FLOOR = 17          # one storey, in SVG units
_PILLARS = 14        # the open ground floor of a block on pillars
_SEED = 13112026


def _n(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _back_row(rnd: random.Random) -> list[str]:
    out = []
    x = -24.0
    while x < WIDTH:
        w = rnd.randint(44, 92)
        h = rnd.randint(96, 212)
        top = HEIGHT - h
        out.append(f'<rect x="{_n(x)}" y="{_n(top)}" width="{w}" height="{h}" rx="2"/>')
        # the tower's own lines: floors on the wide ones, two vertical bands on the narrow ones
        if w > 64:
            for fy in range(int(top) + 14, HEIGHT - 6, 15):
                out.append(f'<path d="M{_n(x + 6)} {fy}h{w - 12}"/>')
        else:
            for k in (1, 2):
                vx = x + w * k / 3
                out.append(f'<path d="M{_n(vx)} {_n(top + 8)}V{HEIGHT}"/>')
        if rnd.random() < 0.35:
            out.append(f'<path d="M{_n(x + w / 2)} {_n(top)}v-{rnd.randint(12, 26)}"/>')
        x += w + rnd.randint(6, 34)
    return out


def _solar_heater(x: float, roof: float) -> str:
    """The Israeli roof: a tilted panel with its water tank lying behind it, on two short legs."""
    return (f'<path d="M{_n(x)} {_n(roof)}l3-9h13l-3 9z"/>'
            f'<rect x="{_n(x + 12)}" y="{_n(roof - 13)}" width="13" height="6" rx="3"/>'
            f'<path d="M{_n(x + 15)} {_n(roof - 7)}v7M{_n(x + 22)} {_n(roof - 7)}v7"/>')


def _palm(x: float) -> str:
    base = HEIGHT
    top = base - 74
    return (f'<path class="lp-sky-palm" d="M{_n(x)} {base}C{_n(x + 2)} {base - 30} {_n(x - 4)} {top + 24} {_n(x + 2)} {top}"/>'
            f'<path class="lp-sky-palm" d="M{_n(x + 2)} {top}c-8-6-18-6-26 2M{_n(x + 2)} {top}c-4-10-14-14-22-12'
            f'M{_n(x + 2)} {top}c6-10 16-12 24-8M{_n(x + 2)} {top}c10-2 18 4 22 12M{_n(x + 2)} {top}c-10 2-16 10-18 18"/>')


def _front_row(rnd: random.Random) -> tuple[list[str], list[str]]:
    blocks, windows = [], []
    x = -12.0
    while x < WIDTH:
        if rnd.random() < 0.13:
            blocks.append(_palm(x + 16))
            x += 40
            continue
        w = rnd.randint(78, 150)
        floors = rnd.randint(3, 7)
        pillars = rnd.random() < 0.3
        h = floors * _FLOOR + (_PILLARS if pillars else 0) + 6
        top = HEIGHT - h
        blocks.append(f'<rect class="lp-sky-block" x="{_n(x)}" y="{_n(top)}" width="{w}" height="{h + 2}" rx="2"/>')
        if pillars:
            py = HEIGHT - _PILLARS
            blocks.append(f'<path d="M{_n(x)} {py}h{w}"/>')
            for px in range(int(x) + 10, int(x + w) - 4, 22):
                blocks.append(f'<path d="M{px} {py}V{HEIGHT}"/>')
        cols = max(2, (w - 14) // 19)
        gap = (w - cols * 9) / (cols + 1)
        for f in range(floors):
            wy = top + 7 + f * _FLOOR
            for c in range(cols):
                wx = x + gap + c * (9 + gap)
                windows.append(f'<rect class="w" x="{_n(wx)}" y="{_n(wy)}" width="9" height="10" rx="1"/>')
            if rnd.random() < 0.25:  # a row of balconies
                blocks.append(f'<path d="M{_n(x + 4)} {_n(wy + 13)}h{w - 8}"/>')
        for k in range(rnd.choice((0, 1, 1, 2, 3))):
            sx = x + 6 + k * 30
            if sx + 26 < x + w:
                blocks.append(_solar_heater(sx, top))
        if rnd.random() < 0.25:
            ax = x + w - 12
            blocks.append(f'<path d="M{_n(ax)} {_n(top)}v-16M{_n(ax - 6)} {_n(top - 11)}h12"/>')
        x += w + rnd.randint(8, 26)
    return blocks, windows


@lru_cache(maxsize=1)
def skyline_svg() -> Markup:
    rnd = random.Random(_SEED)
    back = _back_row(rnd)
    blocks, windows = _front_row(rnd)
    svg = (
        f'<svg class="lp-sky-svg" viewBox="0 0 {WIDTH} {HEIGHT}" preserveAspectRatio="xMidYMax slice" '
        f'aria-hidden="true" focusable="false">'
        f'<g class="lp-sky-back">{"".join(back)}</g>'
        f'<g class="lp-sky-front">{"".join(blocks)}<g class="lp-sky-windows">{"".join(windows)}</g>'
        f'<path class="lp-sky-ground" d="M0 {HEIGHT - 0.5}H{WIDTH}"/></g>'
        f'</svg>'
    )
    return Markup(svg)
