import { motion } from "framer-motion";
import { t, lang } from "./i18n";
import content from "./content.json";

const easePremium = [0.16, 1, 0.3, 1];

// he/en only — matches this content's own real translation coverage in i18n.py (see i18n.py's
// "terms page" section comment). Same tEn() pattern as About.jsx/Accessibility.jsx/Privacy.jsx.
function tEn(key) {
  return content[key]?.en;
}

// Sections 1-11 are all plain title+body — data-driven like Accessibility.jsx's SECTIONS map,
// rather than 11 near-identical JSX blocks. Section 12 (contact, with a real <a href="/contact">
// link) is rendered separately below since it needs its own pre/link/post composition.
const PLAIN_SECTIONS = Array.from({ length: 11 }, (_, i) => `s${i + 1}`);

export default function Terms() {
  const showHebrew = lang === "he";
  const showNotice = lang !== "he" && lang !== "en";
  const tr = (key) => (showHebrew ? t(key) : tEn(key));

  return (
    <div className="legal-page" id="todira-terms-root">
      {showNotice && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: easePremium }}
          className="notice"
          style={{ marginBottom: 22 }}
        >
          {t("legal.non_native_notice")}
        </motion.div>
      )}

      <motion.h1 initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: easePremium }}>
        {tr("terms.h1")}
      </motion.h1>
      <p className="legal-updated">{tr("terms.updated")}</p>

      {PLAIN_SECTIONS.map((s, i) => (
        <motion.div
          key={s}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 + i * 0.06, ease: easePremium }}
        >
          <h2>{tr(`terms.${s}_title`)}</h2>
          <p>{tr(`terms.${s}_body`)}</p>
        </motion.div>
      ))}

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1 + PLAIN_SECTIONS.length * 0.06, ease: easePremium }}
      >
        <h2>{tr("terms.s12_title")}</h2>
        <p>
          {tr("terms.s12_pre")}
          <a href="/contact">{showHebrew ? t("about.link_contact_page") : tEn("about.link_contact_page")}</a>
          {tr("terms.s12_post")}
        </p>
      </motion.div>
    </div>
  );
}
