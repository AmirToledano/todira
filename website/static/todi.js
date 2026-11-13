/* 2026-11-13 (owner: drawings and motion of Todi on the site): moves the drawn Todi (templates/_todi_dog.html) along
   a stage. window.todiStage(stage, walker) gives a small set of steps, each a promise: walkTo(x), sniff(ms), look(ms),
   wait(ms), jump(x). The page writes its own little story with them (home.js for the hero street, the 404 page for
   the lost dog). Every step is a Web Animation, so the whole story pauses while the stage is off screen or the tab is
   hidden, and nothing runs at all for reduced motion or the accessibility menu's "stop motion". */
(function () {
  "use strict";
  window.todiReduce = function () {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
      document.documentElement.classList.contains("a11y-no-motion");
  };

  window.todiStage = function (stage, walker, opts) {
    opts = opts || {};
    var dog = walker.querySelector(".todi-dog");
    var x = 0, facing = -1, current = null, visible = true, stopped = false;
    var speed = function () { return typeof opts.speed === "function" ? opts.speed() : opts.speed || 50; };
    var place = function () { walker.style.transform = "translateX(" + x + "px)"; };
    var face = function (dir) {  // the drawing looks to the left (-1); +1 flips it
      facing = dir;
      dog.style.transform = dir > 0 ? "scaleX(-1)" : "";
    };
    var run = function (anim) {
      current = anim;
      if (!visible) { anim.pause(); }
      return anim.finished.then(function () { if (current === anim) { current = null; } }, function () {});
    };
    var hold = function (ms) { return run(walker.animate([{ opacity: 1 }, { opacity: 1 }], { duration: ms })); };
    var api = {
      width: function () { return stage.clientWidth; },
      dogWidth: function () { return walker.offsetWidth; },
      x: function () { return x; },
      jump: function (to) { x = to; place(); },
      walkTo: function (to) {
        if (stopped) { return new Promise(function () {}); }
        var from = x, dist = Math.abs(to - from);
        if (dist < 1) { return Promise.resolve(); }
        face(to > from ? 1 : -1);
        dog.classList.add("is-walking");
        x = to;
        var anim = walker.animate(
          [{ transform: "translateX(" + from + "px)" }, { transform: "translateX(" + to + "px)" }],
          { duration: dist / speed() * 1000, easing: "linear", fill: "forwards" }
        );
        return run(anim).then(function () { place(); anim.cancel(); dog.classList.remove("is-walking"); });
      },
      sniff: function (ms) {
        dog.classList.add("is-sniffing");
        return hold(ms).then(function () { dog.classList.remove("is-sniffing"); });
      },
      look: function (ms) {
        dog.classList.add("is-looking");
        return hold(ms).then(function () { dog.classList.remove("is-looking"); });
      },
      wait: hold,
      face: face,
      facing: function () { return facing; },
      stop: function () { stopped = true; if (current) { current.cancel(); } },
    };
    var setVisible = function (v) {
      visible = v;
      stage.classList.toggle("td-paused", !v);
      if (current) { if (v) { current.play(); } else { current.pause(); } }
    };
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) { setVisible(es[es.length - 1].isIntersecting && !document.hidden); }).observe(stage);
    }
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { setVisible(false); }
      else {
        var r = stage.getBoundingClientRect();
        setVisible(r.bottom > 0 && r.top < window.innerHeight);
      }
    });
    place();
    return api;
  };

  window.todiRand = function (a, b) { return a + Math.random() * (b - a); };
})();
