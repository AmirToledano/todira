
// The server (website/main.py's _render) already resolves the viewer's language once per
// request (?lang= > cookie > Hebrew) and injects it into every template, including home.html —
// so this reads that same resolved value from a small inline script the server writes into the
// page, rather than re-deriving it client-side and risking it disagreeing with the
// already-server-rendered header/nav around this React island.
const injected = typeof window !== "undefined" ? window.__TODIRA_PAGE__ || {} : {};

export const lang = injected.lang || "he";
export const dir = injected.dir || "rtl";
export const telegramBotUrl = "https://t.me/AmirDirotBot";
// The visitor's Telegram user id, when present in the page's own URL (e.g. `/contact?uid=...` or
// `/login?uid=...`, both via base.html's nav / a bot deep link) — Contact.jsx forwards it in the
// POST /api/contact body for message attribution, Login.jsx forwards it into the Google OAuth
// start link, same as each page's old server-rendered hidden field/href used to.
export const uid = injected.uid ?? null;
// Already sanitized server-side by main.py's _safe_next() before injection — see login() — so
// this is safe to use directly in a client-built href without re-validating it here.
export const next = injected.next ?? null;
// /contact only: "feedback" when opened from the feedback bubble (base.html), and the signed-in visitor's own name and
// email to start the form with (contact.html, from their session).
export const topic = injected.topic ?? null;
export const prefill = injected.prefill || {};
// Raw escape hatch for a page whose own config is too shaped/heavy to deserve individual named
// exports here (e.g. Account.jsx's subscription/notification/channel state + payment history,
// injected as one object via account()'s own `| tojson` — see account.html's own comment). Pages
// with a couple of simple values keep using the named exports above instead.
export const pageConfig = injected;

// 2026-11-10 (owner: make the home page faster): only the visitor's language is downloaded, as its own small chunk
// (vite.config.js's todiraContentPerLanguage builds one per language from content.json, fallbacks already applied:
// the languages whose texts come from website/i18n_langs/<code>.json show English for a key their file doesn't have
// yet, then Hebrew; the five core languages fall back to Hebrew). Every page module waits for it before rendering.
const LOADERS = {
  he: () => import("virtual:todira-content/he"),
  en: () => import("virtual:todira-content/en"),
  ru: () => import("virtual:todira-content/ru"),
  fr: () => import("virtual:todira-content/fr"),
  ar: () => import("virtual:todira-content/ar"),
  es: () => import("virtual:todira-content/es"),
  pt: () => import("virtual:todira-content/pt"),
  hi: () => import("virtual:todira-content/hi"),
  fil: () => import("virtual:todira-content/fil"),
  th: () => import("virtual:todira-content/th"),
  zh: () => import("virtual:todira-content/zh"),
};
const content = (await (LOADERS[lang] || LOADERS.he)()).default;

// vars supports the same named-placeholder interpolation as i18n.py's own t(key, **kwargs) (e.g.
// login.hint's "{telegram_cta}") — .format()-style, not HTML, so no injection risk either way.
export function t(key, vars) {
  const text = content[key] ?? key;
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in vars ? vars[name] : match));
}
