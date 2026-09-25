import { useRef } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { t, whatsappPublicNumber, telegramBotUrl } from "../i18n";

const easePremium = [0.16, 1, 0.3, 1];

function Blob({ style, animate, duration }) {
  return (
    <motion.div
      className="tl-blob"
      style={style}
      animate={animate}
      transition={{ duration, repeat: Infinity, repeatType: "mirror", ease: "easeInOut" }}
    />
  );
}

/* Cursor-tracked 3D tilt on the hero image — the "flying" feel from the reference reels this
   redesign was based on. Raw pointer offset feeds a spring (not the raw value directly) so the
   tilt settles with a soft, physical motion instead of snapping to the cursor every pixel; resets
   to flat on mouse-leave rather than staying tilted wherever the cursor last was. Framer Motion
   composes rotateX/rotateY (this) with the separate `rotate` (2D, entrance-only) and `y` (the
   floating bob) used on the child <motion.img> automatically — different transform components, no
   conflict between the one-time entrance animation and this continuous cursor-driven one. */
function TiltImage({ children }) {
  const ref = useRef(null);
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const springX = useSpring(mouseX, { stiffness: 150, damping: 20 });
  const springY = useSpring(mouseY, { stiffness: 150, damping: 20 });
  const rotateX = useTransform(springY, [-0.5, 0.5], ["10deg", "-10deg"]);
  const rotateY = useTransform(springX, [-0.5, 0.5], ["-10deg", "10deg"]);

  function handleMouseMove(e) {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const rect = ref.current.getBoundingClientRect();
    mouseX.set((e.clientX - rect.left) / rect.width - 0.5);
    mouseY.set((e.clientY - rect.top) / rect.height - 0.5);
  }
  function handleMouseLeave() {
    mouseX.set(0);
    mouseY.set(0);
  }

  return (
    <div
      ref={ref}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{ perspective: 800 }}
    >
      <motion.div style={{ rotateX, rotateY, transformStyle: "preserve-3d" }}>
        {children}
      </motion.div>
    </div>
  );
}

export default function Hero() {
  return (
    <section style={{ paddingTop: "clamp(40px, 7vw, 80px)", overflow: "hidden" }}>
      <Blob
        style={{ width: 380, height: 380, top: -140, insetInlineStart: "-8%", background: "var(--gold-light)", opacity: 0.35 }}
        animate={{ x: [0, 40, -20, 0], y: [0, -30, 20, 0], scale: [1, 1.1, 0.95, 1] }}
        duration={16}
      />
      <Blob
        style={{ width: 420, height: 420, top: 60, insetInlineEnd: "-10%", background: "var(--teal)", opacity: 0.22 }}
        animate={{ x: [0, -50, 30, 0], y: [0, 30, -20, 0], scale: [1, 0.9, 1.08, 1] }}
        duration={20}
      />

      {/* Responsive grid columns/alignment live ENTIRELY in the stylesheet below (className only,
          no inline style on this div) — an inline style value always wins over any stylesheet
          rule, including one inside @media, so putting gridTemplateColumns inline here would
          silently defeat the min-width:860px rule below and the layout would never switch to
          two columns on desktop. Real bug found while verifying this live. */}
      <div className="tl-hero-grid" style={{ position: "relative", zIndex: 1 }}>
        <div className="tl-hero-text">
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: easePremium }}>
            <span className="tl-eyebrow">{t("home.eyebrow")}</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 28, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.75, delay: 0.1, ease: easePremium }}
            className="tl-hero-h1"
            style={{
              margin: "22px 0 0", fontSize: "clamp(2.4rem, 7vw, 4.6rem)", maxWidth: 620,
              background: "linear-gradient(90deg, var(--heading) 0%, var(--teal) 40%, var(--gold) 70%, var(--heading) 100%)",
              backgroundSize: "200% auto", WebkitBackgroundClip: "text", backgroundClip: "text",
              color: "transparent",
            }}
          >
            {t("home.h1")}
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.25, ease: easePremium }}
            className="tl-hero-lead"
            style={{ fontSize: "1.15rem", color: "var(--text-muted)", maxWidth: 560, margin: "20px 0 0" }}
          >
            {t("home.lead")}
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.4, ease: easePremium }}
            className="tl-hero-ctas"
            style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 32 }}
          >
            <a className="tl-btn gold" href={telegramBotUrl} target="_blank" rel="noreferrer">
              {t("home.cta_open_bot")}
            </a>
            {whatsappPublicNumber && (
              <a
                className="tl-btn whatsapp"
                href={`https://wa.me/${whatsappPublicNumber}?text=${encodeURIComponent(t("whatsapp.greeting"))}`}
                target="_blank"
                rel="noreferrer"
              >
                {t("home.cta_open_whatsapp")}
              </a>
            )}
            <a className="tl-btn outline" href="#how">{t("home.cta_how")}</a>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.55, ease: easePremium }}
            className="tl-hero-proof"
            style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", marginTop: 26 }}
          >
            <span className="tl-eyebrow" style={{ background: "var(--card)" }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--teal)", display: "inline-block" }} />
              {t("home.live_badge")}
            </span>
            <div
              style={{
                background: "var(--card)", border: "1px solid var(--border)", borderRadius: 14,
                padding: "8px 14px", boxShadow: "0 4px 14px rgba(14,60,58,.08)", textAlign: "start",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span
                  style={{
                    background: "var(--teal-tint)", color: "var(--heading)", fontSize: ".68rem", fontWeight: 700,
                    padding: "2px 9px", borderRadius: 999,
                  }}
                >
                  {t("home.example_badge_label")}
                </span>
                <span style={{ fontFamily: "Rubik, sans-serif", fontWeight: 700, fontSize: ".9rem" }}>
                  {t("home.example_card_title")}
                </span>
              </div>
              <span style={{ fontSize: ".8rem", color: "var(--text-muted)" }}>{t("home.example_card_sub")}</span>
            </div>
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 40, rotate: -3 }}
          animate={{ opacity: 1, y: 0, rotate: 0 }}
          transition={{ duration: 0.9, delay: 0.3, ease: easePremium }}
          className="tl-hero-image"
          style={{ position: "relative", maxWidth: 340, margin: "0 auto" }}
        >
          <TiltImage>
            <motion.img
              src="/static/todira-brand.webp?v=4"
              alt={t("home.hero_img_alt")}
              width={1184}
              height={1895}
              animate={{ y: [0, -14, 0] }}
              transition={{ duration: 6, repeat: Infinity, repeatType: "mirror", ease: "easeInOut" }}
              style={{ width: "100%", borderRadius: 28, boxShadow: "0 30px 60px rgba(14,60,58,.22)" }}
            />
            {/* home.stat_uptime_* ("24/7" / "הבוט תמיד ער") here, not home.live_badge — that text
                already appears once, in its original spot near the CTAs below, so reusing it here
                too would just repeat the same sentence on screen twice for no reason. */}
            <motion.div
              initial={{ opacity: 0, scale: 0.8, x: -20 }}
              animate={{ opacity: 1, scale: 1, x: 0 }}
              transition={{ duration: 0.6, delay: 1.1, ease: easePremium }}
              style={{
                position: "absolute", bottom: -18, insetInlineStart: -18,
                background: "var(--card)", border: "1px solid var(--border)", borderRadius: 16,
                padding: "10px 16px", boxShadow: "0 12px 28px rgba(14,60,58,.16)",
                display: "flex", alignItems: "center", gap: 8,
              }}
            >
              <span style={{ fontFamily: "Rubik, sans-serif", fontWeight: 800, fontSize: "1.05rem", color: "var(--teal)" }}>
                {t("home.stat_uptime_value")}
              </span>
              <span style={{ fontSize: ".72rem", color: "var(--text-muted)" }}>{t("home.stat_uptime_label")}</span>
            </motion.div>
          </TiltImage>
        </motion.div>
      </div>

      <style>{`
        @keyframes tl-shine { to { background-position: -200% center; } }
        .tl-hero-grid {
          display: grid;
          grid-template-columns: minmax(0, 1fr);
          gap: 40px;
          align-items: center;
          text-align: center;
        }
        .tl-hero-h1, .tl-hero-lead { margin-left: auto; margin-right: auto; }
        .tl-hero-ctas { justify-content: center; }
        /* No "order" overrides needed: DOM order is already text-then-image (matches the
           original site's mobile stacking), and CSS grid follows the container's own text
           direction for column placement — in this RTL page that already puts the first grid
           item (text) on the right and the second (image) on the left at desktop width, same as
           the original .hero-split layout it replaces. */
        @media (min-width: 860px) {
          .tl-hero-grid { grid-template-columns: 1.1fr 0.9fr; text-align: start; }
          .tl-hero-h1, .tl-hero-lead { margin-left: 0; margin-right: 0; }
          .tl-hero-ctas { justify-content: flex-start; }
        }
        /* animation lives here (className), not in the style= prop above — same "inline style
           always wins over a stylesheet rule, media queries included" lesson already found twice
           tonight (the grid columns above, and Compare.jsx's own grid) — a THIRD instance found
           live while checking prefers-reduced-motion: the reduced-motion override below could
           never have taken effect against an inline animation value no matter what it said. */
        .tl-hero-h1 { animation: tl-shine 9s linear infinite; }
        @media (prefers-reduced-motion: reduce) {
          .tl-hero-h1 { animation: none; }
        }
      `}</style>
    </section>
  );
}
