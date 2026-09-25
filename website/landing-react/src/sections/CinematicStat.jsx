import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { t } from "../i18n";

/* A deliberate "camera-move" moment borrowed from the current wave of Awwwards-style 3D/WebGL
   product sites (reviewed live: real reference reels of Three.js product showcases — huge
   oversized single-word/short-phrase statements, color-washed backgrounds that shift as the
   "camera" moves through the scene). This site has no 3D scene to move a camera through, so the
   same *feeling* — scale, focus and color drifting as you scroll past a huge central figure — is
   built with a scroll-linked Framer Motion transform instead: real content (home.stat_uptime_*,
   the same "24/7 / the bot never sleeps" stat already shown in Stats.jsx), not new invented copy,
   given one dramatic full-bleed moment of its own rather than a small card among four others. */
export default function CinematicStat() {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const scale = useTransform(scrollYProgress, [0, 0.5, 1], [0.82, 1, 0.82]);
  const opacity = useTransform(scrollYProgress, [0, 0.3, 0.7, 1], [0.25, 1, 1, 0.25]);
  const hueDeg = useTransform(scrollYProgress, [0, 1], [-16, 16]);
  const filter = useTransform(hueDeg, (v) => `hue-rotate(${v}deg)`);

  // useScroll/useTransform drive real inline styles on every scroll frame — not a CSS transition
  // or animation, so no @media (prefers-reduced-motion) rule can ever reach it (same class of
  // issue as Hero.jsx's TiltImage). Checked here in JS instead: reduced motion gets the section's
  // own final resting state (fully visible, no hue shift) with no motion value applied at all,
  // rather than risking it landing mid-transform.
  const reduceMotion =
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  return (
    // aria-hidden: this restates the exact same uptime stat Stats.jsx already exposes
    // accessibly elsewhere on the page — a purely visual reprise, not new information, so a
    // screen-reader user shouldn't hear "24/7, the bot never sleeps" announced a second time.
    <section ref={ref} className="tl-cinematic" aria-hidden="true">
      <motion.div style={reduceMotion ? undefined : { scale, opacity }}>
        <motion.div className="tl-cinematic-figure" style={reduceMotion ? undefined : { filter }}>
          {t("home.stat_uptime_value")}
        </motion.div>
        <p className="tl-cinematic-caption">{t("home.stat_uptime_label")}</p>
      </motion.div>

      <style>{`
        .tl-cinematic {
          padding: clamp(64px, 13vw, 150px) 24px;
          text-align: center;
          overflow: hidden;
        }
        .tl-cinematic-figure {
          font-family: 'Rubik', sans-serif;
          font-weight: 800;
          font-size: clamp(4.2rem, 17vw, 10.5rem);
          line-height: 1;
          letter-spacing: -.02em;
          background: linear-gradient(90deg, var(--teal), var(--gold));
          -webkit-background-clip: text; background-clip: text; color: transparent;
        }
        .tl-cinematic-caption {
          margin: 18px 0 0;
          font-size: clamp(1.05rem, 2.6vw, 1.5rem);
          font-weight: 600;
          color: var(--text-muted);
        }
      `}</style>
    </section>
  );
}
