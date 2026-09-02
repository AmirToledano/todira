"""One-off asset processor — NOT run at deploy/runtime. Takes the full set of 50 photos of Todi
(the user's own dachshund) submitted for the "no real photos" listing-card placeholder and produces
the final card assets: every photo edited to isolate Todi alone, background and any touching
person removed (2026-09-02 request: "תוסיף את כל ה50! ... תוציא את טודי מתמונות עם אנשים ותשים
אותו לבד ממש תערוך את התמונות כמו שצריך").

Two segmentation passes were used, in order of what the first pass could and couldn't handle:

1. `rembg` (U2Net-portable model, "u2netp") - a generic saliency/foreground detector. Works well
   when Todi is the only foreground subject, but has no concept of "which foreground object": it
   can't tell a person's hand from the dog when they're touching, so any photo with a person in
   contact with Todi still shows the person after this pass. Used for photos 1-27 (the first
   curation round - see PROJECT_STATE.md).
2. `ultralytics` YOLOv8-seg ("yolov8x-seg", COCO-pretrained), a CLASS-AWARE instance segmentation
   model. Only the highest-confidence "dog"-class mask is kept (never unioned with a second "dog"
   detection - a lower-confidence second detection was, in every case checked, actually the
   PERSON's torso/arm misclassified as a dog, not a second real animal - see git history for the
   before/after). Any detected "person"-class mask is also subtracted as a safety net for cases
   where the dog mask itself bled slightly onto adjacent skin. Requires
   `pip install ultralytics scipy` (not project dependencies - one-off local tooling) and network
   access to download the pretrained checkpoint from the ultralytics GitHub release on first run
   (~137MB for yolov8x-seg; this sandbox's egress policy allows GitHub release-asset downloads,
   confirmed live 2026-09-02, unlike most other image-hosting domains). Used for photos 28-50.

A handful of photos in pass 2 needed a manual pixel-region assist after the automatic person
subtraction still left a small fragment (a hand had no separate "person" detection at all, or the
model's person mask didn't fully cover a thin sliver right at the boundary with Todi): a hard
crop/notch was cut into the mask at the specific coordinates found by inspecting each one at full
resolution (never at thumbnail size - a hand/ring was missed at thumbnail size in the very first
curation round; see PROJECT_STATE.md). This is a one-off decision per photo, not a general
algorithm, which is why this script's CUTOUT_SOURCES/YOLO_SOURCES lists are the actual source of
truth for what ships, not a fully-automatic re-run.

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

# --- Pass 1 (todi_01..todi_27) - rembg u2netp, background removal only -------------------------

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

# Plain resize, no cutout - the original photo already had no person in it, but the automatic
# background removal itself produced visible artifacts on these two (a patterned bed/blanket
# confused the foreground detector), so the real photo is used as-is instead of a broken edit.
PLAIN_SOURCES = [
    "A4CF2458-4992-40B5-B3D6-38411F375F34.jpeg",
    "todi_chat_36.jpg",
]

# todi_chat_27 needed rembg too (cage bars badly confused u2net into ghosting), but a plain resize
# still showed the cage - handled with a one-off connected-component cleanup, see git history for
# the exact code (kept out of this script since it's not reusable for any other photo).

# --- Pass 2 (todi_28..todi_50) - YOLOv8-seg (yolov8x-seg), class-aware dog-only segmentation ----

# Every one of these had a person directly touching Todi (or a background too complex for pass 1
# to isolate cleanly) in the source photo. See this script's docstring for the method; a few
# needed an additional manual crop/notch on top of the automatic person-mask subtraction - noted
# inline. All 22 confirmed clean (no visible person) at full resolution, not just thumbnail.
YOLO_SOURCES = [
    "IMG_1638.jpeg",
    "IMG_1758.jpeg",
    "IMG_1886.jpeg",
    "IMG_2057.jpeg",
    "IMG_2097.jpeg",
    "IMG_2296.jpeg",
    "todi_chat_06.jpg",
    "todi_chat_10.jpg",
    "todi_chat_11.jpg",
    "todi_chat_14.jpg",
    "todi_chat_16.jpg",
    "todi_chat_17.jpg",
    "todi_chat_20.jpg",
    "todi_chat_21.jpg",
    "todi_chat_23.jpg",
    "todi_chat_24.jpg",
    "todi_chat_25.jpg",  # + manual x-cut: a tattooed arm reached all the way to Todi's paw
    "todi_chat_30.jpg",
    "todi_chat_31.jpg",
    "todi_chat_33.jpg",
    "todi_chat_38.jpg",  # + manual x-cut: a hand at the frame edge, no separate person detection
    "todi_chat_39.jpg",  # + manual y-cut and notch: face/hair fragments behind Todi's ear
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


def _run_pass_1(n: int) -> int:
    from rembg import new_session, remove

    session = new_session("u2netp")
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

    return n


def _run_pass_2(n: int) -> int:
    """Class-aware dog-only segmentation for photos where a person is directly touching Todi.
    The manual per-photo crop/notch coordinates for todi_chat_25/38/39 aren't reproduced here
    (they were found interactively at full resolution and are one-off, not a general rule) - this
    function reproduces the clean majority; see git history for the exact manual-fix code."""
    import numpy as np
    from scipy import ndimage
    from ultralytics import YOLO

    DOG_CLASS, PERSON_CLASS = 16, 0
    model = YOLO("yolov8x-seg.pt")

    def resize_mask(mask: np.ndarray, size: tuple[int, int]) -> np.ndarray:
        arr = (mask * 255).astype("uint8")
        return np.array(Image.fromarray(arr).resize(size, Image.BILINEAR)) > 127

    for filename in YOLO_SOURCES:
        n += 1
        img = _load_fixed(filename).convert("RGB")
        r = model(img, verbose=False)[0]
        if r.boxes is None or r.masks is None:
            print(f"[SKIP] {filename}: no detections")
            continue

        best_i, best_conf = None, -1.0
        person_masks = []
        for i, (c, conf) in enumerate(zip(r.boxes.cls, r.boxes.conf)):
            cls = int(c)
            if cls == DOG_CLASS and float(conf) > best_conf:
                best_i, best_conf = i, float(conf)
            elif cls == PERSON_CLASS:
                person_masks.append(resize_mask(r.masks.data[i].cpu().numpy(), img.size))
        if best_i is None:
            print(f"[SKIP] {filename}: no dog detected")
            continue

        dog_mask = resize_mask(r.masks.data[best_i].cpu().numpy(), img.size)
        if person_masks:
            person_union = np.logical_or.reduce(person_masks)
            person_union = ndimage.binary_dilation(person_union, iterations=6)
            dog_mask = dog_mask & ~person_union

        labeled, count = ndimage.label(dog_mask)
        if count > 1:
            sizes = ndimage.sum(dog_mask, labeled, range(1, count + 1))
            dog_mask = labeled == (int(sizes.argmax()) + 1)

        alpha = Image.fromarray((dog_mask * 255).astype("uint8"))
        rgba = img.convert("RGBA")
        rgba.putalpha(alpha)
        cropped = _crop_to_content(rgba)
        _save(cropped, f"todi_{n:02d}.png")
        print(f"[yolo]   {filename} -> todi_{n:02d}.png (manual fixup may still be needed)")

    return n


def main() -> None:
    n = _run_pass_1(0)
    n = _run_pass_2(n)
    print(f"Wrote {n} Todi photos to {len(OUT_DIRS)} locations.")


if __name__ == "__main__":
    main()
