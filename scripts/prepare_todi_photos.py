"""One-off asset processor — NOT run at deploy/runtime. Takes all 50 original, UNEDITED photos of
Todi (the user's own dachshund) and produces the card assets for the "no real photos" listing
placeholder: the original photo as-is (no background removal, no cropping, no cutout — 2026-09-02
request: "תשתמש בכל ה50 תמונות המקוריות שהגיעו אליך! בלי לשנות רקעים בלי להסתיר שום דבר"), except
where a human face is visible in the frame, which gets a big 😎 emoji sticker over it so the
listing placeholder never shows an identifiable person.

This replaces the two earlier approaches (see PROJECT_STATE.md for that history): a CC0 cartoon
dog illustration, then real photos with the background/any touching person removed via rembg and
YOLOv8-seg. Those both edited the photo itself (crop, cutout, background removal); this version
doesn't touch anything except stamping an emoji over a face when one is present — the direct,
explicit ask being "don't change backgrounds, don't hide anything [else]."

All 50 photos were reviewed by hand (not an automatic face detector — see below for why) at a
large-enough size to spot a face; exactly 5 had a visible human face. The other person-adjacent
photos in the set (a hand, an arm, a torso, hair, a shoulder — no actual face) are shipped
untouched, since only a *face* triggers the emoji, per the request.

Why not an automatic face detector: `cv2.FaceDetectorYN` (YuNet, downloaded from the opencv_zoo
GitHub repo — its raw file is a git-lfs pointer, but `media.githubusercontent.com/media/...` in
place of `raw.githubusercontent.com` resolves the real binary, reachable through this sandbox's
egress policy) was tried across all 4 90-degree rotations (several of these phone photos have the
subject sideways/upside-down within an already EXIF-upright frame, not just a wrong EXIF tag) with
non-max-suppression across rotations to dedupe. At a strict threshold it returned zero detections
across all 50 photos; at a permissive one it returned dozens of false positives per photo (the
dog's spotted coat pattern reads as face-like texture to the model). Neither setting was usable
unsupervised, so the 50-photo review was done directly instead — same as every other curation pass
in this project's Todi-photo history.

Face coordinates below were hand-measured on the EXIF-TRANSPOSED image (`ImageOps.exif_transpose`
output), not the raw file — a real bug hit while building this: viewing the raw file directly
shows it BEFORE EXIF rotation is applied, so eyeballing coordinates from that view and pasting onto
the transposed image put the emoji in the wrong place entirely for any photo with a 90/270-degree
EXIF orientation tag (confirmed via `img.getexif().get(274)` — tag 6 or 5 on 3 of the 5 face
photos here). Coordinates were re-measured directly against saved `exif_transpose` output before
finalizing.

Re-run manually (`python scripts/prepare_todi_photos.py`) only if the curated selection or face
coordinates change; nothing imports this module at runtime.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

SOURCE_DIR = Path(__file__).resolve().parent.parent.parent / "todi-photos-raw-src"

OUT_DIRS = [
    Path(__file__).resolve().parent.parent / "common" / "dorin_common" / "assets" / "dachshunds",
    Path(__file__).resolve().parent.parent / "website" / "static" / "dachshunds",
]

MAX_DIMENSION = 1000
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

# All 50 submitted photos, in the order they get numbered todi_01..todi_50. Order doesn't matter
# functionally (selection is `listing_id % count`) - kept as originally received for traceability.
ALL_SOURCES = [
    "IMG_1651.jpeg", "IMG_1763.jpeg", "IMG_2300.jpeg", "IMG_1638.jpeg", "IMG_1758.jpeg",
    "IMG_1886.jpeg", "IMG_2057.jpeg", "IMG_2097.jpeg", "IMG_2296.jpeg",
    "A4CF2458-4992-40B5-B3D6-38411F375F34.jpeg",
    "todi_chat_01.jpg", "todi_chat_02.jpg", "todi_chat_03.jpg", "todi_chat_04.jpg",
    "todi_chat_05.jpg", "todi_chat_06.jpg", "todi_chat_07.jpg", "todi_chat_08.jpg",
    "todi_chat_09.jpg", "todi_chat_10.jpg", "todi_chat_11.jpg", "todi_chat_12.jpg",
    "todi_chat_13.jpg", "todi_chat_14.jpg", "todi_chat_15.jpg", "todi_chat_16.jpg",
    "todi_chat_17.jpg", "todi_chat_18.jpg", "todi_chat_19.jpg", "todi_chat_20.jpg",
    "todi_chat_21.jpg", "todi_chat_22.jpg", "todi_chat_23.jpg", "todi_chat_24.jpg",
    "todi_chat_25.jpg", "todi_chat_26.jpg", "todi_chat_27.jpg", "todi_chat_28.jpg",
    "todi_chat_29.jpg", "todi_chat_30.jpg", "todi_chat_31.jpg", "todi_chat_32.jpg",
    "todi_chat_33.jpg", "todi_chat_34.jpg", "todi_chat_35.jpg", "todi_chat_36.jpg",
    "todi_chat_37.jpg", "todi_chat_38.jpg", "todi_chat_39.jpg", "todi_chat_40.jpg",
]
assert len(ALL_SOURCES) == 50

# filename -> (center_x, center_y, size) of the 😎 sticker, in pixels of the EXIF-TRANSPOSED
# image (see module docstring). Only these 5 of the 50 had a visible human face.
FACE_STICKERS: dict[str, tuple[int, int, int]] = {
    "todi_chat_11.jpg": (280, 440, 800),
    "todi_chat_17.jpg": (1650, 1950, 1100),
    "todi_chat_25.jpg": (1880, 2050, 1300),
    "todi_chat_33.jpg": (250, 260, 650),
    "todi_chat_39.jpg": (300, 1050, 1050),
}


def _render_emoji(size: int) -> Image.Image:
    # NotoColorEmoji is a fixed bitmap-strike font (109px native); render at native size and
    # upscale with LANCZOS rather than asking the font for `size` directly (color bitmap fonts
    # generally only render at their one native strike size).
    native = 109
    font = ImageFont.truetype(EMOJI_FONT, native)
    tmp = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tmp)
    draw.text((10, 10), "😎", font=font, embedded_color=True)
    tmp = tmp.crop(tmp.getbbox())
    return tmp.resize((size, size), Image.LANCZOS)


def _save(img: Image.Image, dest_name: str) -> None:
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
    for out_dir in OUT_DIRS:
        out_dir.mkdir(parents=True, exist_ok=True)
        img.convert("RGB").save(out_dir / dest_name, "JPEG", quality=88, optimize=True)


def main() -> None:
    for n, filename in enumerate(ALL_SOURCES, start=1):
        img = Image.open(SOURCE_DIR / filename)
        img = ImageOps.exif_transpose(img).convert("RGBA")

        sticker = FACE_STICKERS.get(filename)
        if sticker is not None:
            cx, cy, size = sticker
            emoji = _render_emoji(size)
            img.alpha_composite(emoji, (cx - size // 2, cy - size // 2))

        dest = f"todi_{n:02d}.jpg"
        _save(img, dest)
        tag = "emoji" if sticker else "as-is"
        print(f"[{tag}] {filename} -> {dest}")

    print(f"Wrote {len(ALL_SOURCES)} Todi photos to {len(OUT_DIRS)} locations.")


if __name__ == "__main__":
    main()
