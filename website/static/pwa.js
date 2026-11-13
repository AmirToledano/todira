/* Todira as an app on the home screen (2026-11-07, owner: "a + button that adds an icon to the home screen, shown only
   to people who don't have it yet, and when opened from the icon it must behave like an app: no zoom, no long-press
   selecting or copying or saving pictures. In the browser all of that stays as it is").

   Two halves:
   - In the app (opened from the home screen icon): the <head> script in base.html already marked <html class="is-app">
     and turned off zoom in the viewport. Here: no long-press menu or picture dragging (except in fields), no pinch on
     iOS, and remember on this device that the app is installed.
   - In the browser: the "+" button at the bottom of the screen, unless the app is installed (Android/Chrome tell us)
     or the person said they added it (iPhone gives a site no way to know) or closed the button lately. Android and
     desktop Chrome open their own install question; an iPhone or another browser gets a short sheet with the steps.
   The service worker (/sw.js) is what lets Android offer the install, and shows a page of its own when offline. */
(function () {
  var INSTALLED = 'todira-app-installed';
  var CLOSED_AT = 'todira-app-button-closed';
  var CLOSED_DAYS = 7;
  var root = document.documentElement;

  function get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private mode: this visit only */ } }

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () { navigator.serviceWorker.register('/sw.js').catch(function () {}); });
  }

  function editable(el) {
    return !!(el && el.closest && el.closest('input, textarea, select, [contenteditable="true"]'));
  }

  if (root.classList.contains('is-app')) {
    set(INSTALLED, '1');
    document.addEventListener('contextmenu', function (e) { if (!editable(e.target)) { e.preventDefault(); } });
    document.addEventListener('dragstart', function (e) { if (!editable(e.target)) { e.preventDefault(); } });
    // iOS lets a home screen app pinch-zoom whatever the viewport says; these stop the pinch itself.
    ['gesturestart', 'gesturechange'].forEach(function (name) {
      document.addEventListener(name, function (e) { e.preventDefault(); }, { passive: false });
    });
    document.addEventListener('touchmove', function (e) {
      if (e.scale !== undefined && e.scale !== 1) { e.preventDefault(); }
    }, { passive: false });
    return;
  }

  var button = document.getElementById('app-add');
  var sheet = document.getElementById('app-sheet');
  if (!button || !sheet) { return; }

  var ua = navigator.userAgent || '';
  var ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  var phone = ios || /Android/.test(ua) || (window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
  var promptEvent = null;

  function closedLately() {
    var at = parseInt(get(CLOSED_AT) || '0', 10);
    return at && (Date.now() - at) < CLOSED_DAYS * 864e5;
  }

  function hide() { button.hidden = true; }

  function lift() {
    // stay above the cookie line while it is shown
    var notice = document.getElementById('cookie-notice');
    var high = notice && !notice.hidden ? notice.offsetHeight + 12 : 0;
    // 2026-11-13 (owner): it sits in the same row as the round corner buttons (accessibility, assistant), between them
    button.style.setProperty('--app-add-lift', high + 'px');
  }

  function show() {
    if (get(INSTALLED) || closedLately()) { return; }
    button.hidden = false;
    lift();
  }

  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    promptEvent = e;
    show();
  });

  window.addEventListener('appinstalled', function () {
    set(INSTALLED, '1');
    hide();
    closeSheet();
  });

  function openSheet() {
    sheet.querySelector('[data-steps="ios"]').hidden = !ios;
    sheet.querySelector('[data-steps="other"]').hidden = ios;
    sheet.hidden = false;
    var first = sheet.querySelector('button');
    if (first) { first.focus(); }
  }

  function closeSheet() { sheet.hidden = true; }

  button.querySelector('.app-add-main').addEventListener('click', function () {
    if (promptEvent) {
      var ev = promptEvent;
      promptEvent = null;
      ev.prompt();
      ev.userChoice.then(function (choice) {
        if (choice && choice.outcome === 'accepted') { set(INSTALLED, '1'); hide(); }
      }).catch(function () {});
      return;
    }
    openSheet();
  });

  button.querySelector('.app-add-close').addEventListener('click', function () {
    set(CLOSED_AT, String(Date.now()));
    hide();
  });

  sheet.addEventListener('click', function (e) {
    if (e.target === sheet || e.target.closest('[data-sheet-later]')) { closeSheet(); }
    if (e.target.closest('[data-sheet-done]')) { set(INSTALLED, '1'); closeSheet(); hide(); }
  });

  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !sheet.hidden) { closeSheet(); } });

  var dismiss = document.getElementById('cookie-notice-dismiss');
  if (dismiss) { dismiss.addEventListener('click', function () { setTimeout(lift, 0); }); }

  // Android Chrome can say the app is already on this phone (manifest related_applications)
  if (navigator.getInstalledRelatedApps) {
    navigator.getInstalledRelatedApps().then(function (apps) {
      if (apps && apps.length) { set(INSTALLED, '1'); hide(); }
    }).catch(function () {});
  }

  // A phone without the browser's own install question (iPhone, Firefox, Samsung and others) gets the steps instead.
  // Desktop only shows the button when the browser offers to install.
  if (phone) { setTimeout(function () { if (!promptEvent) { show(); } }, 1200); }
})();
