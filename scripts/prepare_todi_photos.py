"""One-off asset processor — NOT run at deploy/runtime, and there is currently nothing to run.

The 18 photos in common/dorin_common/assets/dachshunds/ and website/static/dachshunds/ (the
"no real photos" listing-card placeholder) are AI-generated staged photos of Todi (the user's own
dachshund), made directly by the user with Gemini's "nano banana" image editing and handed over as
two collage images. This replaces every earlier approach tried for this feature (2026-09-02, same
day): a CC0 cartoon illustration, then real photos with the background/any touching person removed
(rembg, then YOLOv8-seg), then real photos with an emoji stamped over any visible face — all
rejected in favor of these AI-generated photos, used as-is. See PROJECT_STATE.md for that history.

The two collages were split into individual photos with a one-off script (not kept here — it isn't
reusable without the source collage files, which aren't part of this repo) that detected the
white/off-white gutter rows and columns between cells and cropped each cell out with a small inward
padding. Of 19 cells, 1 was dropped (a failed generation showing potted plants with no dog visible
at all); the remaining 18 were renumbered todi_01.jpg..todi_18.jpg and copied unmodified into both
asset directories.

Selection is fully random per render (see dorin_common/cards.py's `_dachshund_photo_path` and
website/templates/_listing_card.html's `random` filter) — 2026-09-02 request: "שיהיה אקראי
לחלוטין" (should be completely random), a deliberate departure from every earlier version of this
feature, which picked deterministically from the listing id so a given listing always showed the
same photo.

If the photo set changes again, there's no script to re-run - just replace the todi_NN.jpg files
in both asset directories directly and update _TODI_PHOTO_COUNT / todi_photo_count to match.
"""
