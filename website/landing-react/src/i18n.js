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
// The visitor's Telegram user id, when logged in via a `/contact?uid=...` nav link (base.html) —
// only Contact.jsx reads this, to forward it in the POST /api/contact body for message
// attribution, same as the old form-encoded route's hidden `uid` field used to.
export const uid = injected.uid ?? null;

export function t(key) {
  const entry = content[key];
  if (!entry) return key;
  return entry[lang] || entry.he || key;
}
