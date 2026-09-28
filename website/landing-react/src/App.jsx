import { MotionConfig } from "framer-motion";
import Hero from "./sections/Hero";
import Momentum from "./sections/Momentum";
import Stats from "./sections/Stats";
import CityMarquee from "./sections/CityMarquee";
import CinematicStat from "./sections/CinematicStat";
import Features from "./sections/Features";
import Compare from "./sections/Compare";
import HowItWorks from "./sections/HowItWorks";
import FAQ from "./sections/FAQ";
import FooterCTA from "./sections/FooterCTA";

export default function App() {
  // 2026-09-28: the Stats/Compare/Features/HowItWorks/FAQ/FooterCTA/Momentum sections all use
  // Framer Motion's whileInView to fade content in from opacity:0 as it scrolls into view — real
  // owner report: this breaks iOS Safari's own "Full Page" screenshot capture, which appears not
  // to reliably trigger every section's IntersectionObserver before stitching the final image, so
  // sections below the fold can render as blank/invisible in the captured screenshot.
  // reducedMotion="user" makes every whileInView animation on the page resolve instantly to its
  // end (visible) state instead of an animated fade whenever the OS/browser reports
  // prefers-reduced-motion: reduce, matching how Hero/CityMarquee/CinematicStat already behave
  // (see their own prefers-reduced-motion checks) — these scroll-reveal sections were the one
  // real gap. Doesn't remove the underlying "invisible until intersection fires" dependency (still
  // unverified against real iOS Safari from this environment), but is a genuine, low-risk
  // improvement either way — real accessibility gap, not a guess dressed up as a full fix.
  return (
    <MotionConfig reducedMotion="user">
      <div id="todira-landing-root">
        <Hero />
        <Momentum />
        <Stats />
        <CityMarquee />
        <CinematicStat />
        <Features />
        <Compare />
        <HowItWorks />
        <FAQ />
        <FooterCTA />
      </div>
    </MotionConfig>
  );
}
