import { readFileSync } from 'node:fs'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 2026-11-10 (owner: make the home page faster): src/content.json holds every language (~680 kB as one chunk, loaded by
// every page). This plugin serves `virtual:todira-content/<lang>`: only that language's texts, with the fallbacks
// already applied (newer file languages -> English -> Hebrew; the five core languages -> Hebrew), the same order
// src/i18n.js's t() used. i18n.js imports the visitor's one language, so each becomes its own small chunk.
// content.json stays the single generated source (tests/test_website_home.py checks it against i18n.py).
const FILE_LANGS = ['es', 'pt', 'hi', 'fil', 'th', 'zh']
const CONTENT_PREFIX = 'virtual:todira-content/'
function todiraContentPerLanguage() {
  const contentPath = new URL('src/content.json', import.meta.url).pathname
  return {
    name: 'todira-content-per-language',
    resolveId(id) {
      return id.startsWith(CONTENT_PREFIX) ? '\0' + id : null
    },
    load(id) {
      if (!id.startsWith('\0' + CONTENT_PREFIX)) return null
      this.addWatchFile(contentPath)
      const lang = id.slice(('\0' + CONTENT_PREFIX).length)
      const content = JSON.parse(readFileSync(contentPath, 'utf-8'))
      // 'en-only': English with no fallback (the legal pages' tEn(), which shows English to everyone but Hebrew readers)
      const order = lang === 'en-only' ? ['en'] : FILE_LANGS.includes(lang) ? [lang, 'en', 'he'] : [lang, 'he']
      const texts = {}
      for (const [key, entry] of Object.entries(content)) {
        const found = order.find((code) => entry[code])
        if (found) texts[key] = entry[found]
      }
      return 'export default ' + JSON.stringify(texts)
    },
  }
}

// Built output lands in website/static/landing/, already served by FastAPI's existing
// app.mount("/static", ...) in main.py — zero extra server wiring needed. base must match that
// mount path so the built index.html's <script>/<link> URLs resolve correctly at runtime.
//
// 2026-09-25: multi-page build — index.html (home) was the only entry until about.html (About)
// became the second React island. Every future page-as-React-island just adds one more entry
// here rather than spinning up a whole separate Vite project (separate node_modules/config/
// content.json to keep in sync) the way landing-react itself was first scaffolded — this is the
// shared foundation the eventual full-site migration builds on incrementally, page by page.
export default defineConfig({
  plugins: [react(), todiraContentPerLanguage()],
  base: '/static/landing/',
  build: {
    outDir: '../static/landing',
    emptyOutDir: true,
    // manifest.json maps each source entry -> its own hashed built filenames, so main.py can
    // inject the correct <script>/<link> tags per page without anyone hand-editing a hashed
    // filename after every future `npm run build` (those hashes change on every content change).
    manifest: true,
    rollupOptions: {
      input: {
        index: new URL('index.html', import.meta.url).pathname,
        about: new URL('about.html', import.meta.url).pathname,
        accessibility: new URL('accessibility.html', import.meta.url).pathname,
        privacy: new URL('privacy.html', import.meta.url).pathname,
        terms: new URL('terms.html', import.meta.url).pathname,
        contact: new URL('contact.html', import.meta.url).pathname,
        login: new URL('login.html', import.meta.url).pathname,
        account: new URL('account.html', import.meta.url).pathname,
      },
    },
  },
})
