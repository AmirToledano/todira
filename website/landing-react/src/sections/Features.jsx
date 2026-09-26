import { motion } from "framer-motion";
import { t } from "../i18n";
import { useSpotlight } from "../useSpotlight";

const easePremium = [0.16, 1, 0.3, 1];

// Matches the chip pill styling below (var(--card) background, teal text/border) so a highlighted
// phrase inside the query bubble visually reads as "this becomes that chip," not as a coincidence.
const highlightStyle = {
  background: "var(--card)", color: "var(--teal)", fontWeight: 700,
  borderRadius: 6, padding: "0 5px", whiteSpace: "nowrap",
};

const FEATURES = [
  { titleKey: "home.feature1_title", bodyKey: "home.feature1_body" },
  { titleKey: "home.feature2_title", bodyKey: "home.feature2_body" },
  { titleKey: "home.feature3_title", bodyKey: "home.feature3_body" },
];

function FeatureCard({ f, index }) {
  const spotlight = useSpotlight();
  return (
    <motion.div
      ref={spotlight.ref}
      onMouseMove={spotlight.onMouseMove}
      className={spotlight.className}
      initial={{ opacity: 0, y: 40 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.6, delay: index * 0.12, ease: easePremium }}
      whileHover={{ y: -8, boxShadow: "0 24px 48px rgba(14,138,130,.18)", borderColor: "var(--teal)" }}
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderRadius: 24,
        padding: "36px 30px",
        boxShadow: "0 4px 16px rgba(14,60,58,.06)",
      }}
    >
      <span className="tl-spotlight-glow" aria-hidden="true" />
      <div
        style={{
          width: 52, height: 52, borderRadius: 16,
          background: "linear-gradient(135deg, var(--teal-tint), var(--card))",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontFamily: "Rubik, sans-serif", fontWeight: 800, fontSize: "1.3rem", color: "var(--teal)",
          marginBottom: 18,
        }}
      >
        {index + 1}
      </div>
      <h3 style={{ fontSize: "1.25rem", marginBottom: 10 }}>{t(f.titleKey)}</h3>
      <p style={{ color: "var(--text-muted)", fontSize: "0.98rem", lineHeight: 1.6, margin: 0 }}>
        {t(f.bodyKey)}
      </p>
      {index === 0 && (
        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.6 }}
          variants={{ hidden: {}, show: { transition: { staggerChildren: 0.15, delayChildren: 0.2 } } }}
          style={{ marginTop: 18, paddingTop: 18, borderTop: "1px dashed var(--border)" }}
        >
          {/* Fixed Hebrew example, not a translation key — matches feature1_body's own
              "you write to the bot in Hebrew" framing (see i18n.py's own comment on the
              original home.html version of this), stays Hebrew regardless of page language;
              only the parsed chip labels below translate. The three phrases below are
              highlighted (highlightStyle, matching the chip pills' own colors) precisely because
              they're the SAME words as the chips beneath them — a real visitor screenshot flagged
              the un-highlighted version as reading like an accidental duplication rather than a
              parsing demo; highlighting + the home.feature1_understood_label caption below make
              the "AI extracted these 3 things from your sentence" point explicit instead of
              relying on a lone "↓" to imply it. */}
          <motion.div
            variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } }}
            style={{
              background: "var(--surface-tint, var(--teal-tint))", borderRadius: 12, padding: "10px 14px",
              fontSize: ".88rem", color: "var(--text)", textAlign: "start", direction: "rtl", lineHeight: 1.8,
            }}
          >
            "<span style={highlightStyle}>2-3 חדרים</span> ב<span style={highlightStyle}>תל אביב</span> עד{" "}
            <span style={highlightStyle}>6000 שקל</span>"
          </motion.div>
          <motion.div
            variants={{ hidden: { opacity: 0 }, show: { opacity: 1 } }}
            style={{ textAlign: "center", color: "var(--teal)", fontSize: ".78rem", fontWeight: 700, margin: "10px 0" }}
          >
            {t("home.feature1_understood_label")}
          </motion.div>
          <motion.div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
            {[t("home.feature1_example_city"), t("home.feature1_example_rooms"), t("home.feature1_example_price")].map((chip) => (
              <motion.span
                key={chip}
                variants={{ hidden: { opacity: 0, scale: 0.8 }, show: { opacity: 1, scale: 1 } }}
                style={{
                  background: "var(--card)", border: "1px solid var(--teal)", color: "var(--teal)",
                  borderRadius: 999, padding: "5px 14px", fontSize: ".8rem", fontWeight: 700,
                }}
              >
                {chip}
              </motion.span>
            ))}
          </motion.div>
        </motion.div>
      )}
    </motion.div>
  );
}

export default function Features() {
  return (
    <section>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: 24,
        }}
      >
        {FEATURES.map((f, i) => (
          <FeatureCard key={f.titleKey} f={f} index={i} />
        ))}
      </div>
    </section>
  );
}
