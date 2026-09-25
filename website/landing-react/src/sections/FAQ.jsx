import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { t } from "../i18n";

const easePremium = [0.16, 1, 0.3, 1];

const ITEMS = [
  { qKey: "home.faq1_q", aKey: "home.faq1_a" },
  { qKey: "home.faq2_q", aKey: "home.faq2_a" },
  { qKey: "home.faq3_q", aKey: "home.faq3_a" },
  { qKey: "home.faq4_q", aKey: "home.faq4_a" },
];

function FaqItem({ item, index }) {
  const [open, setOpen] = useState(false);
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.4 }}
      transition={{ duration: 0.5, delay: index * 0.06, ease: easePremium }}
      style={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 16, overflow: "hidden" }}
    >
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "18px 22px", background: "transparent", border: "none", cursor: "pointer",
          fontFamily: "Rubik, sans-serif", fontWeight: 700, fontSize: "1rem", color: "var(--heading)",
          textAlign: "start",
        }}
        aria-expanded={open}
      >
        {t(item.qKey)}
        <motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.3 }} style={{ flexShrink: 0, marginInlineStart: 12 }}>
          ⌄
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: easePremium }}
            style={{ overflow: "hidden" }}
          >
            <p style={{ margin: 0, padding: "0 22px 20px", color: "var(--text-muted)", lineHeight: 1.6 }}>{t(item.aKey)}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function FAQ() {
  return (
    <section style={{ textAlign: "center" }}>
      <motion.h2
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.6 }}
        transition={{ duration: 0.6, ease: easePremium }}
        style={{ fontSize: "clamp(1.7rem, 4vw, 2.4rem)", marginBottom: 40 }}
      >
        {t("home.faq_title")}
      </motion.h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 680, margin: "0 auto" }}>
        {ITEMS.map((item, i) => (
          <FaqItem key={item.qKey} item={item} index={i} />
        ))}
      </div>
    </section>
  );
}
