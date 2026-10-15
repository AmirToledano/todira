import { useEffect, useRef } from "react";
import { animate, useInView } from "framer-motion";
import { formatCount } from "./liveStats";

// Counts up to `value` the first time it scrolls into view, and glides to each new value after that (the live stats refresh
// every minute). Plain text once prefers-reduced-motion is set.
export default function CountUp({ value, duration = 1.6 }) {
  const ref = useRef(null);
  const shown = useRef(0);
  const inView = useInView(ref, { once: true, amount: 0.5 });

  useEffect(() => {
    const el = ref.current;
    if (!el || !inView) return undefined;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.textContent = formatCount(value);
      shown.current = value;
      return undefined;
    }
    const controls = animate(shown.current, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        shown.current = v;
        el.textContent = formatCount(v);
      },
    });
    return () => controls.stop();
  }, [value, inView, duration]);

  return <span ref={ref}>{formatCount(0)}</span>;
}
