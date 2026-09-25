import { motion } from "framer-motion";
import { t, telegramBotUrl, whatsappPublicNumber } from "../i18n";

const easePremium = [0.16, 1, 0.3, 1];

export default function FooterCTA() {
  return (
    <section>
      <motion.div
        initial={{ opacity: 0, y: 40, scale: 0.98 }}
        whileInView={{ opacity: 1, y: 0, scale: 1 }}
        viewport={{ once: true, amount: 0.4 }}
        transition={{ duration: 0.7, ease: easePremium }}
        style={{
          position: "relative", overflow: "hidden",
          background: "linear-gradient(135deg, var(--teal) 0%, var(--teal-dark) 100%)",
          borderRadius: 28, padding: "clamp(40px, 6vw, 72px) 28px", textAlign: "center", color: "#fff",
        }}
      >
        <motion.div
          className="tl-blob"
          animate={{ x: [0, 30, -20, 0], y: [0, -20, 10, 0] }}
          transition={{ duration: 14, repeat: Infinity, repeatType: "mirror", ease: "easeInOut" }}
          style={{ width: 260, height: 260, top: -100, insetInlineEnd: -60, background: "var(--gold-light)", opacity: 0.25 }}
        />
        <h2 style={{ color: "#fff", fontSize: "clamp(1.6rem, 4vw, 2.3rem)", position: "relative", zIndex: 1 }}>
          {t("home.footer_cta_title")}
        </h2>
        <p style={{ color: "rgba(255,255,255,.85)", maxWidth: 480, margin: "14px auto 30px", position: "relative", zIndex: 1 }}>
          {t("home.footer_cta_body")}
        </p>
        <div style={{ display: "flex", gap: 14, justifyContent: "center", flexWrap: "wrap", position: "relative", zIndex: 1 }}>
          <a className="tl-btn gold" href={telegramBotUrl} target="_blank" rel="noreferrer">
            {t("home.footer_cta_btn")}
          </a>
          {whatsappPublicNumber && (
            <a
              className="tl-btn whatsapp"
              href={`https://wa.me/${whatsappPublicNumber}?text=${encodeURIComponent(t("whatsapp.greeting"))}`}
              target="_blank"
              rel="noreferrer"
            >
              {t("home.footer_cta_whatsapp_btn")}
            </a>
          )}
        </div>
      </motion.div>
    </section>
  );
}
