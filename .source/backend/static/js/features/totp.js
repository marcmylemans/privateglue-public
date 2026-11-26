/* One-time codes: the live code on the credential page and the secret field on the form. */
(function () {
  'use strict';

  var csrfMeta = document.querySelector('meta[name="csrf-token"]');
  var CSRF = csrfMeta ? csrfMeta.getAttribute('content') : '';
  var WARN_SECONDS = 5;
  var GRACE_MS = 300;
  var reducedMotion = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };  // ask a moment after the roll-over, so the server has the new code

  function toast(message, type) { if (window.pgToast) window.pgToast(message, type); }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy') ? resolve() : reject(); } catch (e) { reject(e); }
      ta.remove();
    });
  }

  function flashCopied(btn) {
    var icon = btn.querySelector('i');
    btn.classList.add('copied');
    if (icon) icon.className = 'bi bi-check2';
    setTimeout(function () { btn.classList.remove('copied'); if (icon) icon.className = 'bi bi-copy'; }, 1400);
  }

  function group(code) { var h = Math.floor(code.length / 2); return code.slice(0, h) + ' ' + code.slice(h); }

  /* ---------- The code on the credential page ---------- */
  function bindLiveCode(box) {
    var url = box.getAttribute('data-totp');
    var input = box.querySelector('.totp-code');
    var meter = box.querySelector('.totp-meter');
    var bar = meter && meter.firstElementChild;
    var status = box.querySelector('[data-totp-status]');
    var copyBtn = box.querySelector('[data-totp-copy]');
    var period = parseInt(box.getAttribute('data-totp-period'), 10) || 30;
    var code = input.value.replace(/\s+/g, '');
    var expiresAt = Date.now() + (parseInt(box.getAttribute('data-totp-left'), 10) || 0);
    var timer = null, pending = null, retryAt = 0, stopped = false, shownSeconds = -1;

    if (meter) meter.hidden = false;

    function setBar(fraction, animate) {
      if (!bar) return;
      if (!animate) {
        bar.classList.add('no-anim');
        bar.style.width = (fraction * 100) + '%';
        void bar.offsetWidth;  // apply the jump before turning the animation back on
        bar.classList.remove('no-anim');
      } else {
        bar.style.width = (fraction * 100) + '%';
      }
    }

    function render(jump) {
      var left = Math.max(0, expiresAt - Date.now());
      var secs = Math.ceil(left / 1000);
      if (secs !== shownSeconds || jump) {
        shownSeconds = secs;
        if (status) {
          status.textContent = secs < 1 ? 'Getting the new code.'
            : 'New code in ' + secs + (secs === 1 ? ' second.' : ' seconds.');
        }
        box.classList.toggle('is-expiring', secs <= WARN_SECONDS);
        var now = left / (period * 1000);
        if (reducedMotion.matches) { setBar(now, false); return; }
        // Aim the bar at where it will be one second from now; the 1 s transition fills the gap.
        if (jump) setBar(now, false);
        setBar(Math.max(0, (left - 1000) / (period * 1000)), true);
      }
    }

    function stop(message) {
      stopped = true;
      halt();
      box.classList.remove('is-expiring');
      if (meter) meter.hidden = true;
      input.value = '';
      input.placeholder = 'Not available';
      if (copyBtn) copyBtn.disabled = true;
      if (status) status.textContent = message;
    }

    function refresh() {
      if (pending) return pending;
      pending = fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin', cache: 'no-store' })
        .then(function (r) {
          if (r.status === 404) { stop('This login has no one-time code any more.'); return null; }
          if (r.status === 409) { stop('The saved secret cannot be read.'); return null; }
          var type = r.headers.get('Content-Type') || '';
          if (!r.ok || type.indexOf('application/json') === -1) throw new Error('unavailable');
          return r.json();
        })
        .then(function (d) {
          if (!d) return null;
          code = d.code;
          period = d.period || period;
          expiresAt = Date.now() + d.expires_in_ms;
          input.value = group(code);
          retryAt = 0;
          render(true);
          return code;
        })
        .catch(function () { retryAt = Date.now() + 5000; return null; })
        .then(function (v) { pending = null; return v; });
      return pending;
    }

    function tick() {
      if (stopped) return;
      if (Date.now() >= expiresAt + GRACE_MS && !pending && Date.now() >= retryAt) refresh();
      render(false);
    }

    function start() {
      if (timer || stopped) return;
      timer = setInterval(tick, 250);
      tick();
    }
    function halt() { if (timer) { clearInterval(timer); timer = null; } }

    document.addEventListener('visibilitychange', function () {
      if (stopped) return;
      if (document.hidden) { halt(); return; }
      refresh();
      start();
    });

    if (copyBtn) {
      copyBtn.addEventListener('click', function () {
        // Copy the code that is valid now: if it rolled over since it was shown, get the new one.
        var ready = Date.now() < expiresAt ? Promise.resolve(code) : refresh();
        ready.then(function (value) {
          if (!value) { toast('No valid code right now. Try again in a moment.', 'warning'); return; }
          return copyText(value).then(function () { flashCopied(copyBtn); toast('One-time code copied'); });
        }).catch(function () { toast('Copy failed. Select the code and copy it manually.', 'danger'); });
      });
    }

    render(true);
    start();
  }

  /* ---------- The secret field on the credential form ---------- */
  function bindForm(wrap) {
    var input = wrap.querySelector('#totp_secret');
    var toggle = wrap.querySelector('[data-totp-toggle]');
    var test = wrap.querySelector('[data-totp-test]');
    var result = wrap.querySelector('[data-totp-test-result]');
    var remove = wrap.querySelector('#totp_remove');
    if (!input) return;

    if (toggle) {
      toggle.addEventListener('click', function () {
        var show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        toggle.querySelector('i').className = show ? 'bi bi-eye-slash' : 'bi bi-eye';
        toggle.setAttribute('aria-label', show ? 'Hide secret' : 'Show secret');
        toggle.setAttribute('aria-pressed', show ? 'true' : 'false');
      });
    }

    function say(text, isError) {
      result.hidden = false;
      result.textContent = text;
      result.classList.toggle('text-danger-emphasis', !!isError);
    }

    if (test && result) {
      test.hidden = false;
      test.addEventListener('click', function () {
        var value = input.value.trim();
        if (!value) { say('Paste a setup key first.', true); input.focus(); return; }
        test.disabled = true;
        fetch(test.getAttribute('data-totp-test'), {
          method: 'POST', credentials: 'same-origin', cache: 'no-store',
          headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json' },
          body: 'secret=' + encodeURIComponent(value)
        })
          .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
          .then(function (res) {
            if (!res.ok || !res.d.ok) { say(res.d.error || 'That secret does not work.', true); return; }
            say('Code now: ' + res.d.grouped + '. It should match the one in your authenticator app.');
          })
          .catch(function () { say('Could not test the code right now.', true); })
          .then(function () { test.disabled = false; });
      });
      input.addEventListener('input', function () { result.hidden = true; });
    }

    if (remove) {
      var update = function () {
        input.disabled = remove.checked;
        if (test) test.disabled = remove.checked;
        if (remove.checked && result) result.hidden = true;
      };
      remove.addEventListener('change', update);
      update();
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    Array.prototype.forEach.call(document.querySelectorAll('[data-totp]'), bindLiveCode);
    Array.prototype.forEach.call(document.querySelectorAll('[data-totp-form]'), bindForm);
  });
})();
