import { motion } from "framer-motion";
import { t, whatsappPublicNumber, telegramBotUrl } from "../i18n";

const easePremium = [0.16, 1, 0.3, 1];

function Blob({ style, animate, duration }) {
  return (
    <motion.div
      className="tl-blob"
      style={style}
      animate={animate}
      transition={{ duration, repeat: Infinity, repeatType: "mirror", ease: "easeInOut" }}
    />
  );
}

export default function Hero() {
  return (
    <section style={{ paddingTop: "clamp(40px, 7vw, 80px)", overflow: "hidden" }}>
      <Blob
        style={{ width: 380, height: 380, top: -140, insetInlineStart: "-8%", background: "var(--gold-light)", opacity: 0.35 }}
        animate={{ x: [0, 40, -20, 0], y: [0, -30, 20, 0], scale: [1, 1.1, 0.95, 1] }}
        duration={16}
      />
      <Blob
        style={{ width: 420, height: 420, top: 60, insetInlineEnd: "-10%", background: "var(--teal)", opacity: 0.22 }}
        animate={{ x: [0, -50, 30, 0], y: [0, 30, -20, 0], scale: [1, 0.9, 1.08, 1] }}
        duration={20}
      />

      {/* Responsive grid columns/alignment live ENTIRELY in the stylesheet below (className only,
          no inline style on this div) — an inline style value always wins over any stylesheet
          rule, including one inside @media, so putting gridTemplateColumns inline here would
          silently defeat the min-width:860px rule below and the layout would never switch to
          two columns on desktop. Real bug found while verifying this live. */}
      <div className="tl-hero-grid" style={{ position: "relative", zIndex: 1 }}>
        <div className="tl-hero-text">
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: easePremium }}>
            <span className="tl-eyebrow">{t("home.eyebrow")}</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 28, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.75, delay: 0.1, ease: easePremium }}
            className="tl-hero-h1"
            style={{
              margin: "22px 0 0", fontSize: "clamp(2.4rem, 7vw, 4.6rem)", maxWidth: 620,
              background: "linear-gradient(90deg, var(--heading) 0%, var(--teal) 40%, var(--gold) 70%, var(--heading) 100%)",
              backgroundSize: "200% auto", WebkitBackgroundClip: "text", backgroundClip: "text",
              color: "transparent", animation: "tl-shine 9s linear infinite",
            }}
          >
            {t("home.h1")}
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.25, ease: easePremium }}
            className="tl-hero-lead"
            style={{ fontSize: "1.15rem", color: "var(--text-muted)", maxWidth: 560, margin: "20px 0 0" }}
          >
            {t("home.lead")}
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.4, ease: easePremium }}
            className="tl-hero-ctas"
            style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 32 }}
          >
            <a className="tl-btn gold" href={telegramBotUrl} target="_blank" rel="noreferrer">
              {t("home.cta_open_bot")}
            </a>
            {whatsappPublicNumber && (
              <a
                className="tl-btn whatsapp"
                href={`https://wa.me/${whatsappPublicNumber}?text=${encodeURIComponent(t("whatsapp.greeting"))}`}
                target="_blank"
                rel="noreferrer"
              >
                {t("home.cta_open_whatsapp")}
              </a>
            )}
            <a className="tl-btn outline" href="#how">{t("home.cta_how")}</a>
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 40, rotate: -3 }}
          animate={{ opacity: 1, y: 0, rotate: 0 }}
          transition={{ duration: 0.9, delay: 0.3, ease: easePremium }}
          className="tl-hero-image"
          style={{ position: "relative", maxWidth: 340, margin: "0 auto" }}
        >
          <motion.img
            src="/static/todira-brand.webp?v=4"
            alt={t("home.hero_img_alt")}
            width={1184}
            height={1895}
            animate={{ y: [0, -14, 0] }}
            transition={{ duration: 6, repeat: Infinity, repeatType: "mirror", ease: "easeInOut" }}
            style={{ width: "100%", borderRadius: 28, boxShadow: "0 30px 60px rgba(14,60,58,.22)" }}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.8, x: -20 }}
            animate={{ opacity: 1, scale: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 1.1, ease: easePremium }}
            style={{
              position: "absolute", bottom: -18, insetInlineStart: -18,
              background: "var(--card)", border: "1px solid var(--border)", borderRadius: 16,
              padding: "10px 16px", boxShadow: "0 12px 28px rgba(14,60,58,.16)",
              display: "flex", alignItems: "center", gap: 8, fontSize: ".82rem", fontWeight: 700,
            }}
          >
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--teal)", display: "inline-block" }} />
            {t("home.live_badge")}
          </motion.div>
        </motion.div>
      </div>

      <style>{`
        @keyframes tl-shine { to { background-position: -200% center; } }
        .tl-hero-grid {
          display: grid;
          grid-template-columns: minmax(0, 1fr);
          gap: 40px;
          align-items: center;
          text-align: center;
        }
        .tl-hero-h1, .tl-hero-lead { margin-left: auto; margin-right: auto; }
        .tl-hero-ctas { justify-content: center; }
        /* No "order" overrides needed: DOM order is already text-then-image (matches the
           original site's mobile stacking), and CSS grid follows the container's own text
           direction for column placement — in this RTL page that already puts the first grid
           item (text) on the right and the second (image) on the left at desktop width, same as
           the original .hero-split layout it replaces. */
        @media (min-width: 860px) {
          .tl-hero-grid { grid-template-columns: 1.1fr 0.9fr; text-align: start; }
          .tl-hero-h1, .tl-hero-lead { margin-left: 0; margin-right: 0; }
          .tl-hero-ctas { justify-content: flex-start; }
        }
      `}</style>
    </section>
  );
}
