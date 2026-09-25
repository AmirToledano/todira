import content from "./content.json";

// The server (website/main.py's _render) already resolves the viewer's language once per
// request (?lang= > cookie > Hebrew) and injects it into every template, including home.html —
// so this reads that same resolved value from a small inline script the server writes into the
// page, rather than re-deriving it client-side and risking it disagreeing with the
// already-server-rendered header/nav around this React island.
const injected = typeof window !== "undefined" ? window.__TODIRA_PAGE__ || {} : {};

export const lang = injected.lang || "he";
export const dir = injected.dir || "rtl";
export const whatsappPublicNumber = injected.whatsappPublicNumber || "";
export const telegramBotUrl = "https://t.me/AmirDirotBot";
// The visitor's Telegram user id, when present in the page's own URL (e.g. `/contact?uid=...` or
// `/login?uid=...`, both via base.html's nav / a bot deep link) — Contact.jsx forwards it in the
// POST /api/contact body for message attribution, Login.jsx forwards it into the Google OAuth
// start link, same as each page's old server-rendered hidden field/href used to.
export const uid = injected.uid ?? null;
// Already sanitized server-side by main.py's _safe_next() before injection — see login() — so
// this is safe to use directly in a client-built href without re-validating it here.
export const next = injected.next ?? null;

// vars supports the same named-placeholder interpolation as i18n.py's own t(key, **kwargs) (e.g.
// login.hint's "{telegram_cta}") — .format()-style, not HTML, so no injection risk either way.
export function t(key, vars) {
  const entry = content[key];
  if (!entry) return key;
  const text = entry[lang] || entry.he || key;
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in vars ? vars[name] : match));
}
