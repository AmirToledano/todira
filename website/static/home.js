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
    .then(function (data) { if (data) { live(data); } })
    .catch(function () { /* the rest of the page stands on its own */ });

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
    var show = function () {
      var city = find(input.value);
      if (!city) { out.textContent = ""; go.hidden = true; return; }
      var n = byCity[city] || 0;
      out.textContent = fill(n === 0 ? S.city_result_0 : n === 1 ? S.city_result_1 : S.city_result_n, { city: city, n: fmt(n) });
      go.textContent = fill(S.city_go, { city: city });
      // signed in: /login goes straight on; otherwise it asks to sign in first, then shows that city's flats
      go.href = "/login?next=" + encodeURIComponent("/apartments?city=" + encodeURIComponent(city));
      go.hidden = n === 0;
    };
    input.addEventListener("input", show);
    input.addEventListener("change", show);

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
      ping: function (lat, lng) {  // a ring where the newest listing in the feed is
        at(ringEl, lat, lng);
        ringEl.hidden = false;
        ringEl.classList.remove("go");
        void ringEl.offsetWidth;
        ringEl.classList.add("go");
      },
    };
  }

  function live(data) {
    var items = (data.recent || []).filter(function (it) { return it.price >= 1000; });

    // one notification at a time, dropping in from the top like a phone's, then the next one
    var notif = document.getElementById("lp-notif");
    if (notif && items.length) {
      var setNotif = function (it) {
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
