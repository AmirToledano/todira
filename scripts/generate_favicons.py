"""One-off asset generator — NOT run at deploy/runtime, only when the favicon needs regenerating.

**Round 4, same day (2026-09-07) — back to the real photo, done properly this time.** The full
history, so nobody re-litigates it from scratch:
1. A loose photographic crop (crown+face+cape) with the source photo's own opaque beige
   background — looked fine as a plain square favicon, but read as "a square photo forced into a
   circle" against Chrome's New Tab shortcuts tile, which clips favicons into a circle.
2. Same crop, background removed (rembg) — fixed the circle-clipping mismatch, but the owner's own
   side-by-side screenshot against GitHub's tab favicon showed a real remaining problem: the crop
   was too LOOSE (lots of ear/cape/dead space diluting the subject) and too soft after a plain
   LANCZOS downsample — fine photographic detail and low local contrast just doesn't survive
   getting shrunk to 16-32px the way a bold graphic mark does.
3. A simplified flat geometric crown icon (no photo at all) — legible at every size, but the owner
   flatly didn't like the result ("הכתר לא משהו בכלל") and asked to go back to the real photo,
   just made to actually look good this time — not defaulting to a generic icon because the photo
   is hard to get right.
4. **This version**: same idea as round 2 (photo, background removed) but with three real fixes,
   not just a redo:
   - **Tighter crop** — crown-to-collar only, cropped in from the SIDES too (not just top/bottom),
     so the ears touch the frame edges and there's no dead background space diluting the subject
     at small size. Confirmed by simulating both a plain square favicon and a circular Chrome tile
     with this crop before committing to it — the crown no longer gets crowded/cut and the ears
     fill the circle's sides naturally instead of floating in empty space.
   - **Contrast + saturation boost** (`ImageEnhance`, +15% contrast / +25% saturation) — real
     photographic tonal transitions are subtle by design (a professional pet-photography shoot),
     which reads as ideal at full size but turns to indistinct mush once shrunk to 16px; boosting
     both before downsampling gives the resize algorithm more separated tones to preserve.
   - **Unsharp-mask sharpening AFTER each resize**, not before — LANCZOS downsampling has a
     softening effect on its own that boosting the source alone doesn't fix; sharpening applied at
     the FINAL small size (not the large source) is what actually recovers crisp edges at 16x16/
     32x32. Verified by comparing sharpened vs. unsharpened 16px/32px output side by side on both
     light and dark backgrounds before shipping — the sharpened version reads noticeably clearer
     in both.

`apple-touch-icon.png` again gets its own opaque-background treatment (flattened onto the same
beige as the original photo's own backdrop) rather than transparency, since iOS is known to render
a transparent apple-touch-icon with an ugly solid-black fill on the home screen instead of
compositing it properly.

Requires Pillow + rembg (`pip install pillow rembg onnxruntime`) — not project dependencies, only
needed to run this script. rembg's model (~1GB) downloads on first use.
"""

from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter
from rembg import remove

STATIC_DIR = Path(__file__).resolve().parent.parent / "website" / "static"
SOURCE = STATIC_DIR / "todira-brand.webp"

# Tight crop box (left, top, right, bottom) on the 1184x1895 source — crown through collar, in
# from the sides too so the ears touch the frame edges (see the module docstring's "Tighter crop"
# note for why this matters at small favicon sizes).
CROP_BOX = (100, 0, 1100, 1000)

CONTRAST_FACTOR = 1.15
SATURATION_FACTOR = 1.25

# Background color to flatten the (iOS-only) opaque apple-touch-icon onto — matches the original
# photo's own beige studio backdrop, so it still reads as intentional, not a black square.
APPLE_TOUCH_ICON_BG = (230, 219, 201)

TRANSPARENT_PNG_SIZES = {
    "favicon-16x16.png": 16,
    "favicon-32x32.png": 32,
    "android-chrome-192x192.png": 192,
    "android-chrome-512x512.png": 512,
}
ICO_SIZES = [(16, 16), (32, 32), (48, 48)]
APPLE_TOUCH_ICON_SIZE = 180


def _boosted_cutout() -> Image.Image:
    im = Image.open(SOURCE)
    crop = im.crop(CROP_BOX)
    cutout = remove(crop).convert("RGBA")

    rgb = ImageEnhance.Contrast(cutout.convert("RGB")).enhance(CONTRAST_FACTOR)
    rgb = ImageEnhance.Color(rgb).enhance(SATURATION_FACTOR)
    r, g, b = rgb.split()
    _, _, _, a = cutout.split()
    return Image.merge("RGBA", (r, g, b, a))


def _resize_sharp(im: Image.Image, size: int) -> Image.Image:
    # Sharpen AFTER resizing — this is what actually recovers crispness at the final small size,
    # not sharpening the large source beforehand (LANCZOS's own softening happens during the
    # resize itself, so there's nothing yet to sharpen until after it).
    small = im.resize((size, size), Image.LANCZOS)
    return small.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=2))


def main() -> None:
    cutout = _boosted_cutout()

    for name, size in TRANSPARENT_PNG_SIZES.items():
        _resize_sharp(cutout, size).save(STATIC_DIR / name)

    # ICO container: Pillow's multi-size .ico writer only downsamples FROM the single image
    # passed to .save() — it can't upscale a smaller frame to fill a larger requested size (an
    # earlier version of this script tried passing separately-sharpened per-size frames via
    # append_images and silently ended up with only one usable size in the file, caught by
    # actually loading each size back out and checking before shipping). Feed it our largest ICO
    # size (already sharpened) and let it derive the smaller ones itself.
    ico_source = _resize_sharp(cutout, max(s for s, _ in ICO_SIZES))
    ico_source.save(STATIC_DIR / "favicon.ico", sizes=ICO_SIZES)

    apple_bg = Image.new("RGB", cutout.size, APPLE_TOUCH_ICON_BG)
    apple_bg.paste(cutout, (0, 0), cutout)
    apple_icon = apple_bg.resize((APPLE_TOUCH_ICON_SIZE, APPLE_TOUCH_ICON_SIZE), Image.LANCZOS)
    apple_icon = apple_icon.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=2))
    apple_icon.save(STATIC_DIR / "apple-touch-icon.png")

    print(f"Wrote favicon.ico + {len(TRANSPARENT_PNG_SIZES) + 1} PNG variants to {STATIC_DIR}")


if __name__ == "__main__":
    main()
