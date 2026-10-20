import { motion } from "framer-motion";
import Icon from "./Icon";
import { t, uid, next, telegramBotUrl } from "./i18n";

const easePremium = [0.16, 1, 0.3, 1];

// 2026-09-25: /login became a React island — same reasoning as Contact.jsx's own comment on why
// `.reveal` (base.html's one-time IntersectionObserver) never works on a React root, so this uses
// Framer Motion's own initial/animate instead.
export default function Login() {
  const safeNext = next || "/apartments";
  const googleHref = `/auth/google/start?next=${encodeURIComponent(safeNext)}${uid != null ? `&uid=${uid}` : ""}`;

  return (
    <motion.div
      className="login-card"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: easePremium }}
    >
      <div className="login-head">
        <span className="crown" aria-hidden="true">
          <Icon name="crown" />
        </span>
        <h1>{t("login.h1")}</h1>
        <p>{t("login.subtitle")}</p>
      </div>

      <a className="btn google block" href={googleHref}>
        <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
          <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.71v2.26h2.9c1.7-1.57 2.7-3.87 2.7-6.6z" />
          <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.9-2.26c-.8.54-1.84.86-3.06.86-2.35 0-4.34-1.59-5.05-3.72H.96v2.33A9 9 0 0 0 9 18z" />
          <path fill="#FBBC05" d="M3.95 10.7A5.4 5.4 0 0 1 3.66 9c0-.59.1-1.17.29-1.7V4.97H.96A9 9 0 0 0 0 9c0 1.45.35 2.83.96 4.03l2.99-2.33z" />
          <path fill="#EA4335" d="M9 3.58c1.32 0 2.51.46 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.97l2.99 2.33C4.66 5.17 6.65 3.58 9 3.58z" />
        </svg>
        {t("login.google_cta")}
      </a>

      <div className="login-divider">
        <span>{t("login.divider")}</span>
      </div>

      <a className="btn telegram block" href={telegramBotUrl} target="_blank" rel="noreferrer">
        <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
          <path
            fill="#fff"
            d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"
          />
        </svg>
        {t("login.telegram_cta")}
      </a>

      {uid == null && (
        <p className="login-hint">{t("login.hint", { telegram_cta: t("login.telegram_cta") })}</p>
      )}
    </motion.div>
  );
}
