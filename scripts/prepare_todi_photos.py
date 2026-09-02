"""One-off asset processor — NOT run at deploy/runtime. Takes the curated selection of the real
Todi (the user's own dachshund) photos out of a source directory, fixes phone-camera EXIF
rotation (a real bug caught while reviewing these — several came out sideways without this),
resizes/compresses them for web+Telegram use, and writes them to both asset locations, replacing
the earlier CC0-illustration placeholder (2026-09-02 request — the user has since sent 50 real
photos of their own dog and asked for those instead).

No cropping: object-fit is deliberately "no crop, scale to fit" both on the website (.no-image-
dachshund img uses width:70%/height:auto, not background-size:cover) and in Telegram's own photo
rendering, so a tall portrait phone photo just shows in full rather than risking cutting Todi out
of frame — safer than guessing a per-photo crop box for 17 different photos.

Re-run manually (`python scripts/prepare_todi_photos.py`) only if the curated selection changes;
nothing imports this module at runtime.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

SOURCE_DIR = Path(__file__).resolve().parent.parent.parent / "todi-photos-raw-src"

OUT_DIRS = [
    Path(__file__).resolve().parent.parent / "common" / "dorin_common" / "assets" / "dachshunds",
    Path(__file__).resolve().parent.parent / "website" / "static" / "dachshunds",
]

# Curated from all 50 submitted photos (dog clearly the main subject, no visible human faces,
# reasonably sharp/lit, good variety of poses/settings) - see PROJECT_STATE.md for the full
# curation note.
SELECTED = [
    "IMG_1651.jpeg",
    "IMG_2057.jpeg",
    "todi_chat_03.jpg",
    "todi_chat_04.jpg",
    "todi_chat_05.jpg",
    "todi_chat_08.jpg",
    "todi_chat_09.jpg",
    "todi_chat_13.jpg",
    "todi_chat_15.jpg",
    "todi_chat_19.jpg",
    "todi_chat_22.jpg",
    "todi_chat_26.jpg",
    "todi_chat_28.jpg",
    "todi_chat_29.jpg",
    "todi_chat_32.jpg",
    "todi_chat_35.jpg",
    "todi_chat_36.jpg",
]

MAX_DIMENSION = 1200


def process(src: Path, dest_name: str) -> None:
    img = Image.open(src)
    img = ImageOps.exif_transpose(img)  # fixes sideways/upside-down phone photos
    img = img.convert("RGB")
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
    for out_dir in OUT_DIRS:
        out_dir.mkdir(parents=True, exist_ok=True)
        img.save(out_dir / dest_name, "JPEG", quality=82, optimize=True)


def main() -> None:
    for i, filename in enumerate(SELECTED, start=1):
        src = SOURCE_DIR / filename
        dest_name = f"todi_{i:02d}.jpg"
        process(src, dest_name)
        print(f"{filename} -> {dest_name}")
    print(f"Wrote {len(SELECTED)} Todi photos to {len(OUT_DIRS)} locations.")


if __name__ == "__main__":
    main()
