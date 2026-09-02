"""One-off asset generator — NOT run at deploy/runtime. Renders the Todi mascot SVG (a small
flat-vector illustration of a crowned dachshund — matches the bot's own "טודירה 👑" royal branding)
to the PNG used as the Telegram/WhatsApp fallback photo for a listing with zero real photos.

Replaces prepare_todi_photos.py and every approach it documented (2026-09-02, same day): a CC0
cartoon illustration, real photos with background/people removed, real photos with an emoji over
any visible face, then 18 AI-generated "nano banana" photos with quality/composition problems that
kept recurring — see PROJECT_STATE.md for that full history. Direct request after the AI-photo
approach kept falling short: "צריך להיות יצירתיים באמת באמת לחשוב מחוץ לקופסה", pointing at the
reference bot Dorin's own no-photos placeholder (one consistent branded character illustration + a
confident caption) as the model to follow instead of another photo-realism attempt.

The SVG markup here MUST be kept identical to the inline <svg class="todi-mascot"> in
website/templates/_listing_card.html — the website renders that markup directly (crisp at any
size, no image request, themeable), while this script renders the SAME markup to a PNG for
Telegram/WhatsApp, which can only send a real image file. There's deliberately no single shared
source both read from (the SVG is tiny and simple enough that a build step would be overkill) —
if the design changes, update both copies and re-run this script.

Requires only playwright's already-installed Chromium (PLAYWRIGHT_BROWSERS_PATH is preconfigured
in this project's dev environment - see CLAUDE.md/README) - no other dependencies, no network
access, no external assets.
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIRS = [
    Path(__file__).resolve().parent.parent / "common" / "dorin_common" / "assets" / "dachshunds",
    Path(__file__).resolve().parent.parent / "website" / "static" / "dachshunds",
]

# Keep in sync with website/templates/_listing_card.html's <svg class="todi-mascot"> — see
# module docstring.
MASCOT_SVG = """
<svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">
  <path d="M 100 220 Q 55 195 62 150 Q 66 128 82 138 Q 76 165 105 190 Z" fill="#6b4226"/>
  <rect x="255" y="255" width="26" height="55" rx="13" fill="#6b4226"/>
  <rect x="145" y="255" width="26" height="55" rx="13" fill="#6b4226"/>
  <ellipse cx="210" cy="230" rx="115" ry="58" fill="#8b5a3c"/>
  <ellipse cx="205" cy="255" rx="80" ry="30" fill="#faf3e6"/>
  <rect x="245" y="265" width="26" height="55" rx="13" fill="#8b5a3c"/>
  <rect x="155" y="265" width="26" height="55" rx="13" fill="#8b5a3c"/>
  <ellipse cx="300" cy="190" rx="62" ry="55" fill="#8b5a3c"/>
  <path d="M 265 150 Q 230 160 235 220 Q 240 250 265 235 Q 250 190 265 150 Z" fill="#5c3823"/>
  <path d="M 335 150 Q 370 165 362 225 Q 356 253 332 235 Q 350 190 335 150 Z" fill="#5c3823"/>
  <ellipse cx="335" cy="205" rx="34" ry="26" fill="#a0724d"/>
  <ellipse cx="355" cy="203" rx="10" ry="8" fill="#3a2317"/>
  <circle cx="290" cy="175" r="8" fill="#241417"/>
  <circle cx="292" cy="172" r="2.5" fill="#fff"/>
  <circle cx="322" cy="172" r="8" fill="#241417"/>
  <circle cx="324" cy="169" r="2.5" fill="#fff"/>
  <path d="M 315 215 Q 340 236 362 216" stroke="#3a2317" stroke-width="3.5" fill="none" stroke-linecap="round"/>
  <path d="M 330 220 Q 338 236 346 220 Q 338 232 330 220 Z" fill="#d97a86"/>
  <g transform="translate(268,108)">
    <path d="M0 30 L0 10 L14 22 L27 0 L40 22 L54 10 L54 30 Z" fill="#e8c25a" stroke="#b8860b" stroke-width="2" stroke-linejoin="round"/>
    <circle cx="27" cy="8" r="4.5" fill="#7a1f2b"/>
  </g>
  <g fill="#e8c25a">
    <path d="M 95 120 l 6 16 l 16 6 l -16 6 l -6 16 l -6 -16 l -16 -6 l 16 -6 Z"/>
    <path d="M 340 300 l 4 11 l 11 4 l -11 4 l -4 11 l -4 -11 l -11 -4 l 11 -4 Z"/>
  </g>
</svg>
"""

# Card's own background tint (--wine-tint in style.css) so the PNG matches the website's SVG
# rendering, which sits on that same color via .listing-cover.no-image's background.
BACKGROUND = "#fdf1f2"


def main() -> None:
    html = f"""
    <html><head><style>
      html, body {{ margin:0; padding:0; }}
      .box {{ width: 1000px; height: 1000px; background: {BACKGROUND};
              display: flex; align-items: center; justify-content: center; }}
      svg {{ width: 820px; height: 820px; }}
    </style></head>
    <body><div class="box">{MASCOT_SVG}</div></body></html>
    """
    html_path = Path("/tmp/todi_mascot_render.html")
    html_path.write_text(html)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            # This dev sandbox's Chromium lives at a fixed path rather than Playwright's own
            # default download location (see CLAUDE.md) - fall back to it if the plain launch
            # fails, rather than requiring every environment to hardcode the same path.
            browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        page = browser.new_page(viewport={"width": 1000, "height": 1000})
        page.goto(f"file://{html_path}")
        raw_path = Path("/tmp/todi_mascot_raw.png")
        page.screenshot(path=str(raw_path))
        browser.close()

    from PIL import Image
    import numpy as np

    img = Image.open(raw_path).convert("RGB")
    arr = np.array(img)
    bg = arr[0, 0]
    mask = np.any(np.abs(arr.astype(int) - bg.astype(int)) > 8, axis=2)
    ys, xs = np.where(mask)
    pad = 60
    left, right = max(0, xs.min() - pad), min(img.width, xs.max() + pad)
    top, bottom = max(0, ys.min() - pad), min(img.height, ys.max() + pad)
    cropped = img.crop((left, top, right, bottom))

    size = max(cropped.size)
    square = Image.new("RGB", (size, size), tuple(bg))
    square.paste(cropped, ((size - cropped.width) // 2, (size - cropped.height) // 2))

    for out_dir in OUT_DIRS:
        out_dir.mkdir(parents=True, exist_ok=True)
        square.save(out_dir / "todi_mascot.png", quality=95)
        print(f"Wrote {out_dir / 'todi_mascot.png'} ({square.size[0]}x{square.size[1]})")


if __name__ == "__main__":
    main()
