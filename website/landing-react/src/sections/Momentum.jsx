import { motion } from "framer-motion";
import { t } from "../i18n";

const easePremium = [0.16, 1, 0.3, 1];

const ITEMS = [
  ["home.momentum_1_value", "home.momentum_1_label"],
  ["home.momentum_2_value", "home.momentum_2_label"],
  ["home.momentum_3_value", "home.momentum_3_label"],
];

const container = { hidden: {}, show: { transition: { staggerChildren: 0.1, delayChildren: 0.1 } } };
const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: easePremium } },
};

export default function Momentum() {
  return (
    <section style={{ paddingTop: 0, paddingBottom: 0 }}>
      <motion.div
        variants={container}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, amount: 0.5 }}
        style={{
          display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 28,
          maxWidth: 720, margin: "0 auto",
        }}
      >
        {ITEMS.map(([valueKey, labelKey]) => (
          <motion.div key={valueKey} variants={item} style={{ textAlign: "center" }}>
            <div style={{ fontFamily: "Rubik, sans-serif", fontWeight: 800, fontSize: "1.3rem", color: "var(--teal)" }}>
              {t(valueKey)}
            </div>
            <div style={{ fontSize: ".8rem", color: "var(--text-muted)" }}>{t(labelKey)}</div>
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
}
