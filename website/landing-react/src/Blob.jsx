import { motion } from "framer-motion";

// Shared decorative floating gradient orb — used by Hero.jsx (home) and any other React page
// wanting the same soft ambient background motion. Extracted out of Hero.jsx (2026-09-25) when
// About.jsx became the second page to need it, rather than duplicating the definition.
export default function Blob({ style, animate, duration }) {
  return (
    <motion.div
      className="tl-blob"
      style={style}
      animate={animate}
      transition={{ duration, repeat: Infinity, repeatType: "mirror", ease: "easeInOut" }}
    />
  );
}
