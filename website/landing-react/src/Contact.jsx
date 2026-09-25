import { useState } from "react";
import { motion } from "framer-motion";
import { t, uid, whatsappPublicNumber, telegramBotUrl } from "./i18n";

const easePremium = [0.16, 1, 0.3, 1];

// idle -> submitting -> "sent" | "error" (errorKind: "empty" | "consent" | "generic")
export default function Contact() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [consent, setConsent] = useState(false);
  const [status, setStatus] = useState("idle");
  const [errorKind, setErrorKind] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setStatus("submitting");
    setErrorKind(null);
    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          email,
          message,
          uid: uid != null ? String(uid) : "",
          consent,
        }),
      });
      // Validation failures come back as 200 {ok:false, error:...} — see /api/contact's own
      // docstring for why. A non-2xx here means something actually broke server-side.
      const data = res.ok ? await res.json() : { ok: false, error: "generic" };
      if (data.ok) {
        setStatus("sent");
      } else {
        setStatus("error");
        setErrorKind(data.error || "generic");
      }
    } catch {
      setStatus("error");
      setErrorKind("generic");
    }
  }

  const errorMessage =
    errorKind === "empty"
      ? t("contact.error_empty")
      : errorKind === "consent"
        ? t("contact.error_consent")
        : errorKind
          ? t("contact.error_generic")
          : null;

  return (
    <>
      <motion.div
        className="page-banner"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: easePremium }}
      >
        <div className="pb-text">
          <h1>{t("contact.title")}</h1>
          <p>{t("contact.subtitle")}</p>
        </div>
      </motion.div>

      <motion.div
        className="settings-card"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1, ease: easePremium }}
      >
        {status === "sent" ? (
          <div className="empty-state">
            <div className="glyph" aria-hidden="true">
              📬
            </div>
            <p>
              <strong>{t("contact.success_title")}</strong>
            </p>
            <p className="hint">{t("contact.success_body")}</p>
          </div>
        ) : (
          <>
            {errorMessage && (
              <div className="notice" role="alert">
                {errorMessage}
              </div>
            )}
            <form onSubmit={handleSubmit}>
              <div className="field">
                <label htmlFor="c-name">{t("contact.name_label")}</label>
                <input id="c-name" type="text" value={name} onChange={(e) => setName(e.target.value)} />
              </div>

              <div className="field">
                <label htmlFor="c-email">{t("contact.email_label")}</label>
                <input id="c-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>

              <div className="field">
                <label htmlFor="c-message">{t("contact.message_label")}</label>
                <textarea
                  id="c-message"
                  rows={6}
                  placeholder={t("contact.message_placeholder")}
                  required
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                />
              </div>

              <label className="check-chip" style={{ textAlign: "start", display: "flex", gap: 6, marginBottom: 10 }}>
                <input
                  type="checkbox"
                  required
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                <span>
                  {t("contact.consent_prefix")}{" "}
                  <a href="/privacy" target="_blank" rel="noreferrer">
                    {t("cookies.notice_link")}
                  </a>
                </span>
              </label>

              <button className="btn block" type="submit" disabled={status === "submitting"}>
                {t("contact.submit_btn")}
              </button>
            </form>
          </>
        )}
      </motion.div>

      <motion.div
        className="contact-other"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.2, ease: easePremium }}
      >
        <h2 className="section-title">{t("contact.other_ways_title")}</h2>
        <a className="btn outline" href={telegramBotUrl} target="_blank" rel="noreferrer">
          {t("contact.telegram_way")} 💬
        </a>
        {whatsappPublicNumber && (
          <a
            className="btn outline"
            href={`https://wa.me/${whatsappPublicNumber}?text=${encodeURIComponent(t("whatsapp.greeting"))}`}
            target="_blank"
            rel="noreferrer"
          >
            {t("contact.whatsapp_way")} 💬
          </a>
        )}
      </motion.div>
    </>
  );
}
