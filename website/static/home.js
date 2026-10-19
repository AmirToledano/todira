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
    var steps = Array.prototype.slice.call(document.querySelectorAll("#lp-steps li"));
    var on = function (i) { steps.forEach(function (s, k) { s.classList.toggle("on", k === i); }); };
    if (reduce) { return; }  // the first conversation is already in the page, complete
    var idx = 0;
    function fillDemo(d) {
      chips.innerHTML = "";
      d.chips.forEach(function (c) { var s = document.createElement("span"); s.textContent = c; chips.appendChild(s); });
      document.getElementById("lp-d-title").textContent = d.title;
      document.getElementById("lp-d-price").textContent = d.price;
      document.getElementById("lp-d-detail").textContent = d.detail;
      document.getElementById("lp-d-street").textContent = d.street;
    }
    function play() {
      var d = demos[idx % demos.length]; idx++;
      fillDemo(d);
      got.hidden = true; alertB.hidden = true; got.classList.remove("arrive"); alertB.classList.remove("arrive");
      ask.textContent = ""; on(0); body.classList.remove("fading");
      var caret = document.createElement("span"); caret.className = "lp-caret";
      var i = 0;
      (function type() {
        ask.textContent = d.ask.slice(0, i); ask.appendChild(caret);
        if (i++ < d.ask.length) { setTimeout(type, 50); return; }
        caret.remove();
        setTimeout(function () { on(1); got.hidden = false; got.classList.add("arrive"); }, 700);
        setTimeout(function () { on(2); alertB.hidden = false; alertB.classList.add("arrive"); }, 2500);
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

    // the map: Israel drawn only from where listings are, projected with the latitude's cosine so it keeps its shape
    var LNG0 = 34.25, LAT0 = 33.35, K = Math.cos(31.4 * Math.PI / 180), SC = 300;
    var W = Math.round(1.7 * K * SC), H = Math.round(3.9 * SC);
    var xy = function (lat, lng) { return [(lng - LNG0) * K * SC, (LAT0 - lat) * SC]; };
    var NS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", S.map_label || "");
    svg.innerHTML = '<defs><filter id="lp-glow" x="-50%" y="-50%" width="200%" height="200%">' +
      '<feGaussianBlur in="SourceGraphic" stdDeviation="3.6" result="b"/><feFlood class="glow-flood"/>' +
      '<feComposite in2="b" operator="in" result="g"/><feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge>' +
      "</filter></defs>";
    var el = function (tag, attrs, parent) {
      var e = document.createElementNS(NS, tag);
      Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
      (parent || svg).appendChild(e);
      return e;
    };
    var delay = function (y) { return (y / H * 1.6).toFixed(2) + "s"; };  // the sweep runs north to south
    data.grid.forEach(function (g) {
      var p = xy(g[0], g[1]);
      el("circle", { cx: p[0].toFixed(1), cy: p[1].toFixed(1), r: Math.min(4.6, 2 + Math.sqrt(g[2]) * 0.2).toFixed(2), "class": "old", style: "--d:" + delay(p[1]) });
    });
    var fresh = data.grid.filter(function (g) { return g[3] > 0; }).sort(function (a, b) { return b[3] - a[3]; });
    var seed = 7;
    var rnd = function () { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
    var newG = document.createElementNS(NS, "g");
    newG.setAttribute("filter", "url(#lp-glow)");
    fresh.forEach(function (g) {
      var p = xy(g[0], g[1]);
      var r = Math.min(4.8, 2.1 + Math.sqrt(g[3]) * 0.45);
      el("circle", {
        cx: p[0].toFixed(1), cy: p[1].toFixed(1), r: r.toFixed(2), "class": "new" + (rnd() < 0.4 ? " twinkle" : ""),
        style: "--d:" + delay(p[1]) + ";--tw:" + (2 + rnd() * 2.5).toFixed(2) + "s;--td:" + (1.6 + rnd() * 3).toFixed(2) + "s",
      }, newG);
    });
    svg.appendChild(newG);
    fresh.slice(0, 14).forEach(function (g) {  // four-point glints over the busiest places
      var p = xy(g[0], g[1]), x = p[0], y = p[1], s = 9;
      el("path", {
        d: "M" + x + " " + (y - s) + " Q" + x + " " + y + " " + (x + s) + " " + y + " Q" + x + " " + y + " " + x + " " + (y + s) +
          " Q" + x + " " + y + " " + (x - s) + " " + y + " Q" + x + " " + y + " " + x + " " + (y - s) + "Z",
        "class": "glint", style: "--td:" + (rnd() * 2.8).toFixed(2) + "s",
      });
    });
    (L.cities || []).forEach(function (c) {  // labels out at sea, joined to their city by a short line
      var p = xy(c.lat, c.lng), lx = Math.min(p[0], 52) - 10;
      el("line", { x1: (p[0] - 5).toFixed(1), y1: p[1].toFixed(1), x2: (lx + 4).toFixed(1), y2: p[1].toFixed(1), "class": "tick" });
      var t = el("text", { x: lx.toFixed(1), y: (p[1] + 5).toFixed(1), "class": "city", "text-anchor": "end" });
      t.textContent = c.name;
    });
    var ping = el("circle", { cx: -50, cy: -50, r: 9, "class": "ping" });
    var mapEl = document.getElementById("lp-map");
    mapEl.appendChild(svg);

    // the numbers count up when they come into view
    var countUp = function (node, to) {
      if (reduce) { node.textContent = fmt(to); return; }
      var t0 = performance.now();
      (function step(t) {
        var k = Math.min(1, (t - t0) / 1600);
        node.textContent = fmt(Math.round(to * (1 - Math.pow(1 - k, 3))));
        if (k < 1) { requestAnimationFrame(step); }
      })(t0);
    };
    onView(mapEl, function () {
      mapEl.classList.remove("lp-sweep"); mapEl.classList.add("lp-swept");
      countUp(document.getElementById("lp-n-new"), data.new_24h || 0);
      countUp(document.getElementById("lp-n-cities"), data.cities_24h || 0);
    }, 0.15);

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
      var p = xy(it.lat, it.lng);
      ping.setAttribute("cx", p[0].toFixed(1)); ping.setAttribute("cy", p[1].toFixed(1));
    };
    if (!items.length) { feed.parentNode.hidden = true; return; }
    for (var k = Math.min(4, items.length - 1); k >= 0; k--) { addFeed(items[k], false); }
    if (!reduce && items.length > 5) {
      var next = 5;
      setInterval(function () { addFeed(items[next % items.length], true); next++; }, 3000);
    }
  }
})();
