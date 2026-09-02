"""One-off asset note — NOT run at deploy/runtime, and there is currently nothing to run.

`common/dorin_common/assets/dachshunds/todi_detective.jpg` and its copy in
`website/static/dachshunds/` (the "no real photos" listing-card placeholder, used identically on
the website and in Telegram/WhatsApp — see dorin_common/cards.py's `_dachshund_photo_path` and
website/templates/_listing_card.html) are a crop of a single illustration the user supplied
directly (2026-09-02): Todi as a detective (deerstalker hat) standing on a laptop, pointing out a
matching listing on a map to his smiling owner, with real-estate UI icons (a "for rent" sign, a
key, a floor plan, a bot, a calculator) floating around them.

The original image was portrait-oriented (896x1195) and didn't fit the listing card's own 4:3
cover aspect ratio without either heavy letterboxing or losing most of its detail to a "cover"
crop. Cropped down to its lower ~60% (896x715 — Todi, the laptop, and the owner's face; the
floating icon row above that region wouldn't read at small card size anyway) to come close to a
4:3 landscape shape, then used as-is; the crop's exact bounds aren't reproducible from anything
still in the repo (the original full image isn't checked in, only this crop), so there's no
regenerate script here.

This replaces the flat-vector crowned-dachshund mascot illustration that came immediately before
it (2026-09-02, same day) and every photo-based attempt before that (a CC0 cartoon illustration,
real photos with background/people removed, real photos with an emoji over any visible face, 18
AI-generated "nano banana" photos) — see PROJECT_STATE.md for that full history. Unlike every
earlier round, this illustration was supplied directly and asked for by name rather than iterated
on inside a session, so there's no design-process history to document here either.
"""
