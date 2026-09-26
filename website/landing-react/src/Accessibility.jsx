import { motion } from "framer-motion";
import { t, lang } from "./i18n";
import content from "./content.json";

const easePremium = [0.16, 1, 0.3, 1];

// he/en only — matches this content's own real translation coverage in i18n.py (see
// i18n.py's "accessibility page" section comment). Same tEn() pattern as About.jsx: reads
// content.json's own "en" entry directly, bypassing t()'s lang-keyed lookup (and its Hebrew
// fallback) entirely.
function tEn(key) {
  return content[key]?.en;
}

const SECTIONS = ["s1", "s2", "s3"];

export default function Accessibility() {
  const showHebrew = lang === "he";
  const showNotice = lang !== "he" && lang !== "en";
  const tr = (key) => (showHebrew ? t(key) : tEn(key));

  // Deliberately no site-wide .reveal class here — that mechanism does a one-time
  // querySelectorAll('.reveal') before this React bundle even mounts, so an element added to the
  // DOM afterward (this whole tree) would never be found and would stay stuck at .reveal's own
  // opacity:0 starting state forever. Framer Motion's own initial/animate below does the
  // equivalent entrance animation instead — same pattern About.jsx uses.
  return (
    <div className="legal-page" id="todira-accessibility-root">
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

      <motion.h1
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: easePremium }}
      >
        {tr("accessibility.h1")}
      </motion.h1>
      <p className="legal-updated">{tr("accessibility.updated")}</p>

      {SECTIONS.map((s, i) => (
        <motion.div
          key={s}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 + i * 0.08, ease: easePremium }}
        >
          <h2>{tr(`accessibility.${s}_title`)}</h2>
          {s === "s2" ? (
            <ul>
              <li>{tr("accessibility.s2_item1")}</li>
              <li>{tr("accessibility.s2_item2")}</li>
              <li>{tr("accessibility.s2_item3")}</li>
              <li>{tr("accessibility.s2_item4")}</li>
            </ul>
          ) : (
            <p>{tr(`accessibility.${s}_body`)}</p>
          )}
        </motion.div>
      ))}

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1 + SECTIONS.length * 0.08, ease: easePremium }}
      >
        <h2>{tr("accessibility.s4_title")}</h2>
        <p>
          {tr("accessibility.s4_body_pre")}
          <a href="mailto:amir81358@gmail.com">amir81358@gmail.com</a>
          {tr("accessibility.s4_body_post")}
        </p>
      </motion.div>
    </div>
  );
}
