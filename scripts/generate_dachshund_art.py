"""One-off asset generator — NOT run at deploy/runtime. Draws a handful of cute, colorful cartoon
dachshund (תחש) PNGs with plain PIL shapes (no external image APIs, no network, no cost) and writes
identical copies to both common/dorin_common/assets/dachshunds/ (read directly by the bot/scraper,
see cards.py) and website/static/dachshunds/ (served as static files by the website — its Docker
image only mounts website/static/, not the dorin_common package tree, see website/Dockerfile).

Re-run manually (`python scripts/generate_dachshund_art.py`) and commit the resulting PNGs if the
art needs to change; nothing imports this module at runtime.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIRS = [
    Path(__file__).resolve().parent.parent / "common" / "dorin_common" / "assets" / "dachshunds",
    Path(__file__).resolve().parent.parent / "website" / "static" / "dachshunds",
]

W, H = 480, 340

# (name, body, belly, ear, collar)
PALETTES = [
    ("chocolate", (121, 74, 46), (200, 160, 120), (90, 52, 30), (214, 69, 65)),
    ("golden", (216, 160, 74), (245, 214, 168), (178, 122, 46), (74, 144, 172)),
    ("cream", (235, 210, 168), (250, 236, 212), (204, 170, 118), (150, 96, 168)),
    ("black_tan", (48, 40, 40), (196, 148, 92), (30, 24, 24), (222, 168, 46)),
    ("reddish", (176, 78, 46), (226, 160, 120), (132, 54, 28), (74, 158, 110)),
    ("silver", (150, 150, 156), (214, 214, 218), (110, 110, 118), (214, 96, 140)),
]


def draw_dachshund(body, belly, ear, collar) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # tail (thin, curved-looking via two overlapping ellipses) — drawn first, tucked under the body
    d.ellipse([65, 175, 115, 205], fill=body)
    d.ellipse([50, 160, 90, 190], fill=body)

    # legs (short, stubby — dachshund signature), drawn before the body so the body covers their tops
    for lx in (130, 195, 285, 350):
        d.rounded_rectangle([lx, 220, lx + 30, 280], radius=12, fill=body)
        d.ellipse([lx - 3, 268, lx + 33, 292], fill=(45, 34, 30))  # paw

    # long low body, belly stripe
    d.rounded_rectangle([95, 145, 400, 245], radius=48, fill=body)
    d.rounded_rectangle([115, 195, 375, 235], radius=20, fill=belly)

    # head (round) + snout
    d.ellipse([340, 95, 455, 205], fill=body)
    d.ellipse([415, 140, 468, 178], fill=belly)  # snout
    d.ellipse([454, 152, 466, 164], fill=(35, 25, 25))  # nose

    # ears — floppy rounded ellipses hanging down either side of the head, not pointed
    d.ellipse([325, 110, 365, 195], fill=ear)
    d.ellipse([408, 90, 445, 165], fill=ear)

    # eye + blush + highlight
    d.ellipse([392, 128, 408, 144], fill=(35, 25, 25))
    d.ellipse([396, 130, 401, 135], fill=(255, 255, 255))
    d.ellipse([368, 162, 390, 178], fill=(255, 150, 160, 150))  # blush

    # collar + tag
    d.rectangle([345, 180, 398, 193], fill=collar)
    d.ellipse([362, 191, 380, 209], fill=(255, 214, 90))

    return img


def main() -> None:
    for out_dir in OUT_DIRS:
        out_dir.mkdir(parents=True, exist_ok=True)
    for name, body, belly, ear, collar in PALETTES:
        img = draw_dachshund(body, belly, ear, collar)
        for out_dir in OUT_DIRS:
            img.save(out_dir / f"{name}.png")
    print(f"Wrote {len(PALETTES)} dachshund PNGs to {len(OUT_DIRS)} locations.")


if __name__ == "__main__":
    main()
