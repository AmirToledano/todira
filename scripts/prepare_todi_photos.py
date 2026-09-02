"""One-off asset processor — NOT run at deploy/runtime. Takes the curated selection of the real
Todi (the user's own dachshund) photos out of a source directory and produces the final card
assets: background/person removal for most of them (rembg, U2Net-portable model), a plain resize
for the couple where automatic removal didn't work but the original photo had no person in it
anyway (2026-09-02 request: "תוסיף את כל ה50! ... תוציא את טודי מתמונות עם אנשים ותשים אותו לבד").

Requires `pip install rembg onnxruntime` (NOT a project dependency — a one-off local tool, same
as the earlier fetch_dachshund_art.py/prepare_todi_photos.py v1) and network access to download
rembg's u2netp model on first run (~4.5MB, from its GitHub release — this sandbox's egress policy
allows it, confirmed live 2026-09-02, unlike most other domains; see PROJECT_STATE.md).

All 50 submitted photos were reviewed via a background-removed contact-sheet montage (same
technique as the v1 curation pass). Roughly half came out genuinely clean; the other half either
still showed a person after removal (a hand/arm/face touching Todi directly gets kept by a generic
foreground-detector, which doesn't know "dog yes, person no") or the removal itself failed
(ghosting/fading on complex backgrounds — cage wires, clutter, motion blur). Those are excluded
entirely rather than shipped looking broken, same quality bar as v1's curation, just applied to
the edited result instead of the raw photo.

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

MAX_DIMENSION = 900
# A little transparent margin left around the cropped-to-content bounding box so the dog doesn't
# touch the very edge of the frame.
CROP_PADDING = 14

# Cutout (background + any touching person removed) — the large majority. Order picked from the
# full 50-photo review; each one confirmed clean at full resolution, not just as a thumbnail.
CUTOUT_SOURCES = [
    "IMG_1651.jpeg",
    "IMG_1763.jpeg",
    "IMG_2300.jpeg",
    "todi_chat_01.jpg",
    "todi_chat_02.jpg",
    "todi_chat_03.jpg",
    "todi_chat_04.jpg",
    "todi_chat_05.jpg",
    "todi_chat_07.jpg",
    "todi_chat_08.jpg",
    "todi_chat_09.jpg",
    "todi_chat_12.jpg",
    "todi_chat_13.jpg",
    "todi_chat_15.jpg",
    "todi_chat_18.jpg",
    "todi_chat_19.jpg",
    "todi_chat_22.jpg",
    "todi_chat_26.jpg",
    "todi_chat_28.jpg",
    "todi_chat_29.jpg",
    "todi_chat_32.jpg",
    "todi_chat_34.jpg",
    "todi_chat_35.jpg",
    "todi_chat_37.jpg",
    "todi_chat_40.jpg",
]

# Plain resize, no cutout — the original photo already had no person in it, but the automatic
# background removal itself produced visible artifacts on these two (a patterned bed/blanket
# confused the foreground detector), so the real photo is used as-is instead of a broken edit.
PLAIN_SOURCES = [
    "A4CF2458-4992-40B5-B3D6-38411F375F34.jpeg",
    "todi_chat_36.jpg",
]


def _load_fixed(name: str) -> Image.Image:
    img = Image.open(SOURCE_DIR / name)
    return ImageOps.exif_transpose(img)  # fixes sideways/upside-down phone photos


def _crop_to_content(img: Image.Image) -> Image.Image:
    """Trims transparent margin down to the subject's own bounding box (+ padding) — several
    source photos had Todi small in a large empty frame, which would otherwise render tiny inside
    the card's bounded display box (see website/static/style.css's .no-image-dachshund img)."""
    # Threshold the alpha channel before computing the box - rembg leaves a soft, spread-out
    # low-confidence "ghost" fringe around several of these photos' subjects (motion blur/complex
    # backgrounds the model was unsure about), and getbbox() on the raw alpha treats ANY alpha > 0
    # as content, so that faint halo alone was enough to keep the crop nearly full-canvas-sized,
    # leaving Todi tiny in the middle. Cropping to only the CONFIDENT region (alpha > 50) fixes
    # that; the soft edge immediately around Todi himself (which IS wanted, for a clean cutout
    # look) still comes along since it's well inside that tighter box.
    mask = img.getchannel("A").point(lambda a: 255 if a > 50 else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return img
    left, top, right, bottom = bbox
    left = max(0, left - CROP_PADDING)
    top = max(0, top - CROP_PADDING)
    right = min(img.width, right + CROP_PADDING)
    bottom = min(img.height, bottom + CROP_PADDING)
    return img.crop((left, top, right, bottom))


def _save(img: Image.Image, dest_name: str) -> None:
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
    for out_dir in OUT_DIRS:
        out_dir.mkdir(parents=True, exist_ok=True)
        img.save(out_dir / dest_name, "PNG", optimize=True)


def main() -> None:
    from rembg import new_session, remove

    session = new_session("u2netp")
    n = 0

    for filename in CUTOUT_SOURCES:
        n += 1
        img = _load_fixed(filename)
        cutout = remove(img, session=session)
        cutout = _crop_to_content(cutout)
        _save(cutout, f"todi_{n:02d}.png")
        print(f"[cutout] {filename} -> todi_{n:02d}.png")

    for filename in PLAIN_SOURCES:
        n += 1
        img = _load_fixed(filename).convert("RGBA")
        _save(img, f"todi_{n:02d}.png")
        print(f"[plain]  {filename} -> todi_{n:02d}.png")

    print(f"Wrote {n} Todi photos to {len(OUT_DIRS)} locations.")


if __name__ == "__main__":
    main()
