import { useEffect, useState } from "react";
import { pageConfig } from "./i18n";

// 2026-10-15 (owner): the home page's live numbers. The server puts the current values into the page itself
// (window.__TODIRA_PAGE__.liveStats, from main.py's _home_live_stats), so they show at once; while the page stays open they
// are refreshed from /api/home-stats every minute. null when the server could not count them: the caller then shows its fixed
// stats instead.
const REFRESH_MS = 60_000;

export function useLiveStats() {
  const [stats, setStats] = useState(pageConfig.liveStats || null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      fetch("/api/home-stats", { credentials: "same-origin" })
        .then((resp) => (resp.ok ? resp.json() : null))
        .then((data) => {
          if (alive && data && typeof data.active === "number") setStats(data);
        })
        .catch(() => {});
    const id = setInterval(load, REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);
  return stats;
}

export function formatCount(n) {
  return Math.round(n).toLocaleString("en-US");
}
