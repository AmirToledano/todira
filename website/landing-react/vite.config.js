import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

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
  plugins: [react()],
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
      },
    },
  },
})
