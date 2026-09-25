import { motion } from "framer-motion";
import { t } from "../i18n";

const easePremium = [0.16, 1, 0.3, 1];

const STEPS = [
  { titleKey: "home.step1_title", bodyKey: "home.step1_body" },
  { titleKey: "home.step2_title", bodyKey: "home.step2_body" },
  { titleKey: "home.step3_title", bodyKey: "home.step3_body" },
];

export default function HowItWorks() {
  return (
    <section id="how" style={{ textAlign: "center" }}>
      <motion.h2
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.6 }}
        transition={{ duration: 0.6, ease: easePremium }}
        style={{ fontSize: "clamp(1.7rem, 4vw, 2.4rem)", marginBottom: 10 }}
      >
        {t("home.how_title")}
      </motion.h2>
      <motion.p
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.6, delay: 0.1 }}
        style={{ color: "var(--text-muted)", maxWidth: 480, margin: "0 auto 56px" }}
      >
        {t("home.how_sub")}
      </motion.p>

      <div style={{ display: "flex", flexDirection: "column", gap: 40, maxWidth: 620, margin: "0 auto", textAlign: "start" }}>
        {STEPS.map((s, i) => (
          <motion.div
            key={s.titleKey}
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.5 }}
            transition={{ duration: 0.6, delay: i * 0.15, ease: easePremium }}
            style={{ display: "flex", gap: 20, alignItems: "flex-start" }}
          >
            <motion.div
              whileInView={{ scale: [0.6, 1.15, 1] }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.15 + 0.1 }}
              style={{
                flexShrink: 0, width: 48, height: 48, borderRadius: "50%",
                background: "linear-gradient(135deg, var(--gold-light), var(--gold))",
                color: "var(--teal-dark)", fontFamily: "Rubik, sans-serif", fontWeight: 800,
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1.1rem",
                boxShadow: "0 8px 20px rgba(217,164,65,.35)",
              }}
            >
              {i + 1}
            </motion.div>
            <div>
              <h3 style={{ fontSize: "1.1rem", marginBottom: 6 }}>{t(s.titleKey)}</h3>
              <p style={{ color: "var(--text-muted)", margin: 0, lineHeight: 1.6 }}>{t(s.bodyKey)}</p>
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
