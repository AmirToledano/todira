// 2026-10-23: the site assistant's chat (templates/_assistant.html, main.py /api/assistant). The chat lives only in this
// page; each question sends the conversation so far, and nothing is stored on the server.
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
  var history = [];
  var busy = false;

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
    if (chips) { chips.remove(); chips = null; }
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
      waiting.classList.remove('asst-wait');
      waiting.textContent = reply;
      history.push({ role: 'assistant', text: reply });
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
  if (chips) {
    chips.addEventListener('click', function (e) {
      var chip = e.target.closest('.asst-chip');
      if (chip) { ask(chip.textContent); }
    });
  }
})();
