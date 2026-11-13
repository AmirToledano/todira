/* 2026-10-19 home page (templates/home.html): the live map, the rotating phone notification, the feed and the
   self-typing demo chat. Everything here is decoration on top of a page that already reads fine without it. */
(function () {
  "use strict";
  var L = window.__TODIRA_LANDING__ || {};
  var S = L.strings || {};
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    document.documentElement.classList.contains("a11y-no-motion");
  var nf = new Intl.NumberFormat(L.lang === "ru" || L.lang === "fr" ? L.lang : "en-US");
  var fmt = function (n) { return nf.format(n); };
  var fill = function (s, vals) { return String(s).replace(/\{(\w+)\}/g, function (m, k) { return k in vals ? vals[k] : m; }); };
  var roomsText = function (r) { return r === 1 ? S.rooms_1 : fill(S.rooms_n, { n: fmt(r) }); };
  var onView = function (el, fn, threshold) {
    if (reduce || !("IntersectionObserver" in window)) { fn(); return; }
    var io = new IntersectionObserver(function (es) {
      if (es.some(function (e) { return e.isIntersecting; })) { io.disconnect(); fn(); }
    }, { threshold: threshold || 0.25 });
    io.observe(el);
  };

  /* ---------- the demo chat: several example conversations, one after another ---------- */
  (function demo() {
    var body = document.getElementById("lp-demo");
    var demos = L.demos || [];
    if (!body || !demos.length) { return; }
    var ask = document.getElementById("lp-d-ask");
    var got = document.getElementById("lp-d-got");
    var chips = document.getElementById("lp-d-chips");
    var alertB = document.getElementById("lp-d-alert");
    if (reduce) { return; }  // the first conversation is already in the page, complete
    var idx = 0;
    function fillDemo(d) {
      chips.innerHTML = "";
      d.chips.forEach(function (c) { var s = document.createElement("span"); s.textContent = c; chips.appendChild(s); });
      // the bot's real message, line for line (main.py _demo_alert)
      var a = d.alert, card = document.getElementById("lp-d-card"), buttons = document.getElementById("lp-d-buttons");
      var line = function (emoji, label, value, cls) {
        var p = document.createElement("p");
        if (cls) { p.className = cls; }
        p.appendChild(document.createTextNode(emoji + " "));
        var b = document.createElement("b"); b.textContent = label; p.appendChild(b);
        if (value) { p.appendChild(document.createTextNode(" " + value)); }
        card.appendChild(p);
      };
      card.textContent = "";
      if (a.prefix) { line("🏢", a.prefix, ""); }
      var place = document.createElement("p"), link = document.createElement("span");
      link.className = "lp-alert-link"; link.textContent = a.place;
      place.appendChild(document.createTextNode("📍")); place.appendChild(link); card.appendChild(place);
      a.rows.forEach(function (r) { line(r[0], r[1], r[2]); });
      line("🔑", a.features_label, a.features.join(" | "), "lp-tg-features");
      buttons.textContent = "";
      a.buttons.forEach(function (label) { var b = document.createElement("span"); b.textContent = label; buttons.appendChild(b); });
    }
    function play() {
      var d = demos[idx % demos.length]; idx++;
      fillDemo(d);
      got.hidden = true; alertB.hidden = true; got.classList.remove("arrive"); alertB.classList.remove("arrive");
      ask.textContent = ""; body.classList.remove("fading");
      var caret = document.createElement("span"); caret.className = "lp-caret";
      var i = 0;
      (function type() {
        ask.textContent = d.ask.slice(0, i); ask.appendChild(caret);
        if (i++ < d.ask.length) { setTimeout(type, 50); return; }
        caret.remove();
        setTimeout(function () { got.hidden = false; got.classList.add("arrive"); }, 700);
        setTimeout(function () { alertB.hidden = false; alertB.classList.add("arrive"); }, 2500);
        setTimeout(function () { body.classList.add("fading"); }, 7600);
        setTimeout(play, 8000);
      })();
    }
    onView(body, play, 0.4);
  })();

  /* ---------- live data: map, numbers, feed and the hero notification ---------- */
  fetch("/api/home-map", { credentials: "omit" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) { if (data) { heroNumbers(data); hotCities(data); live(data); weekChart(data); } })
    .catch(function () { /* the rest of the page stands on its own */ });

  /* ---------- 2026-11-11 (owner: "Dorin's site looks more professional, how things move") ----------
     the hero's live numbers, the week's busiest cities, sections that rise into view and a main button that stays at
     hand on a phone. Real counts only (/api/home-map); without them nothing extra is shown. */
  function countUp(els) {
    // each number is sized to its final value first, so nothing around it moves while the digits change
    els.forEach(function (n) {
      n[0].textContent = fmt(n[1]);
      if (!reduce) { n[0].style.minWidth = Math.ceil(n[0].getBoundingClientRect().width) + "px"; n[0].textContent = fmt(0); }
    });
    if (reduce) { return; }
    var t0 = performance.now();
    (function step(t) {
      var k = Math.min(1, (t - t0) / 1600), e = 1 - Math.pow(1 - k, 3);
      els.forEach(function (n) { n[0].textContent = fmt(k < 1 ? Math.round(n[1] * e) : n[1]); });
      if (k < 1) { requestAnimationFrame(step); }
    })(t0);
  }

  function heroNumbers(data) {
    var pill = document.getElementById("lp-pill");
    var stats = document.getElementById("lp-stats");
    var fontsReady = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    fontsReady.then(function () {
      if (pill && data.new_24h > 0) {
        pill.hidden = false;
        countUp([[document.getElementById("lp-pill-n"), data.new_24h]]);
      }
      if (stats && data.week_new > 0) {
        stats.hidden = false;
        var els = Array.prototype.map.call(stats.querySelectorAll("dd[data-n]"), function (dd) {
          return [dd, Number(data[dd.getAttribute("data-n")]) || 0];
        });
        onView(stats, function () { countUp(els); }, 0.5);
      }
    });
  }

  function hotCities(data) {
    var section = document.getElementById("lp-hot");
    var list = document.getElementById("lp-hot-list");
    var rows = (data.hot || []).filter(function (r) { return r.rent + r.sale > 0; });
    if (!section || !list || rows.length < 3) { return; }
    var top = rows[0].rent + rows[0].sale;
    rows.forEach(function (r, i) {
      var li = document.createElement("li");
      var rank = document.createElement("span"); rank.className = "lp-hot-rank"; rank.textContent = String(i + 1);
      var main = document.createElement("div"); main.className = "lp-hot-main";
      var name = document.createElement("a"); name.className = "lp-hot-city"; name.textContent = r.city;
      name.href = "/rent/" + encodeURIComponent(r.city);
      var bar = document.createElement("span"); bar.className = "lp-hot-bar";
      var fillEl = document.createElement("i"); fillEl.style.setProperty("--w", Math.max(6, Math.round(100 * (r.rent + r.sale) / top)) + "%");
      bar.appendChild(fillEl);
      main.appendChild(name); main.appendChild(bar);
      var chips = document.createElement("div"); chips.className = "lp-hot-chips";
      [["rent", section.dataset.rent], ["sale", section.dataset.sale]].forEach(function (kv) {
        if (!r[kv[0]]) { return; }
        var c = document.createElement("span"); c.className = "lp-chip lp-chip-" + kv[0];
        c.textContent = kv[1] + " " + fmt(r[kv[0]]);
        chips.appendChild(c);
      });
      li.appendChild(rank); li.appendChild(main); li.appendChild(chips);
      list.appendChild(li);
    });
    section.hidden = false;
    onView(list, function () { list.classList.add("grow"); }, 0.3);
  }

  /* ---------- 2026-11-13 (owner: drawings of buildings and of Todi, a graph that builds, a card that comes apart) ---------- */

  /* the street behind the hero: windows light up as flats come in, the rows drift slower than the page on a computer,
     and Todi walks along it, stopping to sniff */
  (function street() {
    var st = document.getElementById("lp-street");
    var walker = document.getElementById("lp-walker");
    if (!st) { return; }
    var wins = st.querySelectorAll(".lp-sky-windows .w");
    var copy = document.querySelectorAll(".lp-hero-copy > *:not([hidden])");
    var pick = function () {  // a window that is on screen (the drawing is cropped on narrow screens) and not under the words
      var box = st.getBoundingClientRect();
      var words = Array.prototype.map.call(copy, function (el) { return el.getBoundingClientRect(); });
      var clear = function (r) {
        return words.every(function (t) { return r.right < t.left - 4 || r.left > t.right + 4 || r.bottom < t.top - 4 || r.top > t.bottom + 4; });
      };
      for (var tries = 0; tries < 40; tries++) {
        var w = wins[Math.floor(Math.random() * wins.length)], r = w.getBoundingClientRect();
        if (!w.classList.contains("lit") && r.left > box.left + 8 && r.right < box.right - 8 && clear(r)) { return w; }
      }
      return null;
    };
    var light = function (ms) {
      var w = pick();
      if (!w) { return; }
      w.classList.add("lit");
      if (ms) { setTimeout(function () { w.classList.remove("lit"); }, ms); }
    };
    if (wins.length) {
      if (reduce) { for (var i = 0; i < 6; i++) { light(0); } }
      else {
        [300, 900, 1700].forEach(function (d) { setTimeout(function () { light(6000 + d * 2); }, d); });
        var heard = false;
        window.addEventListener("todira:newflat", function () { heard = true; light(5200); });
        setInterval(function () { if (!heard && !document.hidden) { light(5200); } }, 4200);
      }
    }

    var hero = st.closest(".lp-hero");
    var wide = window.matchMedia("(min-width: 861px)");
    if (!reduce && hero) {  // the buildings move slower than the page (a computer only; a phone keeps them still)
      var raf = 0;
      var par = function () {
        raf = 0;
        st.style.setProperty("--lp-par", wide.matches ? Math.min(window.scrollY, hero.offsetHeight) : 0);
      };
      window.addEventListener("scroll", function () { if (!raf) { raf = requestAnimationFrame(par); } }, { passive: true });
    }

    if (!walker || !window.todiStage) { return; }
    var portrait = hero && hero.querySelector(".lp-portrait");
    var s = window.todiStage(st, walker, { speed: function () { return st.clientWidth < 700 ? 38 : 54; } });
    // where the portrait hides him (a computer only): no stops there
    var hidden = function () {
      if (!portrait || !wide.matches) { return null; }
      var a = st.getBoundingClientRect(), b = portrait.getBoundingClientRect();
      return [b.left - a.left - s.dogWidth() * 0.6, b.right - a.left - s.dogWidth() * 0.4];
    };
    var spot = function (lo, hi) {
      var zone = hidden();
      for (var tries = 0; tries < 20; tries++) {
        var x = window.todiRand(lo, hi);
        if (!zone || x < zone[0] || x > zone[1]) { return x; }
      }
      return lo;
    };
    var rtl = document.documentElement.dir === "rtl";
    if (reduce) {  // standing still by the copy's side
      var W0 = s.width(), D0 = s.dogWidth();
      s.jump(rtl ? W0 - D0 - Math.max(24, W0 * 0.08) : Math.max(24, W0 * 0.08));
      s.face(rtl ? -1 : 1);
      return;
    }
    // 2026-11-13 (owner: "I'd rather it really be Todi in 3D"): once the page is up, a 3D Todi (todi3d.js, three.js)
    // takes the drawing's place in the same walker. Only with WebGL; on any failure the drawing simply stays.
    var try3d = function () {
      var probe = document.createElement("canvas");
      if (!(probe.getContext("webgl2") || probe.getContext("webgl"))) { return; }
      import("/static/todi3d.js?v=" + (L.static_version || "")).then(function (m) { m.mountTodi3D(walker, st); })
        .catch(function () { /* the drawing stays */ });
    };
    var later = function () { if ("requestIdleCallback" in window) { requestIdleCallback(try3d, { timeout: 2500 }); } else { setTimeout(try3d, 1200); } };
    if (document.readyState === "complete") { later(); } else { window.addEventListener("load", later); }
    var fromRight = rtl;  // he comes in from the reading start
    (async function story() {
      await s.wait(1200);
      for (;;) {
        var W = s.width(), D = s.dogWidth();
        var out = fromRight ? [W + 12, -D - 12] : [-D - 12, W + 12];
        s.jump(out[0]);
        var stops = [spot(W * 0.06, W * 0.94 - D), spot(W * 0.06, W * 0.94 - D)];
        if (Math.abs(stops[0] - stops[1]) < Math.min(160, W * 0.25)) { stops.pop(); }
        stops.sort(function (a, b) { return fromRight ? b - a : a - b; });
        for (var k = 0; k < stops.length; k++) {
          await s.walkTo(stops[k]);
          var r = Math.random();
          if (r < 0.6) { await s.sniff(window.todiRand(1300, 2300)); }
          else if (r < 0.85) { await s.look(1500); }
          else { await s.wait(900); }
        }
        await s.walkTo(out[1]);
        await s.wait(window.todiRand(3500, 8000));
        fromRight = !fromRight;
      }
    })();
  })();

  /* a graph that builds itself: the week, a bar a day (rolling 24-hour windows, the newest is "the last 24 hours") */
  function weekChart(data) {
    var fig = document.getElementById("lp-week");
    var bars = document.getElementById("lp-week-bars");
    var days = data.daily || [];
    if (!fig || !bars || days.length !== 7 || !days.some(function (n) { return n > 0; })) { return; }
    var top = Math.max.apply(null, days);
    var wd;
    try { wd = new Intl.DateTimeFormat(L.lang || "he", { weekday: "short" }); } catch (e) { wd = null; }
    var now = Date.now();
    var cells = days.map(function (n, i) {
      var cell = document.createElement("div");
      cell.className = "lp-week-bar" + (i === 6 ? " now" : "");
      cell.style.setProperty("--d", (i * 0.07).toFixed(2) + "s");
      var num = document.createElement("b"); num.textContent = fmt(n);
      var bar = document.createElement("i"); bar.style.setProperty("--h", Math.max(3, Math.round(100 * n / top)) + "%");
      var day = document.createElement("span");
      day.textContent = wd ? wd.format(new Date(now - (6 - i) * 86400000)) : "";
      cell.title = fmt(n);
      cell.appendChild(num); cell.appendChild(bar); cell.appendChild(day);
      bars.appendChild(cell);
      return [num, n];
    });
    fig.hidden = false;
    onView(fig, function () {
      fig.classList.add("grow");
      if (!reduce) {  // the numbers count up as their bars rise
        var t0 = performance.now();
        cells.forEach(function (c) { c[0].textContent = fmt(0); });
        (function step(t) {
          var k = Math.min(1, (t - t0) / 1300), e = 1 - Math.pow(1 - k, 3);
          cells.forEach(function (c) { c[0].textContent = fmt(k < 1 ? Math.round(c[1] * e) : c[1]); });
          if (k < 1) { requestAnimationFrame(step); }
        })(t0);
      }
    }, 0.5);
  }

  /* the bot's card, opened into its layers: each line is checked, then it closes back into one card. Again whenever it
     comes back into view; read flat (and for reduced motion) it is just the card with every line checked. */
  (function xray() {
    var card = document.getElementById("lp-xray-card");
    if (!card || reduce || !("IntersectionObserver" in window)) { return; }
    var layers = Array.prototype.slice.call(card.querySelectorAll(".lp-xray-layer"));
    layers.forEach(function (el, i) { el.style.setProperty("--i", String(layers.length - 1 - i)); });
    card.classList.add("lp-xray-armed");
    var seen = false, playing = false;
    var later = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
    var play = async function () {
      playing = true;
      while (seen) {
        layers.forEach(function (el) { el.classList.remove("ok"); });
        card.classList.remove("match");
        await later(600);
        for (var i = 0; i < layers.length; i++) {
          layers[i].classList.add("scan");
          await later(230);
          layers[i].classList.add("ok");
          layers[i].classList.remove("scan");
          await later(160);
        }
        await later(300);
        card.classList.add("match");
        await later(4200);
      }
      playing = false;
    };
    new IntersectionObserver(function (es) {
      seen = es[es.length - 1].isIntersecting;
      if (seen && !playing) { play(); }
    }, { threshold: 0.55 }).observe(card);
  })();

  (function reveal() {
    var els = document.querySelectorAll(".lp-reveal");
    if (reduce || !("IntersectionObserver" in window) || !els.length) { return; }
    document.documentElement.classList.add("lp-motion");
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
    Array.prototype.forEach.call(els, function (el) { io.observe(el); });
  })();

  (function stickyButton() {
    var bar = document.getElementById("lp-sticky");
    var golds = document.querySelectorAll(".lp-hero .lp-btn, .lp-end .lp-btn, .lp-mycity-go");
    if (!bar || !golds.length || !("IntersectionObserver" in window)) { return; }
    var seen = new Set();
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting && !e.target.hidden) { seen.add(e.target); } else { seen.delete(e.target); } });
      var show = seen.size === 0 && window.innerWidth < 900;
      bar.hidden = !show;
      document.documentElement.classList.toggle("lp-sticky-on", show);
    });
    Array.prototype.forEach.call(golds, function (el) { io.observe(el); });
  })();

  /* ---------- your city: how many came in in the last 24 hours, and when the last one came in ----------
     2026-10-22 (owner): for every visitor, signed in or not - the flats themselves need signing in (the button goes
     through /login, which skips straight on for someone already signed in). */
  function cityCheck(data) {
    var box = document.getElementById("lp-mycity");
    if (!box || !data.by_city) { return; }
    var byCity = data.by_city;
    var names = (L.city_names || []).slice();
    Object.keys(byCity).forEach(function (c) { if (names.indexOf(c) < 0) { names.push(c); } });
    var list = document.getElementById("lp-city-list");
    names.forEach(function (c) { var o = document.createElement("option"); o.value = c; list.appendChild(o); });
    var norm = function (v) { return String(v || "").replace(/["'׳״\-]/g, " ").replace(/\s+/g, " ").trim(); };
    var find = function (v) {
      v = norm(v);
      if (!v) { return null; }
      var exact = names.filter(function (c) { return norm(c) === v; });
      if (exact.length) { return exact[0]; }
      var starts = names.filter(function (c) { return norm(c).indexOf(v) === 0; });
      return starts.length === 1 && v.length >= 2 ? starts[0] : null;
    };
    var input = document.getElementById("lp-city-in");
    var out = document.getElementById("lp-city-out");
    var go = document.getElementById("lp-city-go");
    var priceIn = document.getElementById("lp-city-price");
    var roomsIn = document.getElementById("lp-city-rooms");
    // 2026-11-04 (owner): with a budget or rooms the answer is the matching flats of today and of the last 7 days,
    // without them the 24-hour count shows at once and the week count joins it (/api/city-count)
    var asked = 0, timer = null;
    var show = function () {
      var city = find(input.value);
      var budget = priceIn ? priceIn.value.replace(/\D/g, "") : "";
      var rooms = roomsIn ? roomsIn.value : "";
      var filtered = !!(budget || rooms);
      var n = city ? byCity[city] || 0 : 0;
      clearTimeout(timer);
      asked++;
      if (!city) { out.textContent = ""; go.hidden = true; return; }
      var plain = fill(n === 0 ? S.city_result_0 : n === 1 ? S.city_result_1 : S.city_result_n, { city: city, n: fmt(n) });
      if (!filtered) { out.textContent = plain; }
      go.textContent = fill(S.city_go, { city: city });
      // 2026-11-04 (owner): straight to the flats themselves (/search shows them without signing in), with the budget
      // and rooms asked here
      go.href = "/search?cities=" + encodeURIComponent(city) + (budget ? "&price_max=" + budget : "") + (rooms ? "&rooms_min=" + rooms : "");
      if (!filtered) { go.hidden = n === 0; }
      var mine = asked;
      timer = setTimeout(function () {
        var q = "city=" + encodeURIComponent(city) + (budget ? "&price_max=" + budget : "") + (rooms ? "&rooms_min=" + rooms : "");
        fetch("/api/city-count?" + q, { credentials: "omit" })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (c) {
            if (!c || mine !== asked) { return; }
            if (filtered) {
              out.textContent = c.week === 0 ? fill(S.city_match_0, { city: city })
                : fill(S.city_match, { city: city, today: fmt(c.today), week: fmt(c.week) });
            } else if (c.week > n) {
              out.textContent = plain + " " + (c.week === 1 ? S.city_week_1 : fill(S.city_week_n, { n: fmt(c.week) }));
            }
            go.hidden = c.week === 0 && n === 0;
          })
          .catch(function () { /* the 24-hour count above stays */ });
      }, filtered ? 350 : 150);
    };
    input.addEventListener("input", show);
    input.addEventListener("change", show);
    if (priceIn) { priceIn.addEventListener("input", show); }
    if (roomsIn) { roomsIn.addEventListener("change", show); }

    // the last one in: its age is counted from its real time, again every half minute
    var last = document.getElementById("lp-last");
    var latest = data.latest;
    var at = latest && Date.parse(latest.at);
    var age = function () {
      var min = Math.max(0, Math.floor((Date.now() - at) / 60000));
      var vals = { city: latest.city };
      if (min < 1) { return fill(S.last_now, vals); }
      if (min === 1) { return fill(S.last_min_1, vals); }
      if (min < 60) { vals.n = fmt(min); return fill(S.last_min_n, vals); }
      var h = Math.floor(min / 60);
      if (h === 1) { return fill(S.last_hour_1, vals); }
      vals.n = fmt(h); return fill(S.last_hour_n, vals);
    };
    if (at && !isNaN(at)) {
      last.textContent = age();
      setInterval(function () { last.textContent = age(); }, 30000);
    } else {
      last.hidden = true;
    }
    box.hidden = false;
  }

  /* ---------- the map ----------
     One even grid of dots in the shape of the country, so the Negev and the Arava are there even where few people
     list. It is painted once on a canvas: a dot grows and deepens with the live listings around it and glows gold
     where something came in during the last day. The sparkles and the ping are small elements the browser moves on
     its own, so nothing is repainted while they play. */
  var OUTLINE = [  // [lng, lat], clockwise from Rosh HaNikra; the Gaza Strip is left out
    [35.105, 33.093], [35.23, 33.095], [35.37, 33.07], [35.47, 33.09], [35.52, 33.11], [35.54, 33.21], [35.575, 33.28],
    [35.65, 33.25], [35.74, 33.29], [35.8, 33.33], [35.83, 33.2], [35.81, 33.12], [35.85, 33.0], [35.87, 32.88],
    [35.83, 32.78], [35.76, 32.71], [35.66, 32.68], [35.58, 32.65], [35.57, 32.5], [35.55, 32.3], [35.53, 32.1],
    [35.5, 31.9], [35.55, 31.76], [35.53, 31.55], [35.5, 31.3], [35.48, 31.12], [35.42, 31.0], [35.33, 30.8],
    [35.22, 30.55], [35.16, 30.3], [35.08, 30.05], [35.02, 29.75], [34.98, 29.55], [34.9, 29.49], [34.88, 29.6],
    [34.78, 29.9], [34.65, 30.25], [34.53, 30.55], [34.42, 30.88], [34.33, 31.05], [34.27, 31.22], [34.38, 31.3],
    [34.46, 31.4], [34.54, 31.5], [34.56, 31.55], [34.49, 31.595], [34.53, 31.63], [34.56, 31.7], [34.62, 31.8],
    [34.69, 31.92], [34.74, 32.03], [34.77, 32.1], [34.8, 32.2], [34.84, 32.32], [34.87, 32.45], [34.89, 32.55],
    [34.92, 32.65], [34.95, 32.75], [34.96, 32.83], [35.02, 32.82], [35.07, 32.9], [35.07, 32.95], [35.09, 33.02],
  ];
  var LNG0 = 34.2, LNG1 = 35.95, LAT0 = 33.38, LAT1 = 29.42, K = Math.cos(31.4 * Math.PI / 180);
  var STEP = 0.05, ROW = STEP * 0.866;  // about 5.5 km between dots, every other row shifted by half
  var PW = (LNG1 - LNG0) * K, PH = LAT0 - LAT1;
  var proj = function (lat, lng) { return [(lng - LNG0) * K, LAT0 - lat]; };
  var pct = function (v, of) { return (v / of * 100).toFixed(2) + "%"; };
  var inside = function (lng, lat) {
    var v = false;
    for (var i = 0, j = OUTLINE.length - 1; i < OUTLINE.length; j = i++) {
      var a = OUTLINE[i], b = OUTLINE[j];
      if ((a[1] > lat) !== (b[1] > lat) && lng < (b[0] - a[0]) * (lat - a[1]) / (b[1] - a[1]) + a[0]) { v = !v; }
    }
    return v;
  };

  function drawMap(box, grid) {
    var cells = {};
    var cell = function (r, c) {
      var key = r + ":" + c;
      return cells[key] || (cells[key] = { x: c * STEP + (r % 2 ? STEP / 2 : 0), y: r * ROW, n: 0, f: 0 });
    };
    for (var r = 0; r * ROW <= PH; r++) {
      for (var c = 0; c * STEP <= PW; c++) {
        if (inside(LNG0 + (c * STEP + (r % 2 ? STEP / 2 : 0)) / K, LAT0 - r * ROW)) { cell(r, c); }
      }
    }
    grid.forEach(function (g) {  // each listing square goes to its nearest dot
      var p = proj(g[0], g[1]), r = Math.round(p[1] / ROW), o = cell(r, Math.round((p[0] - (r % 2 ? STEP / 2 : 0)) / STEP));
      o.n += g[2]; o.f += g[3];
    });
    var list = Object.keys(cells).map(function (k) { return cells[k]; });
    var lnN = Math.log(1 + list.reduce(function (m, o) { return Math.max(m, o.n); }, 1));
    var lnF = Math.log(1 + list.reduce(function (m, o) { return Math.max(m, o.f); }, 1));
    list.forEach(function (o) { o.t = Math.log(1 + o.n) / lnN; o.u = Math.log(1 + o.f) / lnF; });
    var fresh = list.filter(function (o) { return o.f > 0; }).sort(function (a, b) { return a.f - b.f; });  // brightest on top

    var canvas = document.createElement("canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", S.map_label || "");
    var layer = document.createElement("div");
    layer.className = "lp-map-layer";
    layer.setAttribute("aria-hidden", "true");
    box.appendChild(canvas);
    box.appendChild(layer);
    var at = function (node, lat, lng) { var p = proj(lat, lng); node.style.left = pct(p[0], PW); node.style.top = pct(p[1], PH); };
    (L.cities || []).forEach(function (c) {
      var s = document.createElement("span");
      s.className = "lp-city" + (c.side === "e" ? " e" : "");
      s.textContent = c.name;
      at(s, c.lat, c.lng);
      layer.appendChild(s);
    });
    var picked = [];  // sparkles over the busiest new places, kept apart from each other
    for (var i = fresh.length - 1; i >= 0 && picked.length < 9; i--) {
      var o = fresh[i];
      if (picked.every(function (q) { return Math.abs(q.x - o.x) + Math.abs(q.y - o.y) > STEP * 5; })) { picked.push(o); }
    }
    picked.forEach(function (o, k) {
      var s = document.createElement("i");
      s.className = "lp-spark";
      s.style.left = pct(o.x, PW); s.style.top = pct(o.y, PH);
      s.style.setProperty("--td", (k * 0.83 % 3.1).toFixed(2) + "s");
      layer.appendChild(s);
    });
    var ringEl = document.createElement("i");
    ringEl.className = "lp-ring";
    ringEl.hidden = true;
    layer.appendChild(ringEl);
    // 2026-11-13 (owner: pins on the map): the newest flat drops in as a pin, and a line runs to it from the one before
    var NS = "http://www.w3.org/2000/svg";
    var route = document.createElementNS(NS, "svg");
    route.setAttribute("class", "lp-route");
    route.setAttribute("viewBox", "0 0 " + PW + " " + PH);
    route.setAttribute("preserveAspectRatio", "none");
    var routePath = document.createElementNS(NS, "path");
    routePath.setAttribute("pathLength", "1");
    routePath.setAttribute("vector-effect", "non-scaling-stroke");
    route.appendChild(routePath);
    layer.appendChild(route);
    var pinEl = document.createElement("i");
    pinEl.className = "lp-pin";
    pinEl.hidden = true;
    pinEl.innerHTML = '<svg viewBox="0 0 22 30"><path class="lp-pin-head" d="M11 29C11 29 1.5 18.2 1.5 10.9a9.5 9.5 0 0 1 19 0C20.5 18.2 11 29 11 29z"/><circle class="lp-pin-dot" cx="11" cy="11" r="3.6"/></svg>';
    layer.appendChild(pinEl);
    var lastPin = null;

    var ctx = canvas.getContext("2d"), sc = 0, front = -1, sprite = null, spriteFor = "";
    var size = function () {
      var w = box.clientWidth, dpr = Math.min(window.devicePixelRatio || 1, 2);
      sc = w / PW;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(PH * sc * dpr);
      canvas.style.height = Math.round(PH * sc) + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    var glowSprite = function (color) {  // a soft round light, drawn once and stamped for every new place
      var c = document.createElement("canvas"), g = c.getContext("2d"), grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
      c.width = c.height = 64;
      g.fillStyle = color; g.fillRect(0, 0, 64, 64);
      grad.addColorStop(0, "rgba(0,0,0,1)"); grad.addColorStop(0.22, "rgba(0,0,0,.62)");
      grad.addColorStop(0.5, "rgba(0,0,0,.2)"); grad.addColorStop(1, "rgba(0,0,0,0)");
      g.globalCompositeOperation = "destination-in"; g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
      return c;
    };
    var paint = function () {
      if (!sc || front < 0) { return; }
      var cs = getComputedStyle(box), v = function (n) { return cs.getPropertyValue(n).trim(); };
      var land = v("--lp-land"), landA = +v("--lp-land-a"), old = v("--lp-dot-old"), oldA = +v("--lp-dot-old-a");
      var core = v("--lp-new"), hot = v("--lp-new-hot"), glow = v("--lp-glow"), glowA = +v("--lp-glow-a");
      if (spriteFor !== glow) { sprite = glowSprite(glow); spriteFor = glow; }
      var d = STEP * sc;
      var seen = function (o) { var k = (front - o.y) / 0.3; return k >= 1 ? 1 : k <= 0 ? 0 : k; };  // the sweep's soft edge
      var dot = function (o, rad) { ctx.beginPath(); ctx.arc(o.x * sc, o.y * sc, rad, 0, 6.2832); ctx.fill(); };
      ctx.clearRect(0, 0, PW * sc, PH * sc);
      ctx.fillStyle = land;
      list.forEach(function (o) { var a = seen(o); if (a && !o.n) { ctx.globalAlpha = landA * a; dot(o, d * 0.15); } });
      ctx.fillStyle = old;
      list.forEach(function (o) { var a = seen(o); if (a && o.n) { ctx.globalAlpha = (oldA + (0.95 - oldA) * o.t) * a; dot(o, d * (0.19 + 0.17 * o.t)); } });
      ctx.globalCompositeOperation = v("--lp-glow-add") === "1" ? "lighter" : "source-over";
      fresh.forEach(function (o) {
        var a = seen(o), gr = d * (0.95 + 1.5 * o.u);
        if (a) { ctx.globalAlpha = glowA * (0.4 + 0.6 * o.u) * a; ctx.drawImage(sprite, o.x * sc - gr, o.y * sc - gr, gr * 2, gr * 2); }
      });
      ctx.globalCompositeOperation = "source-over";
      fresh.forEach(function (o) {
        var a = seen(o);
        if (!a) { return; }
        var rad = d * (0.22 + 0.16 * o.u);
        ctx.globalAlpha = a; ctx.fillStyle = core; dot(o, rad);
        if (o.u > 0.55) { ctx.globalAlpha = a * (o.u - 0.55) / 0.45; ctx.fillStyle = hot; dot(o, rad); }  // the busiest burn hotter
      });
      ctx.globalAlpha = 1;
    };
    size();
    var lastW = box.clientWidth;
    var refit = function () { if (box.clientWidth && box.clientWidth !== lastW) { lastW = box.clientWidth; size(); paint(); } };
    if ("ResizeObserver" in window) { new ResizeObserver(refit).observe(box); } else { window.addEventListener("resize", refit); }
    new MutationObserver(paint).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    var dark = window.matchMedia("(prefers-color-scheme: dark)");
    if (dark.addEventListener) { dark.addEventListener("change", paint); }

    return {
      reveal: function () {  // the dots come in from north to south, then the names and the sparkles
        box.classList.add("lp-on");
        if (reduce) { front = PH + 1; paint(); return; }
        var t0 = performance.now();
        (function step(t) {
          var k = Math.min(1, (t - t0) / 1500);
          front = (PH + 0.3) * (1 - Math.pow(1 - k, 2));
          paint();
          if (k < 1) { requestAnimationFrame(step); }
        })(t0);
      },
      ping: function (lat, lng) {  // a ring, a pin and a line where the newest listing in the feed is
        at(ringEl, lat, lng);
        ringEl.hidden = false;
        ringEl.classList.remove("go");
        at(pinEl, lat, lng);
        pinEl.hidden = false;
        pinEl.classList.remove("go");
        var p = proj(lat, lng);
        routePath.classList.remove("go");
        if (lastPin && Math.abs(lastPin[0] - p[0]) + Math.abs(lastPin[1] - p[1]) > STEP) {
          // a gentle arc: the control point sits off the straight line, to the side of travel
          var mx = (lastPin[0] + p[0]) / 2, my = (lastPin[1] + p[1]) / 2, dx = p[0] - lastPin[0], dy = p[1] - lastPin[1];
          var cx = mx - dy * 0.35, cy = my + dx * 0.35;
          routePath.setAttribute("d", "M" + lastPin[0].toFixed(4) + " " + lastPin[1].toFixed(4) + "Q" + cx.toFixed(4) + " " +
            cy.toFixed(4) + " " + p[0].toFixed(4) + " " + p[1].toFixed(4));
        } else {
          routePath.removeAttribute("d");
        }
        lastPin = p;
        void ringEl.offsetWidth;
        ringEl.classList.add("go");
        pinEl.classList.add("go");
        if (routePath.getAttribute("d")) { routePath.classList.add("go"); }
      },
    };
  }

  function live(data) {
    var items = (data.recent || []).filter(function (it) { return it.price >= 1000; });

    // one notification at a time, dropping in from the top like a phone's, then the next one
    var notif = document.getElementById("lp-notif");
    if (notif && items.length) {
      var setNotif = function (it) {
        window.dispatchEvent(new CustomEvent("todira:newflat"));
        document.getElementById("lp-notif-what").textContent = fill(S.notif_title, { city: it.city });
        document.getElementById("lp-notif-detail").textContent = fill(S.notif_detail, { rooms: roomsText(it.rooms), price: fmt(it.price) });
      };
      var n = 0;
      setNotif(items[n]);
      notif.classList.add("out");
      notif.hidden = false;
      if (reduce) { notif.classList.remove("out"); }
      else {
        requestAnimationFrame(function () { requestAnimationFrame(function () { notif.classList.remove("out"); }); });
        setInterval(function () {
          notif.classList.add("out");
          setTimeout(function () {
            n = (n + 1) % items.length;
            setNotif(items[n]);
            notif.classList.remove("out");
          }, 520);
        }, 4200);
      }
    }

    var section = document.getElementById("lp-live");
    if (!section || !(data.grid || []).length) { return; }
    section.hidden = false;
    var mapEl = document.getElementById("lp-map");
    var map = drawMap(mapEl, data.grid);

    // the numbers count up when they come into view. Each one is sized to its final value first, so the sentence
    // around it is laid out once and never moves while the digits change.
    var nums = [[document.getElementById("lp-n-new"), data.new_24h || 0], [document.getElementById("lp-n-cities"), data.cities_24h || 0]];
    var fontsReady = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    fontsReady.then(function () {
      nums.forEach(function (n) {
        n[0].textContent = fmt(n[1]);
        if (!reduce) { n[0].style.minWidth = "calc(" + Math.ceil(n[0].getBoundingClientRect().width) + "px + .15em)"; n[0].textContent = fmt(0); }
      });
      onView(section.querySelector("h2"), function () {
        if (reduce) { return; }
        var t0 = performance.now();
        (function step(t) {
          var k = Math.min(1, (t - t0) / 1400), e = 1 - Math.pow(1 - k, 3);
          nums.forEach(function (n) { n[0].textContent = fmt(k < 1 ? Math.round(n[1] * e) : n[1]); });
          if (k < 1) { requestAnimationFrame(step); }
        })(t0);
      }, 0.6);
    });
    onView(mapEl, map.reveal, 0.15);
    cityCheck(data);

    // the feed: the newest rentals; each one lights its own place on the map
    var feed = document.getElementById("lp-feed");
    var addFeed = function (it, animate) {
      var li = document.createElement("li");
      var b = document.createElement("b"); b.textContent = it.city;
      var s = document.createElement("span"); s.textContent = roomsText(it.rooms) + ", " + fmt(it.price) + " ₪";
      li.appendChild(b); li.appendChild(s);
      Array.prototype.forEach.call(feed.querySelectorAll("li.fresh"), function (e) { e.classList.remove("fresh"); });
      if (animate) { li.classList.add("fresh"); }
      feed.insertBefore(li, feed.firstChild);
      while (feed.children.length > 5) { feed.removeChild(feed.lastChild); }
      map.ping(it.lat, it.lng);
    };
    if (!items.length) { feed.parentNode.hidden = true; return; }
    for (var k = Math.min(4, items.length - 1); k >= 0; k--) { addFeed(items[k], false); }
    if (!reduce && items.length > 5) {
      var next = 5;
      setInterval(function () { addFeed(items[next % items.length], true); next++; }, 3000);
    }
  }
})();
