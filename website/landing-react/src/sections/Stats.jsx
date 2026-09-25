import { motion } from "framer-motion";
import { t } from "../i18n";
import { useSpotlight } from "../useSpotlight";

const easePremium = [0.16, 1, 0.3, 1];

const STATS = [
  ["home.stat_scan_freq_value", "home.stat_scan_freq_label"],
  ["home.stat_ai_value", "home.stat_ai_label"],
  ["home.stat_uptime_value", "home.stat_uptime_label"],
  ["home.stat_free_value", "home.stat_free_label"],
];

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09 } },
};
const item = {
  hidden: { opacity: 0, y: 24, scale: 0.94 },
  show: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.5, ease: easePremium } },
};

function StatCard({ valueKey, labelKey }) {
  const spotlight = useSpotlight();
  return (
    <motion.div
      ref={spotlight.ref}
      onMouseMove={spotlight.onMouseMove}
      className={spotlight.className}
      variants={item}
      whileHover={{ y: -6, boxShadow: "0 16px 40px rgba(14,138,130,.22)" }}
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderRadius: 18,
        padding: "22px 18px",
        textAlign: "center",
        boxShadow: "0 4px 16px rgba(14,60,58,.06)",
      }}
    >
      <span className="tl-spotlight-glow" aria-hidden="true" />
      <div style={{ fontFamily: "Rubik, sans-serif", fontWeight: 800, fontSize: "1.6rem", color: "var(--teal)" }}>
        {t(valueKey)}
      </div>
      <div style={{ fontSize: ".82rem", color: "var(--text-muted)", marginTop: 4 }}>{t(labelKey)}</div>
    </motion.div>
  );
}

export default function Stats() {
  return (
    <section style={{ paddingTop: 0, paddingBottom: "clamp(40px, 6vw, 80px)" }}>
      <motion.div
        variants={container}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, amount: 0.4 }}
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          gap: 16,
          maxWidth: 820,
          margin: "0 auto",
        }}
      >
        {STATS.map(([valueKey, labelKey]) => (
          <StatCard key={valueKey} valueKey={valueKey} labelKey={labelKey} />
        ))}
      </motion.div>
    </section>
  );
}
