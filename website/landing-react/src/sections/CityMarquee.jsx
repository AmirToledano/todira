// Real city names from todira_common/cities.py (the actual coverage list the scraper/matcher use)
// — not decorative filler. Kept in Hebrew regardless of page language, same reasoning as the
// AI-demo's fixed query text in Features.jsx: this is how the underlying data actually is (Yad2
// listings and the bot's own city matching are Hebrew), not translated UI copy.
const CITIES = [
  "תל אביב יפו", "ירושלים", "חיפה", "ראשון לציון", "פתח תקווה", "רמת גן",
  "הרצליה", "רעננה", "כפר סבא", "נתניה", "באר שבע", "רחובות", "חולון", "גבעתיים",
];

export default function CityMarquee() {
  const track = [...CITIES, ...CITIES]; // duplicated for a seamless loop
  return (
    <div className="tl-marquee" aria-hidden="true">
      <div className="tl-marquee-track">
        {track.map((city, i) => (
          <span className="tl-marquee-item" key={i}>
            {city}
            <span className="tl-marquee-dot">•</span>
          </span>
        ))}
      </div>
      <style>{`
        .tl-marquee {
          overflow: hidden; padding: 18px 0;
          -webkit-mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent);
          mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent);
        }
        .tl-marquee-track {
          display: flex; width: max-content;
          animation: tl-marquee-scroll 32s linear infinite;
        }
        .tl-marquee-item {
          display: inline-flex; align-items: center; gap: 20px;
          font-family: 'Rubik', sans-serif; font-weight: 700; font-size: 1.05rem;
          color: var(--text-muted); white-space: nowrap; padding-inline-end: 20px;
        }
        .tl-marquee-dot { color: var(--gold); font-size: .8rem; }
        @keyframes tl-marquee-scroll {
          from { transform: translateX(0); }
          to { transform: translateX(-50%); }
        }
        [dir="rtl"] .tl-marquee-track { animation-name: tl-marquee-scroll-rtl; }
        @keyframes tl-marquee-scroll-rtl {
          from { transform: translateX(0); }
          to { transform: translateX(50%); }
        }
        /* Real bug found live: [dir="rtl"] .tl-marquee-track (specificity 0,2,0) beats a plain
           .tl-marquee-track rule (0,1,0) regardless of source order or being inside a media
           query — under RTL + reduced-motion the marquee kept scrolling. Matching the RTL
           selector's own specificity here (rather than just repeating .tl-marquee-track) is what
           actually wins in both directions. */
        @media (prefers-reduced-motion: reduce) {
          .tl-marquee-track, [dir="rtl"] .tl-marquee-track { animation: none; }
          .tl-marquee { overflow-x: auto; }
        }
      `}</style>
    </div>
  );
}
