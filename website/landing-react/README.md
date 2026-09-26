# landing-react

Renders a small, growing set of todira pages as isolated React+Framer
Motion "islands" inside the existing server-rendered site: the home page
(`/` — hero, momentum row, stats, feature cards, comparison table,
how-it-works steps, FAQ, closing CTA banner), the about page (`/about`),
the accessibility statement (`/accessibility`), the privacy policy
(`/privacy`), the terms of use (`/terms`), the contact page
(`/contact`), the login screen (`/login`), and the account page
(`/account`). Everything else on the site (`/apartments`, payments, admin,
the WhatsApp/Telegram webhooks, and the header/nav/footer that wrap every
one of these pages) is still the original server-rendered Jinja2 + vanilla
CSS/JS the rest of `website/` is built on.

## Why this exists

The owner asked for a genuinely "agency-level" animated feel — the same
React + Framer Motion + 21st.dev/UI-UX-Pro-Max combo used by several real
Instagram/TikTok "I built a $10k website from my terminal" reference reels
(reviewed frame-by-frame before this was built, not guessed at) — but a
full-site rewrite in one shot (all ~26 templates, splitting the FastAPI
backend into a pure API, re-testing everything at once) was judged too
large and risky to do in a single change. The plan instead is incremental:
each page gets converted into its own React entry here, one at a time,
starting with the simplest/safest pages and verified end-to-end before
moving to the next, with the rest of the (working, tested) product
untouched at every step. Home was first; about was the second, proving the
same shared build/serving infrastructure extends to more than one page;
accessibility was the third — the simplest kind of page there is (headings,
paragraphs, a list, zero interactivity), deliberately picked next to keep
proving the pattern on low-risk content before tackling anything with
forms or real app state; privacy was the fourth, structurally the same
shape as accessibility (headings/paragraphs/lists) but longer (10 sections)
and with a couple of spots needing real inline markup (`<strong>`, an
`<a href="/contact">` link) inside otherwise-plain translation strings —
see "Content" below for how those are handled without ever using `| safe`;
terms was the fifth, 12 sections, almost entirely plain title+body pairs
(only the last needs the same `<a href="/contact">` pattern privacy's
section 5 already established) — data-driven with a small `.map()` over
its section numbers (see `Terms.jsx`) rather than 11 near-identical JSX
blocks, the same reasoning `Accessibility.jsx`'s own `SECTIONS` map used.
Contact was the sixth and the first real departure from "read-only content
page": it has an actual form that must reach the server (name/email/message,
a required privacy-policy consent checkbox, a Telegram push to the owner on
success). A native `<form method=post>` only makes sense targeting a
server-rendered page, and this one no longer is one — so `Contact.jsx`
submits via `fetch` to a new JSON API, `POST /api/contact`, which replaced
the old form-encoded `POST /contact` entirely (see `main.py`'s
`_process_contact_message`/`contact_submit`). Success/error/submitting are
real React state now, not a full-page reload — see "The contact form" below.

## The contact form (`/contact`)

Unlike every other page here, `/contact` needs a real server round-trip
that can fail in ways worth telling the visitor about, so it's the one page
with actual client-side form state (`Contact.jsx`'s `status`/`errorKind`)
rather than being pure presentation:

- **Submits via `fetch`, not a native form POST.** `POST /api/contact`
  takes JSON (`{name, email, message, uid, consent}`) and always answers
  200 with `{ok: true}` or `{ok: false, error: "empty"|"consent"|"generic"}`
  — validation failures are ordinary, expected outcomes of user input, not
  HTTP errors, so the client only ever has to branch on `ok`. An actual
  non-2xx response (network failure, unexpected 5xx) is treated the same
  as `error: "generic"`. `contact.error_generic` (i18n.py) is a new
  translation key added for this — the old form-encoded route never needed
  one, since a network failure just showed the browser's own error page.
- **`uid` still flows through.** When a visitor reaches `/contact?uid=...`
  (a logged-in Telegram user, via `base.html`'s own nav links), `main.py`'s
  `contact()` route injects it into `window.__TODIRA_PAGE__` same as
  `lang`/`dir`/`whatsappPublicNumber`; `i18n.js` exports it, and
  `Contact.jsx` forwards it in the fetch body — same message-attribution
  behavior the old hidden form field used to provide.
- **Fully translated, not he/en-only.** `contact.*` (unlike the legal
  pages' `about.*`/`accessibility.*`/`privacy.*`/`terms.*`) already had
  real copy in all 5 languages before this conversion, so `Contact.jsx`
  uses the plain `t()` helper throughout, not the he/en-only `tEn()`
  pattern those pages use.

Login was the seventh — mostly static content like the legal pages (a
headline, three "continue with" links, an optional hint), but with one
thing worth its own note: **`next` (the post-login redirect target) is the
first value injected into `window.__TODIRA_PAGE__`, across any converted
page, that's genuinely attacker-influenceable text.** Every other injected
value so far is either a fixed-whitelist string (`lang`/`dir`), an int
(`uid`), or a trusted env var (`whatsappPublicNumber`) — `next` is a
visitor's own query parameter, and `main.py`'s `_safe_next()` only requires
it start with a single `/`; it doesn't restrict the character set
otherwise. `login.html` injects it with Jinja's `{{ next | tojson }}`
rather than a hand-written `"{{ next }}"` — `tojson` does real JSON/
JS-string escaping (including `<`/`>`, so a crafted `next` can't break out
via a literal quote or a `</script>` sequence), which plain HTML
autoescaping doesn't guarantee for script-block context. `i18n.js` exports
it as `next`, already-sanitized, safe to use directly when `Login.jsx`
builds the Google OAuth start link — see `tests/test_website_login_page.py`'s
own regression test for this.

Account was the eighth (and last one planned so far) — real subscription/
notification/channel state and a payment-history table, the heaviest data
shape of any converted page. Two things worth their own note:

- **Its 4 POST actions (cancel/resume-subscription, notifications,
  whatsapp-notifications) are deliberately UNCHANGED** — still plain
  `<form method="post">` submits redirecting back to `/account`, not
  `fetch`. A full page reload after a subscription/notification change is
  exactly what already happens and is completely fine UX for it, so unlike
  `/contact`'s real reason to go fetch-based (a form the visitor expects to
  feel instant, with inline success/error state), there's no reason to
  widen `/account`'s blast radius by touching its action routes at all —
  `Account.jsx` only reskins presentation around those same native forms
  and hidden `uid`/`wid` fields. See `main.py`'s `account()` route comment.
- **The whole `account_config` object goes through `{{ ... | tojson }}`
  as one value**, not field-by-field the way `lang`/`dir`/`uid` etc. are
  on the simpler pages — real DB-derived data (dates, payment amounts, a
  `wid` token that's user-supplied on the wid-only login path) has no
  business being hand-interpolated into a `<script>` block one value at a
  time the way `login.html`'s own `next | tojson` finding already showed
  matters. `i18n.js`'s `pageConfig` export is the generic escape hatch for
  this — a page whose config is too shaped/heavy to deserve individual
  named exports there.

## How it's wired into the site

- `vite.config.js`'s `build.rollupOptions.input` lists one entry per React
  page (`index` → `index.html` → home, `about` → `about.html` → about, and
  so on for `accessibility`/`privacy`/`terms`/`contact`/`login`/`account`). Adding another
  page-as-React-island means adding one more entry here,
  not spinning up a whole separate Vite project — shared `node_modules`,
  shared `content.json`/`i18n.js`/component library (e.g. `Blob.jsx`), and
  Vite automatically code-splits shared dependencies (React, Framer Motion,
  shared components) into common chunks across entries.
- `npm run build` outputs to `../static/landing/` (see `vite.config.js`'s
  `base`/`outDir`) — already served by FastAPI's existing
  `app.mount("/static", ...)` in `main.py`, no extra server config needed.
- `npm run build` also emits `.vite/manifest.json` there, mapping each
  entry to its current hashed `.js`/`.css` filenames (they change on every
  build). `website/main.py`'s `_landing_react_assets(entry_name)` reads
  that manifest per entry and injects the right `<script>`/`<link>` tags
  into the matching template (`templates/home.html`, `templates/about.html`)
  — nobody needs to hand-edit a filename after a rebuild. It recursively
  walks each entry's `imports` chain to collect CSS, because Vite attributes
  CSS reachable only through a shared chunk (e.g. `Blob.jsx`, imported by
  both pages) to that chunk's own manifest entry, not to each page directly.
- Each React page's template content block is just `<div id="root">` plus a
  `window.__TODIRA_PAGE__ = {...}` config script (language/direction — the
  exact values `_render()` already resolved for that request, so they can
  never disagree with the server-rendered header around the island — plus
  whatever else that specific page needs, e.g. home's WhatsApp number) and
  the built `<script type="module">` tag. Each page has its own
  `src/<page>-main.jsx` that mounts its root component into that `#root`.
- schema.org JSON-LD SEO markup stays server-rendered in `home.html`'s
  `extra_head` block, untouched — crawlers see it without executing JS.

## Content — real copy only, not invented

`src/content.json` is a **generated** export of `website/i18n.py`'s
`TRANSLATIONS` dict (every `home.*`, `footer.*`, `cookies.*`, `whatsapp.*`,
`about.*`, `accessibility.*`, `privacy.*`, `terms.*`, `contact.*`,
`login.*`, and `account.*` key, plus a handful of exact keys from elsewhere
in the file that a React page reuses rather than re-authoring — e.g.
`upgrade.value_anchor_title`/`_body`, reused on the home page's Compare
section so the price reassurance shown there stays the same real copy as
`/upgrade` itself; `upgrade.plan_weekly`/`_biweekly`/`_monthly`/
`_subscription`, reused by `Account.jsx`'s own payment-history plan
labels, same reasoning — not a second, driftable copy of it; `auth.logout`,
reused by `Account.jsx`'s own logout button (2026-09-26) — `base.html`'s
own hamburger-menu logout link already uses this exact key. All 5
supported languages where they exist — `about.*`/`accessibility.*`/
`privacy.*`/`terms.*` are deliberately he/en only, see below;
`contact.*`/`login.*`/`account.*` are fully translated like `home.*`), not
hand-written placeholder text. `src/i18n.js`'s `t(key, vars?)` reads from
it using the language `window.__TODIRA_PAGE__.lang` carries — the optional
second argument does `.format()`-style `{name}` placeholder substitution,
matching `i18n.py`'s own `t(key, **kwargs)` (used by `login.hint`'s
`{telegram_cta}`).

A translation string never contains raw HTML (no `| safe` anywhere in this
codebase). Where a sentence needs inline markup — `privacy.s1_item7_pre`/
`_strong`/`_post` for a bolded phrase mid-sentence, `privacy.s5_pre`/`_post`
and `terms.s12_pre`/`_post` each wrapping a real `<a href="/contact">` link,
`privacy.s3_item{1-5}_label`/`_body` for a bolded provider name followed by
its description — the key is split into separate pieces and the React
component (`Privacy.jsx`/`Terms.jsx`) composes the actual `<strong>`/`<a>`
JSX elements around them, rather than ever injecting a string as HTML.

**Regenerating it** (do this after editing any of those keys in
`website/i18n.py`, or after adding a new React page that needs its own
content prefix):

```bash
cd website
python3 -c "
import json
ns = {}
exec(compile(open('i18n.py', encoding='utf-8').read(), 'i18n.py', 'exec'), ns)
translations = ns['TRANSLATIONS']
prefixes = ('home.', 'footer.', 'cookies.', 'whatsapp.', 'about.', 'accessibility.', 'privacy.', 'terms.', 'contact.', 'login.', 'account.')
exact = {
    'meta.title_home', 'meta.description', 'meta.title_about', 'meta.title_accessibility',
    'meta.title_privacy', 'meta.title_terms', 'meta.title_contact', 'meta.title_login',
    'meta.title_account', 'legal.non_native_notice', 'upgrade.value_anchor_title',
    'upgrade.value_anchor_body', 'upgrade.plan_weekly', 'upgrade.plan_biweekly',
    'upgrade.plan_monthly', 'upgrade.plan_subscription', 'auth.logout',
}
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

## The hero's 3D scene (ScanCore)

`src/sections/ScanCore.jsx` renders a real Three.js scene (via
`@react-three/fiber` + `@react-three/drei`) behind the hero image — a
rotating wireframe "core" ringed by two tilted orbits and a drifting field
of glowing points, in the brand's own teal/gold. Owner sent real reference
footage of current Awwwards-style Three.js product-showcase sites and
asked for that tier of visual spectacle specifically, not just
CSS/Framer Motion polish; there's no literal product to render in 3D here,
so this represents what the product actually *does* (continuous scanning)
rather than forcing an unrelated 3D object in.

A few things that only matter because this is WebGL, not CSS:

- **Lazy-loaded.** Three.js + fiber + drei add ~250kB gzipped on their own
  — `Hero.jsx` imports `ScanCore` via `React.lazy()`, so that weight is a
  separate chunk (`ScanCore-*.js`) that loads *after* the hero's actual
  content (headline, CTAs), not blocking it. The dark panel frame itself
  (`.tl-scancore-shell`) lives in `Hero.jsx`, not in `ScanCore.jsx` — so the
  panel's own background renders immediately, with zero layout shift,
  before the lazy chunk has even started downloading; the 3D scene just
  fills that already-visible panel a moment later.
- **Graceful when it can't run.** `prefers-reduced-motion: reduce` and a
  runtime WebGL-support check both skip mounting the `<Canvas>` entirely
  (computed once via a `useState` lazy initializer, not an effect — see
  `supportsScene()`) — the shell's own static gradient panel is a
  complete, intentional-looking fallback on its own, not a broken/blank
  state.
- **Bounded, not free-roaming.** The scene reacts to the pointer with a
  small spring-damped offset (same restraint as `Hero.jsx`'s own
  `TiltImage`), never a draggable orbit-controls camera — it should read
  as *alive*, not as a 3D toy visitors can spin.

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
