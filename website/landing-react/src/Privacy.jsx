import { motion } from "framer-motion";
import { t, lang } from "./i18n";
import content from "./content.json";

const easePremium = [0.16, 1, 0.3, 1];

// he/en only — matches this content's own real translation coverage in i18n.py (see
// i18n.py's "privacy page" section comment). Same tEn() pattern as About.jsx/Accessibility.jsx.
function tEn(key) {
  return content[key]?.en;
}

export default function Privacy() {
  const showHebrew = lang === "he";
  const showNotice = lang !== "he" && lang !== "en";
  const tr = (key) => (showHebrew ? t(key) : tEn(key));

  const providers = [1, 2, 3, 4, 5].map((n) => ({
    label: tr(`privacy.s3_item${n}_label`),
    body: tr(`privacy.s3_item${n}_body`),
  }));

  return (
    <div className="legal-page" id="todira-privacy-root">
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
        {tr("privacy.h1")}
      </motion.h1>
      <p className="legal-updated">{tr("privacy.updated")}</p>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1, ease: easePremium }}>
        <h2>{tr("privacy.s1_title")}</h2>
        <ul>
          <li>{tr("privacy.s1_item1")}</li>
          <li>{tr("privacy.s1_item2")}</li>
          <li>{tr("privacy.s1_item3")}</li>
          <li>{tr("privacy.s1_item4")}</li>
          <li>{tr("privacy.s1_item5")}</li>
          <li>{tr("privacy.s1_item6")}</li>
          <li>
            {tr("privacy.s1_item7_pre")}
            <strong>{tr("privacy.s1_item7_strong")}</strong>
            {tr("privacy.s1_item7_post")}
          </li>
          <li>{tr("privacy.s1_item8")}</li>
        </ul>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.16, ease: easePremium }}>
        <h2>{tr("privacy.s2_title")}</h2>
        <p>{tr("privacy.s2_body")}</p>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.22, ease: easePremium }}>
        <h2>{tr("privacy.s3_title")}</h2>
        <p>{tr("privacy.s3_intro")}</p>
        <ul>
          {providers.map((p) => (
            <li key={p.label}>
              <strong>{p.label}</strong>
              {p.body}
            </li>
          ))}
        </ul>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.28, ease: easePremium }}>
        <h2>{tr("privacy.s4_title")}</h2>
        <p>{tr("privacy.s4_body")}</p>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.34, ease: easePremium }}>
        <h2>{tr("privacy.s5_title")}</h2>
        <p>
          {tr("privacy.s5_pre")}
          <a href="/contact">{showHebrew ? t("about.link_contact_page") : tEn("about.link_contact_page")}</a>
          {tr("privacy.s5_post")}
        </p>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.4, ease: easePremium }}>
        <h2>{tr("privacy.s6_title")}</h2>
        <p>{tr("privacy.s6_body")}</p>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.46, ease: easePremium }}>
        <h2>{tr("privacy.s7_title")}</h2>
        <p>{tr("privacy.s7_body")}</p>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.52, ease: easePremium }}>
        <h2>{tr("privacy.s8_title")}</h2>
        <p>{tr("privacy.s8_body")}</p>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.58, ease: easePremium }}>
        <h2>{tr("privacy.s9_title")}</h2>
        <p>{tr("privacy.s9_body")}</p>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.64, ease: easePremium }}>
        <h2>{tr("privacy.s10_title")}</h2>
        <p>{tr("privacy.s10_body")}</p>
      </motion.div>
    </div>
  );
}
