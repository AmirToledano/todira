"""One-off asset generator — NOT run at deploy/runtime, only when the favicon needs regenerating
(e.g. `todira-brand.webp` itself is replaced with a new version some day).

Generates `website/static/favicon.ico` + the PNG variants referenced in `base.html`'s <head>
(2026-09-07 — before this, browsers fell back to a generic auto-generated letter tile, a plain
"T", since no favicon existed at all) from the existing brand image
(`website/static/todira-brand.webp`, 1184x1895 as of this writing).

Same crop logic already proven on the Telegram bot's own avatar (see PROJECT_STATE.md's
2026-08-29 branding entry): a tight square crop of the top of the image — crown, face, and the
top of the cape — reads clearly even at 16x16, unlike the full tall poster (crown+dog+cape+
caption text), which a small square icon can't show legibly all at once.

**Round 2, same day**: the first version kept the source photo's opaque beige studio background
filling the whole square. That looked fine in an ordinary square favicon slot, but Chrome's New
Tab "shortcuts" tiles clip favicons into a CIRCLE — against that circular mask, an opaque square
background reads as "a square photo stuffed into a circle" (visibly mismatched corners), unlike
the transparent-background logo marks other sites use there. Fixed by running the same square
crop through `rembg` (background removal, u2net/bria model — same tool already used earlier in
this project's own Todi-photo curation history) to strip the beige background entirely, leaving
just the dog+crown+cape on a transparent background. Verified by compositing the result onto both
a simulated circular Chrome tile and plain light/dark backgrounds at 16x16/32x32 before shipping —
reads cleanly in all of them, since a transparent PNG naturally blends into whatever container
clips or colors it, rather than fighting it with its own background color.

`apple-touch-icon.png` is the one exception, saved with an OPAQUE background (flattened onto the
same beige tone as the original photo's own backdrop) rather than transparent: iOS has a
long-standing quirk of filling a transparent apple-touch-icon with solid BLACK on the home screen
instead of compositing it nicely, so a flattened, intentional-looking background is safer there
than transparency.

Requires Pillow + rembg (`pip install pillow rembg onnxruntime`) — not project dependencies, only
needed to run this script. rembg's model (~1GB) downloads on first use.
"""

from pathlib import Path

from PIL import Image
from rembg import remove

STATIC_DIR = Path(__file__).resolve().parent.parent / "website" / "static"
SOURCE = STATIC_DIR / "todira-brand.webp"

# Background color to flatten the (iOS-only) opaque apple-touch-icon onto — matches the original
# photo's own beige studio backdrop, so it still reads as intentional, not a black square.
APPLE_TOUCH_ICON_BG = (230, 219, 201)

# name -> pixel size (square), transparent background
TRANSPARENT_PNG_SIZES = {
    "favicon-16x16.png": 16,
    "favicon-32x32.png": 32,
    "android-chrome-192x192.png": 192,
    "android-chrome-512x512.png": 512,
}
ICO_SIZES = [(16, 16), (32, 32), (48, 48)]
APPLE_TOUCH_ICON_SIZE = 180


def main() -> None:
    im = Image.open(SOURCE)
    width, _height = im.size
    # Top square crop (full width) — crown + face + top of cape, no horizontal cropping needed
    # since the dog is already centered in the source frame.
    square = im.crop((0, 0, width, width))
    cutout = remove(square).convert("RGBA")  # background removed, transparent

    for name, size in TRANSPARENT_PNG_SIZES.items():
        cutout.resize((size, size), Image.LANCZOS).save(STATIC_DIR / name)

    cutout.save(STATIC_DIR / "favicon.ico", sizes=ICO_SIZES)

    apple_bg = Image.new("RGB", cutout.size, APPLE_TOUCH_ICON_BG)
    apple_bg.paste(cutout, (0, 0), cutout)
    apple_bg.resize((APPLE_TOUCH_ICON_SIZE, APPLE_TOUCH_ICON_SIZE), Image.LANCZOS).save(
        STATIC_DIR / "apple-touch-icon.png"
    )

    print(f"Wrote favicon.ico + {len(TRANSPARENT_PNG_SIZES) + 1} PNG variants to {STATIC_DIR}")


if __name__ == "__main__":
    main()
