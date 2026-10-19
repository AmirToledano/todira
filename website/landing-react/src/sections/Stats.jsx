import { motion } from "framer-motion";
import { t } from "../i18n";
import { useSpotlight } from "../useSpotlight";
import { useLiveStats } from "../liveStats";
import CountUp from "../CountUp";

const easePremium = [0.16, 1, 0.3, 1];

// Shown only when the live numbers are unavailable (see liveStats.js).
// 2026-10-19 (owner): no "AI", "24/7" or scan-frequency cards - generic filler, and scan times are never shown.
const STATIC_STATS = [["home.stat_free_value", "home.stat_free_label"]];



function liveCards(stats) {
  return [
    { key: "new", value: <CountUp value={stats.new_24h} />, label: t("home.live_new_24h_label") },
    { key: "active", value: <CountUp value={stats.active} />, label: t("home.live_active_label") },
    { key: "cities", value: <CountUp value={stats.cities} />, label: t("home.live_cities_label") },
  ];
}

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09 } },
};
const item = {
  hidden: { opacity: 0, y: 24, scale: 0.94 },
  show: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.5, ease: easePremium } },
};

function StatCard({ value, label }) {
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
        {value}
      </div>
      <div style={{ fontSize: ".82rem", color: "var(--text-muted)", marginTop: 4 }}>{label}</div>
    </motion.div>
  );
}

export default function Stats() {
  const stats = useLiveStats();
  const cards = stats
    ? liveCards(stats)
    : STATIC_STATS.map(([valueKey, labelKey]) => ({ key: valueKey, value: t(valueKey), label: t(labelKey) }));
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
        {cards.map((card) => (
          <StatCard key={card.key} value={card.value} label={card.label} />
        ))}
      </motion.div>
    </section>
  );
}
