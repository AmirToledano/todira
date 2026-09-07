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

Requires Pillow (`pip install pillow`) — not a project dependency, only needed to run this script.
"""

from pathlib import Path

from PIL import Image

STATIC_DIR = Path(__file__).resolve().parent.parent / "website" / "static"
SOURCE = STATIC_DIR / "todira-brand.webp"

# name -> pixel size (square)
PNG_SIZES = {
    "favicon-16x16.png": 16,
    "favicon-32x32.png": 32,
    "apple-touch-icon.png": 180,
    "android-chrome-192x192.png": 192,
    "android-chrome-512x512.png": 512,
}
ICO_SIZES = [(16, 16), (32, 32), (48, 48)]


def main() -> None:
    im = Image.open(SOURCE)
    width, _height = im.size
    # Top square crop (full width) — crown + face + top of cape, no horizontal cropping needed
    # since the dog is already centered in the source frame.
    crop = im.crop((0, 0, width, width)).convert("RGB")

    for name, size in PNG_SIZES.items():
        crop.resize((size, size), Image.LANCZOS).save(STATIC_DIR / name)

    crop.save(STATIC_DIR / "favicon.ico", sizes=ICO_SIZES)
    print(f"Wrote favicon.ico + {len(PNG_SIZES)} PNG variants to {STATIC_DIR}")


if __name__ == "__main__":
    main()
