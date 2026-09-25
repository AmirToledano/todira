import { motion } from "framer-motion";
import { t, lang } from "./i18n";
import content from "./content.json";
import Blob from "./Blob.jsx";

const easePremium = [0.16, 1, 0.3, 1];

// he/en only — matches this content's own real translation coverage in i18n.py (see
// i18n.py's "about page" section comment). t() would silently fall back to Hebrew for ru/fr/ar
// since those languages were never given real about.* translations, which is wrong for THIS
// content specifically — the original page instead showed the English version plus a notice
// explaining it isn't translated yet. tEn() reads content.json's own "en" entry directly,
// bypassing t()'s lang-keyed lookup (and its Hebrew fallback) entirely.
function tEn(key) {
  return content[key]?.en;
}

export default function About() {
  const showHebrew = lang === "he";
  const showNotice = lang !== "he" && lang !== "en";

  return (
    <div id="todira-about-root">
      <Blob
        style={{ width: 340, height: 340, top: -100, insetInlineStart: "-6%", background: "var(--gold-light)", opacity: 0.3 }}
        animate={{ x: [0, 30, -15, 0], y: [0, -20, 15, 0], scale: [1, 1.08, 0.96, 1] }}
        duration={18}
      />
      <Blob
        style={{ width: 300, height: 300, bottom: -80, insetInlineEnd: "-8%", background: "var(--teal)", opacity: 0.2 }}
        animate={{ x: [0, -25, 15, 0], y: [0, 20, -15, 0], scale: [1, 0.92, 1.06, 1] }}
        duration={22}
      />
      <section style={{ position: "relative", zIndex: 1, maxWidth: 680, textAlign: "center" }}>
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
          initial={{ opacity: 0, y: 24, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.7, ease: easePremium }}
          className="tl-about-h1"
        >
          {showHebrew ? t("about.h1") : tEn("about.h1") || "About Todira"}
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.15, ease: easePremium }}
          style={{ fontSize: "1.08rem", color: "var(--text-muted)", lineHeight: 1.75, marginTop: 26 }}
        >
          {showHebrew ? t("about.body_intro") : tEn("about.body_intro")}
        </motion.p>

        <motion.p
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.28, ease: easePremium }}
          style={{ fontSize: "1.08rem", color: "var(--text-muted)", lineHeight: 1.75, marginTop: 18 }}
        >
          {showHebrew ? t("about.body_disclaimer") : tEn("about.body_disclaimer")}
        </motion.p>

        <motion.p
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.4, ease: easePremium }}
          style={{ fontSize: "1.08rem", color: "var(--text-muted)", lineHeight: 1.75, marginTop: 18 }}
        >
          {showHebrew ? t("about.links_p1") : tEn("about.links_p1")}
          <a href="/terms">{showHebrew ? t("about.link_terms") : tEn("about.link_terms")}</a>
          {showHebrew ? t("about.links_p2") : tEn("about.links_p2")}
          <a href="/privacy">{showHebrew ? t("about.link_privacy") : tEn("about.link_privacy")}</a>
          {showHebrew ? t("about.links_p3") : tEn("about.links_p3")}
          <a href="/contact">{showHebrew ? t("about.link_contact_page") : tEn("about.link_contact_page")}</a>
          {showHebrew ? t("about.links_p4") : tEn("about.links_p4")}
        </motion.p>
      </section>

      <style>{`
        #todira-about-root {
          position: relative; overflow: hidden;
          padding: clamp(48px, 8vw, 96px) 24px;
          display: flex; justify-content: center;
        }
        .tl-about-h1 {
          margin: 0; font-size: clamp(2rem, 6vw, 3rem);
          background: linear-gradient(90deg, var(--heading) 0%, var(--teal) 40%, var(--gold) 70%, var(--heading) 100%);
          background-size: 200% auto; -webkit-background-clip: text; background-clip: text; color: transparent;
          animation: tl-about-shine 9s linear infinite;
        }
        @keyframes tl-about-shine { to { background-position: -200% center; } }
        @media (prefers-reduced-motion: reduce) { .tl-about-h1 { animation: none; } }
        #todira-about-root .notice {
          background: var(--teal-tint); color: var(--heading); border-radius: 12px;
          padding: 12px 18px; font-size: .9rem;
        }
        #todira-about-root a { color: var(--teal); font-weight: 600; text-decoration: underline; text-underline-offset: 2px; }
      `}</style>
    </div>
  );
}
