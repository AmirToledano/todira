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
at all); the remaining 18 were renumbered todi_01.jpg..todi_18.jpg.

Each of those 18 crops was then 4x upscaled with Real-ESRGAN (`RealESRGAN_x4plus.pth`, via the
`realesrgan`/`basicsr` pip packages — NOT project dependencies, one-off local tooling) before being
saved into both asset directories. This was a direct follow-up fix, same day: a real quality
complaint ("האיכות של התמונות לא טובות כל כך... אני רוצה שזה יהיה חלק 100%") — each collage cell
was only ~260-380px on a side (the collages were 768x1364 and 896x1195 total for 7 and 12 cells
respectively), soft/blocky once shown at real card size. Real-ESRGAN clearly sharpened fine detail
(fur texture, eyes) on inspection — confirmed with a before/after crop comparison, not just by
running it and assuming it helped. `basicsr` needed a compatibility shim for newer torchvision:
`torchvision.transforms.functional_tensor` was removed/renamed, monkey-patched at runtime by
registering a stand-in module before importing basicsr (see any git history around this date for
the exact shim if this ever needs re-running). The model weights downloaded from
`github.com/xinntao/Real-ESRGAN`'s GitHub release, same reachable-release-asset pattern used for
every other model in this project's history.

Selection is fully random per render (see dorin_common/cards.py's `_dachshund_photo_path` and
website/templates/_listing_card.html's `random` filter) — 2026-09-02 request: "שיהיה אקראי
לחלוטין" (should be completely random), a deliberate departure from every earlier version of this
feature, which picked deterministically from the listing id so a given listing always showed the
same photo.

If the photo set changes again, there's no script to re-run - just replace the todi_NN.jpg files
in both asset directories directly and update _TODI_PHOTO_COUNT / todi_photo_count to match.
"""
