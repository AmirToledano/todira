# landing-react

Renders **only** todira's home page (`/`) marketing content — the hero,
momentum row, stats, feature cards, comparison table, how-it-works steps,
FAQ, and closing CTA banner. Everything else on the site (login,
`/apartments`, payments, admin, the WhatsApp/Telegram webhooks, the
header/nav/footer that wrap this page) is still the original server-rendered
Jinja2 + vanilla CSS/JS the rest of `website/` is built on — this is
deliberately a small, isolated React+Framer Motion island, not a full-site
rewrite.

## Why this exists

The owner asked for a genuinely "agency-level" animated feel for the home
page — the same React + Framer Motion + 21st.dev/UI-UX-Pro-Max combo used by
several real Instagram/TikTok "I built a $10k website from my terminal"
reference reels (reviewed frame-by-frame before this was built, not
guessed at). A full-site React migration was considered and rejected for
launch week specifically: rewriting all ~26 templates, splitting the
FastAPI backend into a pure API, and re-testing everything days before
going live was judged too large and too risky. This is the scoped
middle ground — real React, real Framer Motion, but contained to the one
page where a strong first impression matters most, with the rest of the
(working, tested) product completely untouched.

## How it's wired into the site

- `npm run build` outputs to `../static/landing/` (see `vite.config.js`'s
  `base`/`outDir`) — already served by FastAPI's existing
  `app.mount("/static", ...)` in `main.py`, no extra server config needed.
- `npm run build` also emits `.vite/manifest.json` there, mapping the
  `index.html` entry to its current hashed `.js`/`.css` filenames (they
  change on every build). `website/main.py`'s `_landing_react_assets()`
  reads that manifest and injects the right `<script>`/`<link>` tags into
  `templates/home.html` — nobody needs to hand-edit a filename after a
  rebuild.
- `templates/home.html`'s content block is just `<div id="root">` plus a
  `window.__TODIRA_HOME__ = {...}` config script (language/direction —
  the exact values `_render()` already resolved for that request, so they
  can never disagree with the server-rendered header around this island —
  and the configured WhatsApp number) and the built `<script type="module">`
  tag. `src/main.jsx` mounts `<App />` into that `#root`.
- schema.org JSON-LD SEO markup stays server-rendered in `home.html`'s
  `extra_head` block, untouched — crawlers see it without executing JS.

## Content — real copy only, not invented

`src/content.json` is a **generated** export of `website/i18n.py`'s
`TRANSLATIONS` dict (every `home.*`, `footer.*`, `cookies.*`, and
`whatsapp.*` key, all 5 supported languages: he/en/ru/fr/ar), not
hand-written placeholder text. `src/i18n.js`'s `t(key)` reads from it using
the language `window.__TODIRA_HOME__.lang` carries.

**Regenerating it** (do this after editing any of those keys in
`website/i18n.py`):

```bash
cd website
python3 -c "
import json
ns = {}
exec(compile(open('i18n.py', encoding='utf-8').read(), 'i18n.py', 'exec'), ns)
translations = ns['TRANSLATIONS']
prefixes = ('home.', 'footer.', 'cookies.', 'whatsapp.')
exact = {'meta.title_home', 'meta.description'}
keys = {k: v for k, v in translations.items() if k.startswith(prefixes) or k in exact}
with open('landing-react/src/content.json', 'w', encoding='utf-8') as f:
    json.dump(keys, f, ensure_ascii=False, indent=2)
"
```

`tests/test_website_home.py::test_react_landing_content_json_matches_i18n_py`
diffs every key/language in `content.json` against the live `TRANSLATIONS`
dict, so forgetting to re-run this after an `i18n.py` edit fails CI instead
of silently shipping stale copy.

The Hebrew query text in the feature-1 "AI understands free text" demo
(`src/sections/Features.jsx`) is a fixed literal, **not** a translation
key — matches the original page's own reasoning (a real visitor always
writes to the bot in Hebrew, regardless of the page's display language),
so it isn't in `content.json` and doesn't need regenerating.

## Local development

```bash
cd website/landing-react
npm install
npm run dev        # Vite dev server with HMR, for iterating on components
npm run build      # production build -> ../static/landing/ (what main.py actually serves)
```

`npm run dev`'s dev server is standalone (not proxied through FastAPI) —
useful for fast iteration on the components themselves, but the real
integration (config injection, manifest-driven asset tags, SEO head) only
shows up when you `npm run build` and load the page through the actual
FastAPI app (`uvicorn main:app`, then visit `/`).

## Build artifacts are committed

`../static/landing/` (the build output) is committed directly to the repo
rather than built as a separate CI/Dockerfile stage — `website/Dockerfile`
already does `COPY website/ .`, so committing the build output ships it
with zero Dockerfile changes. A proper `npm run build` CI step would be a
cleaner long-term setup if this pattern expands to more pages; it wasn't
required to get this one page working correctly and was left out of scope
for this change.
