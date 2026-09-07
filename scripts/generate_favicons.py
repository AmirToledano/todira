"""One-off asset generator — NOT run at deploy/runtime, only when the favicon needs regenerating.

**Round 3, same day (2026-09-07)** — the actual final design, replacing both earlier approaches:
1. A tight photographic crop of Todi's crown+face (from `todira-brand.webp`) — looked fine as a
   plain square favicon, but read as "a square photo forced into a circle" against Chrome's New
   Tab shortcuts tile, which clips favicons into a circle.
2. The same crop with its background removed (`rembg`) — fixed the circle-clipping mismatch, but
   the owner's own side-by-side screenshot against GitHub's tab favicon showed the real remaining
   problem: a detailed, photographic, brown-toned dog face simply doesn't hold up at 16x16/32x32
   the way a bold, high-contrast graphic mark (GitHub's Octocat silhouette, Drive's colored
   triangle) does — fine detail and soft photo edges disappear or blur into mush at that scale,
   which is exactly what a real favicon has to survive most of the time.

**The fix**: stop using a photograph at all. This script now draws a genuinely simple, flat
GEOMETRIC crown icon from scratch (three bold triangular points + a band, in the site's own brand
gold `--gold`/`--gold-light` on a solid `--teal` circle) — the same crown-as-icon idea the brand
already leans on everywhere else (👑 in the bot's own branding), just rendered as clean vector
shapes instead of extracted from a real photo. Vector shapes with strong color contrast survive
downsampling to 16x16 the way fine photographic detail never can — rendered at 1024x1024 and
downsampled with LANCZOS, verified legible at both 16x16 and 32x32 (crown shape clearly readable
at both) before shipping.

Two output shapes, for two different real constraints:
- The regular favicon/manifest icons keep the crown on a transparent-cornered CIRCLE — this reads
  correctly however different contexts mask it (Chrome's circular shortcuts tile, a square browser
  tab, Android's own adaptive-icon masking).
- `apple-touch-icon.png` fills the ENTIRE square with solid teal (no transparency, no pre-baked
  circle) — iOS applies its own rounded-square mask and is known to render a transparent
  apple-touch-icon with an ugly solid-black fill, so this one deliberately doesn't pre-mask itself
  at all and just trusts iOS's own masking, per Apple's own documented convention for this file.

Requires only Pillow (`pip install pillow`) — no photo processing, no rembg/onnxruntime needed
for this version.
"""

from pathlib import Path

from PIL import Image, ImageDraw

STATIC_DIR = Path(__file__).resolve().parent.parent / "website" / "static"

TEAL = (14, 138, 130, 255)  # --teal
GOLD = (217, 164, 65, 255)  # --gold
GOLD_LIGHT = (236, 201, 120, 255)  # --gold-light

MASTER_SIZE = 1024
TRANSPARENT_PNG_SIZES = {
    "favicon-16x16.png": 16,
    "favicon-32x32.png": 32,
    "android-chrome-192x192.png": 192,
    "android-chrome-512x512.png": 512,
}
ICO_SIZES = [(16, 16), (32, 32), (48, 48)]
APPLE_TOUCH_ICON_SIZE = 180


def _draw_crown(size: int, *, circular_bg: bool) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if circular_bg:
        d.ellipse((0, 0, size, size), fill=TEAL)
    else:
        d.rectangle((0, 0, size, size), fill=TEAL)

    s = size
    band_top, band_bottom = s * 0.58, s * 0.72
    band_left, band_right = s * 0.20, s * 0.80
    d.rectangle([band_left, band_top, band_right, band_bottom], fill=GOLD)

    points_base_y = band_top + 1
    tip_y, mid_tip_y = s * 0.22, s * 0.12  # center point taller than the two side points
    d.polygon([(band_left, points_base_y), (s * 0.34, points_base_y), (s * 0.27, tip_y)], fill=GOLD)
    d.polygon([(s * 0.40, points_base_y), (s * 0.60, points_base_y), (s * 0.50, mid_tip_y)], fill=GOLD)
    d.polygon([(s * 0.66, points_base_y), (band_right, points_base_y), (s * 0.73, tip_y)], fill=GOLD)

    jewel_r = s * 0.045
    for jx, jy in [(s * 0.27, tip_y), (s * 0.50, mid_tip_y), (s * 0.73, tip_y)]:
        d.ellipse((jx - jewel_r, jy - jewel_r, jx + jewel_r, jy + jewel_r), fill=GOLD_LIGHT)

    d.rectangle([band_left, band_top, band_right, band_top + (band_bottom - band_top) * 0.25], fill=GOLD_LIGHT)
    return im


def main() -> None:
    circular_master = _draw_crown(MASTER_SIZE, circular_bg=True)
    for name, target_size in TRANSPARENT_PNG_SIZES.items():
        circular_master.resize((target_size, target_size), Image.LANCZOS).save(STATIC_DIR / name)
    circular_master.save(STATIC_DIR / "favicon.ico", sizes=ICO_SIZES)

    square_master = _draw_crown(MASTER_SIZE, circular_bg=False).convert("RGB")  # opaque for iOS
    square_master.resize((APPLE_TOUCH_ICON_SIZE, APPLE_TOUCH_ICON_SIZE), Image.LANCZOS).save(
        STATIC_DIR / "apple-touch-icon.png"
    )

    print(f"Wrote favicon.ico + {len(TRANSPARENT_PNG_SIZES) + 1} PNG variants to {STATIC_DIR}")


if __name__ == "__main__":
    main()
