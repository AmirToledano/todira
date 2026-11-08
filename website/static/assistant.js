// 2026-10-23: the site assistant's chat (templates/_assistant.html, main.py /api/assistant). The chat lives only in this
// page; each question sends the conversation so far, and nothing is stored on the server.
// 2026-11-09 (owner): an answer may come with buttons to the pages it points to. The chat is kept in this tab
// (sessionStorage), so after a button opens another page the conversation is still there, and the panel opens again.
(function () {
  var root = document.getElementById('assistant');
  if (!root) { return; }
  var openBtn = root.querySelector('.asst-open');
  var panel = root.querySelector('.asst-panel');
  var closeBtn = root.querySelector('.asst-close');
  var log = root.querySelector('.asst-log');
  var form = root.querySelector('.asst-form');
  var input = form.querySelector('textarea');
  var chips = root.querySelector('.asst-chips');
  var resetBtn = root.querySelector('.asst-reset');
  var startHtml = log.innerHTML;  // the greeting and the first questions, for "new chat"
  var history = [];
  var entries = [];  // what the log shows after the greeting: {who, text, actions}
  var busy = false;
  var STORE = 'todira_assistant';

  function save(reopen) {
    try {
      sessionStorage.setItem(STORE, JSON.stringify({ history: history, entries: entries, reopen: !!reopen }));
    } catch (e) { /* private mode or storage off: the chat just isn't kept */ }
  }

  function safeUrl(url) {
    return typeof url === 'string' && ((url.charAt(0) === '/' && url.charAt(1) !== '/') || url.indexOf('https://t.me/') === 0);
  }

  function addActions(actions) {
    var good = (actions || []).filter(function (a) { return a && a.label && safeUrl(a.url); });
    if (!good.length) { return; }
    var box = document.createElement('div');
    box.className = 'asst-actions';
    good.forEach(function (a) {
      var link = document.createElement('a');
      link.className = 'asst-go';
      link.href = a.url;
      link.textContent = a.label;
      if (a.url.indexOf('https://') === 0) { link.target = '_blank'; link.rel = 'noopener'; }
      box.appendChild(link);
    });
    log.appendChild(box);
  }

  function setOpen(open) {
    panel.hidden = !open;
    openBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    root.classList.toggle('is-open', open);
    if (open) { setTimeout(function () { input.focus(); }, 50); }
  }
  openBtn.addEventListener('click', function () { setOpen(panel.hidden); });
  closeBtn.addEventListener('click', function () { setOpen(false); openBtn.focus(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) { setOpen(false); } });

  function add(text, who) {
    var p = document.createElement('p');
    p.className = 'asst-msg ' + (who === 'user' ? 'asst-user' : 'asst-bot');
    p.textContent = text;
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
    return p;
  }

  function ask(text) {
    text = (text || '').trim();
    if (!text || busy) { return; }
    busy = true;
    log.querySelectorAll('.asst-chips').forEach(function (c) { c.remove(); });
    chips = null;
    add(text, 'user');
    history.push({ role: 'user', text: text });
    var waiting = add(root.getAttribute('data-thinking'), 'bot');
    waiting.classList.add('asst-wait');
    fetch(root.getAttribute('data-endpoint'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ messages: history.slice(-10) })
    }).then(function (r) { return r.json(); }).then(function (data) {
      var reply = (data && data.reply) || root.getAttribute('data-unavailable');
      var actions = (data && data.actions) || [];
      waiting.classList.remove('asst-wait');
      waiting.textContent = reply;
      history.push({ role: 'assistant', text: reply });
      entries.push({ who: 'user', text: text }, { who: 'bot', text: reply, actions: actions });
      save(false);
      addActions(actions);
      // 2026-11-02 (owner): follow-up questions after every answer
      var more = (data && data.suggestions) || [];
      if (more.length) {
        var box = document.createElement('div');
        box.className = 'asst-chips';
        more.forEach(function (q) {
          var b = document.createElement('button');
          b.type = 'button'; b.className = 'asst-chip'; b.textContent = q;
          box.appendChild(b);
        });
        log.appendChild(box);
      }
    }).catch(function () {
      waiting.classList.remove('asst-wait');
      waiting.textContent = root.getAttribute('data-unavailable');
    }).then(function () {
      busy = false;
      log.scrollTop = log.scrollHeight;
    });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = input.value;
    input.value = '';
    input.style.height = '';
    ask(text);
  });
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event('submit')); }
  });
  input.addEventListener('input', function () {
    input.style.height = '';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });
  log.addEventListener('click', function (e) {
    var go = e.target.closest('.asst-go');
    if (go && go.target !== '_blank') { save(true); return; }  // same site: open the chat again on the next page
    var chip = e.target.closest('.asst-chip');
    if (chip && !busy) { ask(chip.textContent); }
  });
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      if (busy) { return; }
      history = [];
      entries = [];
      save(false);
      log.innerHTML = startHtml;
      chips = log.querySelector('.asst-chips');
      input.value = '';
      input.focus();
    });
  }

  // bring back the chat kept in this tab
  try {
    var kept = JSON.parse(sessionStorage.getItem(STORE) || 'null');
    if (kept && Array.isArray(kept.entries) && kept.entries.length) {
      history = Array.isArray(kept.history) ? kept.history : [];
      entries = kept.entries;
      log.querySelectorAll('.asst-chips').forEach(function (c) { c.remove(); });
      entries.forEach(function (item) {
        if (!item || typeof item.text !== 'string') { return; }
        add(item.text, item.who === 'user' ? 'user' : 'bot');
        if (item.who !== 'user') { addActions(item.actions); }
      });
      if (kept.reopen) { save(false); setOpen(true); }
    }
  } catch (e) { /* nothing kept */ }
})();
