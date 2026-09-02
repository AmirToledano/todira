"""One-off asset fetcher — NOT run at deploy/runtime. Downloads a real, public-domain cartoon
dachshund illustration and writes 6 recolored variants, replacing the earlier procedurally-drawn
PIL shapes in generate_dachshund_art.py (kept for reference/history, no longer used) after a real
request (2026-09-02) for actual internet-sourced art instead of geometric primitives.

Source: "dachshund" by Woof, https://openclipart.org/detail/194259/dachshund-by-Woof-194259 —
Creative Commons CC0 / Public Domain (the SVG's own embedded RDF metadata block declares
cc:license = http://creativecommons.org/licenses/publicdomain/, i.e. free to use, modify and
redistribute with no attribution required). Fetched via its mirror on GitHub
(cyanidecupcake/openclipart-svg, itself a full mirror of openclipart.org, MIT-licensed mirror
tooling over CC0 content) because this sandbox's egress policy only allows raw.githubusercontent.com,
not openclipart.org directly.

This sandbox could not verify a license for every other "cute dachshund mascot" SVG found on GitHub
during the same search (several had no LICENSE file at all -> all-rights-reserved by default, one
was AGPL, one was explicitly "All rights reserved / proprietary") — those were deliberately not
used. This is the only dachshund illustration found with an explicit, unambiguous open license.

Re-run manually (`python scripts/fetch_dachshund_art.py`) if the source SVG or palette needs to
change; nothing imports this module at runtime. Requires network access to raw.githubusercontent.com
(only available interactively, not from a deploy pipeline) and Playwright (rasterizes the SVG to
PNG — Telegram's sendPhoto needs a raster image, and PNG keeps this consistent with how the website
already serves these).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/cyanidecupcake/openclipart-svg/"
    "e9da54c346f38ad9b67e43efb688beb783d106f8/svg/unsorted/dachshund.svg"
)

OUT_DIRS = [
    Path(__file__).resolve().parent.parent / "common" / "dorin_common" / "assets" / "dachshunds",
    Path(__file__).resolve().parent.parent / "website" / "static" / "dachshunds",
]

# The source SVG's own 6 fill colors (confirmed via grep -o 'fill:#...' | sort | uniq -c), each
# remapped per palette while preserving their original relative light/dark roles so the fur's
# hair-stroke shading still reads correctly: b55f27 (base accent), 7e6658 (main mid-tone fur,
# dominant), d09b88 (light highlight fur, dominant), 3d5437 (dark shadow strokes + ground shadow
# ellipse), 1b0f08 (near-black outline/eye), ffffff (eye highlight, unchanged everywhere).
PALETTES: dict[str, dict[str, str]] = {
    "chocolate": {  # the source's own original coloring, kept as-is
        "b55f27": "b55f27", "7e6658": "7e6658", "d09b88": "d09b88",
        "3d5437": "3d5437", "1b0f08": "1b0f08", "ffffff": "ffffff",
    },
    "golden": {
        "b55f27": "d9932f", "7e6658": "a9855a", "d09b88": "f0d9ad",
        "3d5437": "5a4a25", "1b0f08": "241708", "ffffff": "ffffff",
    },
    "black_tan": {
        "b55f27": "5a3a1f", "7e6658": "4a3527", "d09b88": "8a6a52",
        "3d5437": "241b14", "1b0f08": "120b06", "ffffff": "ffffff",
    },
    "cream": {
        "b55f27": "d8b489", "7e6658": "c7a37e", "d09b88": "f2e4cc",
        "3d5437": "8a7256", "1b0f08": "3a2c1c", "ffffff": "ffffff",
    },
    "reddish": {
        "b55f27": "b0402a", "7e6658": "8a5240", "d09b88": "e0a892",
        "3d5437": "4a251a", "1b0f08": "200f0a", "ffffff": "ffffff",
    },
    "silver": {
        "b55f27": "8a8378", "7e6658": "69625a", "d09b88": "c9c2b8",
        "3d5437": "3a352e", "1b0f08": "161412", "ffffff": "ffffff",
    },
}

_RASTER_HTML = """<!doctype html><html><head><style>
html,body{{margin:0;background:transparent;}}
img{{display:block;width:480px;height:auto;}}
</style></head><body><img src="{svg_path}"></body></html>"""


_BACKGROUND_RECT = '<path\n      style="fill:#ffffff; stroke:none;"\n      d="M0 0L0 290L434 290L434 0L0 0z"\n  />\n  '


def fetch_source_svg(dest: Path) -> None:
    subprocess.run(["curl", "-sS", "-o", str(dest), SOURCE_URL], check=True)
    text = dest.read_text()
    assert "creativecommons.org/licenses/publicdomain" in text, "license block missing/changed"
    # The artist's own canvas has an opaque white full-page background path as its very first
    # shape (found the hard way: Playwright screenshots of this SVG kept coming back opaque white
    # despite omit_background=True + transparent CSS everywhere, until bounding-box-checking every
    # white-filled path turned up one spanning the full 0,0-434,290 canvas). Strip it so the dog
    # renders on a transparent background — it composites into the card's own gradient/color
    # instead of sitting in a white box, matching how the website/Telegram cards use these PNGs.
    assert _BACKGROUND_RECT in text, "background rect shape changed or not found"
    dest.write_text(text.replace(_BACKGROUND_RECT, ""))


def recolor(svg_text: str, mapping: dict[str, str]) -> str:
    for old, new in mapping.items():
        svg_text = re.sub(rf"(?i)#{old}\b", f"#{new}", svg_text)
    return svg_text


def rasterize(svg_path: Path, png_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    html_path = svg_path.with_suffix(".html")
    html_path.write_text(_RASTER_HTML.format(svg_path=svg_path.name))
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        page = browser.new_page(viewport={"width": 480, "height": 340})
        page.goto(f"file://{html_path}")
        # Neither Locator.screenshot() nor Page.screenshot(clip=...) preserves the alpha channel
        # here (both silently composite over white despite omit_background=True — a real Chromium
        # screenshot quirk) — only an UNCLIPPED Page.screenshot() actually keeps transparency, so
        # resize the viewport to exactly the <img>'s own rendered size instead of clipping.
        box = page.locator("img").bounding_box()
        page.set_viewport_size({"width": round(box["width"]), "height": round(box["height"])})
        page.screenshot(path=str(png_path), omit_background=True)
        browser.close()
    html_path.unlink()


def main() -> None:
    work_dir = Path(__file__).resolve().parent.parent / "scratch_dachshund_art"
    work_dir.mkdir(exist_ok=True)
    source_svg = work_dir / "source.svg"
    fetch_source_svg(source_svg)
    source_text = source_svg.read_text()

    for out_dir in OUT_DIRS:
        out_dir.mkdir(parents=True, exist_ok=True)

    for name, mapping in PALETTES.items():
        variant_svg = work_dir / f"{name}.svg"
        variant_svg.write_text(recolor(source_text, mapping))
        variant_png = work_dir / f"{name}.png"
        rasterize(variant_svg, variant_png)
        for out_dir in OUT_DIRS:
            (out_dir / f"{name}.png").write_bytes(variant_png.read_bytes())

    print(f"Wrote {len(PALETTES)} dachshund PNGs to {len(OUT_DIRS)} locations.")


if __name__ == "__main__":
    main()
