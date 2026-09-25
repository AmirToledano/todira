import { motion } from "framer-motion";
import { t } from "../i18n";

const easePremium = [0.16, 1, 0.3, 1];

export default function Compare() {
  return (
    <section style={{ textAlign: "center" }}>
      <motion.h2
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.6 }}
        transition={{ duration: 0.6, ease: easePremium }}
        style={{ fontSize: "clamp(1.7rem, 4vw, 2.4rem)", marginBottom: 10 }}
      >
        {t("home.compare_title")}
      </motion.h2>
      <motion.p
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.6, delay: 0.1 }}
        style={{ color: "var(--text-muted)", maxWidth: 520, margin: "0 auto 48px" }}
      >
        {t("home.compare_sub")}
      </motion.p>

      {/* gridTemplateColumns lives in the stylesheet (className), not inline — same lesson as
          Hero.jsx: an inline style value always beats a stylesheet rule, media queries included,
          so putting it inline here would silently defeat the max-width:620px mobile-stack rule
          below. Real bug found live: at 390px width this rendered as two cramped ~170px columns
          instead of stacking, same failure mode Hero.jsx already had for its own grid. */}
      <div className="tl-compare-grid" style={{ maxWidth: 820, margin: "0 auto", textAlign: "start" }}>
        <motion.div
          initial={{ opacity: 0, x: 60 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 0.7, ease: easePremium }}
          style={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 22, padding: 28 }}
        >
          <h3 style={{ fontSize: "1.1rem", marginBottom: 16 }}>{t("home.compare_without_title")}</h3>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 12 }}>
            {["home.compare_without_1", "home.compare_without_2", "home.compare_without_3", "home.compare_without_4"].map((k) => (
              <li key={k} style={{ color: "var(--text-muted)", fontSize: ".92rem", paddingInlineStart: 26, position: "relative" }}>
                <span style={{ position: "absolute", insetInlineStart: 0, color: "#b06a6a", fontWeight: 700 }}>✕</span>
                {t(k)}
              </li>
            ))}
          </ul>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: -60 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 0.7, delay: 0.12, ease: easePremium }}
          whileHover={{ y: -6 }}
          style={{
            background: "linear-gradient(160deg, var(--teal-tint), var(--card))",
            border: "1px solid var(--border)", borderRadius: 22, padding: 28,
            boxShadow: "0 20px 44px rgba(14,138,130,.18)",
          }}
        >
          <h3 style={{ fontSize: "1.1rem", marginBottom: 16 }}>{t("home.compare_with_title")}</h3>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 12 }}>
            {["home.compare_with_1", "home.compare_with_2", "home.compare_with_3", "home.compare_with_4"].map((k) => (
              <li key={k} style={{ color: "var(--text-muted)", fontSize: ".92rem", paddingInlineStart: 26, position: "relative" }}>
                <span style={{ position: "absolute", insetInlineStart: 0, color: "var(--gold)", fontWeight: 700 }}>✓</span>
                {t(k)}
              </li>
            ))}
          </ul>
        </motion.div>
      </div>

      {/* Reuses the real value-anchor copy already published on /upgrade (upgrade.value_anchor_*)
          rather than inventing new pricing copy here — same honest ₪49.90/month-vs-coffee framing
          the product already uses where someone's actually deciding whether to pay, now given a
          preview here too so cost isn't a surprise later. Owner feedback, live screenshot review:
          this replaces what used to be a second near-duplicate "example listing" showing almost
          the same Tel Aviv rent numbers as feature1's own demo above. */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.6 }}
        transition={{ duration: 0.6, delay: 0.2, ease: easePremium }}
        style={{
          maxWidth: 620, margin: "36px auto 0", textAlign: "center",
          background: "var(--teal-tint)", borderRadius: 18, padding: "22px 26px",
        }}
      >
        <p style={{ margin: 0, fontWeight: 700, color: "var(--heading)" }}>
          {t("upgrade.value_anchor_title")}
        </p>
        <p style={{ margin: "8px 0 0", fontSize: ".92rem", color: "var(--text-muted)" }}>
          {t("upgrade.value_anchor_body")}
        </p>
      </motion.div>

      <style>{`
        .tl-compare-grid { display: grid; grid-template-columns: 1fr; gap: 24px; }
        @media (min-width: 620px) {
          .tl-compare-grid { grid-template-columns: 1fr 1fr; }
        }
      `}</style>
    </section>
  );
}
