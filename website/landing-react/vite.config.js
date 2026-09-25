import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Built output lands in website/static/landing/, already served by FastAPI's existing
// app.mount("/static", ...) in main.py — zero extra server wiring needed. base must match that
// mount path so the built index.html's <script>/<link> URLs resolve correctly at runtime.
export default defineConfig({
  plugins: [react()],
  base: '/static/landing/',
  build: {
    outDir: '../static/landing',
    emptyOutDir: true,
    // manifest.json maps source entry -> hashed built filenames, so main.py can inject the
    // correct <script>/<link> tags without anyone hand-editing a hashed filename after every
    // future `npm run build` (those hashes change on every content change).
    manifest: true,
  },
})
