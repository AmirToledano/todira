import { useRef, useCallback } from "react";

/**
 * Cursor-tracked "spotlight" glow — a common modern-agency micro-interaction (seen across the
 * reference reels reviewed for this redesign). Writes pointer position straight to CSS custom
 * properties via a ref on plain mousemove, not React state, so it costs no re-render per pointer
 * move. Spread the returned props onto the element that should track the cursor, and render
 * <span className="tl-spotlight-glow" /> as its first child (see index.css for the shared rule —
 * defined once there rather than duplicated inline per component).
 */
export function useSpotlight() {
  const ref = useRef(null);
  const onMouseMove = useCallback((e) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty("--spot-x", `${e.clientX - rect.left}px`);
    el.style.setProperty("--spot-y", `${e.clientY - rect.top}px`);
  }, []);
  return { ref, onMouseMove, className: "tl-spotlight-card" };
}
