/* PrivateGlue shared front-end behaviour.
 * Everything is opt-in through data attributes so templates stay free of inline scripts.
 */
(function () {
  'use strict';

  var root = document.documentElement;
  var csrfMeta = document.querySelector('meta[name="csrf-token"]');
  var CSRF = csrfMeta ? csrfMeta.getAttribute('content') : '';

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $all(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
  function debounce(fn, ms) { var t; return function () { var a = arguments, s = this; clearTimeout(t); t = setTimeout(function () { fn.apply(s, a); }, ms); }; }

  /* ---------------- Theme (light / dark / system) ---------------- */
  var mq = window.matchMedia('(prefers-color-scheme: dark)');
  function themePref() { return localStorage.getItem('pg-theme') || localStorage.getItem('theme') || 'auto'; }
  function applyTheme(pref) {
    var dark = pref === 'dark' || (pref === 'auto' && mq.matches);
    root.setAttribute('data-bs-theme', dark ? 'dark' : 'light');
    $all('[data-theme-value]').forEach(function (b) {
      var on = b.getAttribute('data-theme-value') === pref;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    $all('link[data-hl-theme]').forEach(function (l) { l.disabled = l.getAttribute('data-hl-theme') !== (dark ? 'dark' : 'light'); });
  }
  function setTheme(pref) { localStorage.setItem('pg-theme', pref); localStorage.removeItem('theme'); applyTheme(pref); }
  mq.addEventListener && mq.addEventListener('change', function () { if (themePref() === 'auto') applyTheme('auto'); });

  /* ---------------- Toasts ---------------- */
  var ICONS = { success: 'check-circle-fill', info: 'info-circle-fill', warning: 'exclamation-triangle-fill', danger: 'x-octagon-fill' };
  function toast(message, type) {
    type = type || 'success';
    var stack = $('#toastStack');
    if (!stack || !window.bootstrap) return;
    var el = document.createElement('div');
    el.className = 'toast pg-toast pg-toast-' + type;
    el.setAttribute('role', type === 'danger' ? 'alert' : 'status');
    el.setAttribute('aria-live', type === 'danger' ? 'assertive' : 'polite');
    el.innerHTML = '<div class="d-flex align-items-start gap-2 p-3"><i class="bi bi-' + ICONS[type] + ' toast-icon" aria-hidden="true"></i>' +
      '<div class="flex-grow-1"></div><button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Dismiss"></button></div>';
    el.querySelector('.flex-grow-1').textContent = message;
    stack.appendChild(el);
    var t = bootstrap.Toast.getOrCreateInstance(el, { delay: 3000, autohide: type !== 'danger' });
    el.addEventListener('hidden.bs.toast', function () { el.remove(); });
    t.show();
  }
  window.pgToast = toast;

  /* ---------------- Clipboard ---------------- */
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
    if (icon) { icon.className = 'bi bi-check2'; }
    setTimeout(function () { btn.classList.remove('copied'); if (icon) icon.className = 'bi bi-copy'; }, 1400);
  }

  /* ---------------- Password helpers ---------------- */
  function generatePassword(length) {
    length = length || 20;
    var sets = ['abcdefghijkmnopqrstuvwxyz', 'ABCDEFGHJKLMNPQRSTUVWXYZ', '23456789', '!@#$%^&*-_=+?'];
    var all = sets.join('');
    var out = [];
    var rnd = new Uint32Array(length + sets.length);
    crypto.getRandomValues(rnd);
    sets.forEach(function (s, i) { out.push(s[rnd[i] % s.length]); });          // at least one of each class
    for (var i = sets.length; i < length; i++) out.push(all[rnd[i] % all.length]);
    for (var j = out.length - 1; j > 0; j--) {                                     // Fisher-Yates shuffle
      var r = new Uint32Array(1); crypto.getRandomValues(r);
      var k = r[0] % (j + 1); var tmp = out[j]; out[j] = out[k]; out[k] = tmp;
    }
    return out.join('');
  }

  function scorePassword(pw) {
    if (!pw) return 0;
    var classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter(function (r) { return r.test(pw); }).length;
    if (pw.length < 8) return 1;
    if (pw.length >= 14 && classes >= 3) return 4;
    if (pw.length >= 12 || (pw.length >= 10 && classes >= 3)) return 3;
    return 2;
  }

  function bindStrength(input) {
    var fb = $(input.getAttribute('data-pw-strength'));
    if (!fb) return;
    var min = parseInt(input.getAttribute('minlength') || '8', 10);
    var meter = document.createElement('div');
    meter.className = 'pw-meter'; meter.setAttribute('aria-hidden', 'true'); meter.innerHTML = '<span></span>';
    fb.parentNode.insertBefore(meter, fb);
    var base = fb.textContent;
    function update() {
      var v = input.value, s = scorePassword(v), bar = meter.firstChild;
      fb.classList.remove('is-weak', 'is-ok', 'is-strong');
      if (!v) { fb.textContent = base; bar.style.width = '0'; input.setCustomValidity(''); return; }
      var map = {
        1: ['is-weak', v.length < min ? 'Too short: use at least ' + min + ' characters.' : 'Weak: under 8 characters is easy to guess.', '25%', '#ef4444'],
        2: ['is-ok', 'Okay. Longer, with mixed characters, is better.', '50%', '#f59e0b'],
        3: ['is-strong', 'Good password.', '75%', '#10b981'],
        4: ['is-strong', 'Strong password.', '100%', '#059669']
      }[s];
      fb.classList.add(map[0]); fb.textContent = map[1];
      bar.style.width = map[2]; bar.style.backgroundColor = map[3];
      input.setCustomValidity(v.length < min ? 'Use at least ' + min + ' characters.' : '');
    }
    input.addEventListener('input', update);
  }

  function bindMatch(confirm) {
    var src = $(confirm.getAttribute('data-pw-match'));
    var fb = $(confirm.getAttribute('data-pw-match-feedback'));
    if (!src) return;
    function update() {
      if (!confirm.value) { confirm.classList.remove('is-valid', 'is-invalid'); if (fb) fb.textContent = ''; confirm.setCustomValidity(''); return; }
      var ok = confirm.value === src.value;
      confirm.classList.toggle('is-valid', ok); confirm.classList.toggle('is-invalid', !ok);
      confirm.setCustomValidity(ok ? '' : 'Passwords do not match.');
      if (fb) { fb.textContent = ok ? 'Passwords match.' : 'Passwords do not match.'; fb.className = 'form-text ' + (ok ? 'text-success-emphasis' : 'text-danger-emphasis'); }
    }
    confirm.addEventListener('input', update); src.addEventListener('input', update);
  }

  function bindUsernameCheck(input) {
    var fb = $(input.getAttribute('data-username-check'));
    var check = debounce(function () {
      var v = input.value.trim();
      input.classList.remove('is-valid', 'is-invalid');
      if (!v) { if (fb) fb.textContent = ''; return; }
      fetch('/check_username?username=' + encodeURIComponent(v), { headers: { 'Accept': 'application/json' } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (!d) return;
          input.classList.add(d.exists ? 'is-invalid' : 'is-valid');
          input.setCustomValidity(d.exists ? 'That username is already taken.' : '');
          if (fb) { fb.textContent = d.exists ? 'That username is already taken.' : 'Username is available.'; fb.className = 'form-text ' + (d.exists ? 'text-danger-emphasis' : 'text-success-emphasis'); }
        }).catch(function () {});
    }, 350);
    input.addEventListener('input', check);
  }

  /* ---------------- Confirm modal ---------------- */
  var pendingForm = null;
  function setupConfirm() {
    var modalEl = $('#confirmModal');
    if (!modalEl || !window.bootstrap) return;
    var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    var ok = $('#confirmModalOk');
    document.addEventListener('submit', function (e) {
      var form = e.target;
      if (!form.hasAttribute('data-confirm') || form.dataset.confirmed === '1') return;
      e.preventDefault();
      pendingForm = form;
      $('#confirmModalTitle').textContent = form.getAttribute('data-confirm-title') || 'Are you sure?';
      $('#confirmModalBody').textContent = form.getAttribute('data-confirm');
      ok.textContent = form.getAttribute('data-confirm-ok') || 'Delete';
      modal.show();
    });
    modalEl.addEventListener('shown.bs.modal', function () { ok.focus(); });
    ok.addEventListener('click', function () {
      if (!pendingForm) return;
      pendingForm.dataset.confirmed = '1';
      ok.disabled = true;
      if (pendingForm.requestSubmit) pendingForm.requestSubmit(); else pendingForm.submit();
    });
    modalEl.addEventListener('hidden.bs.modal', function () { ok.disabled = false; pendingForm = null; });
  }

  /* ---------------- Table / list filtering ---------------- */
  function bindListFilter(input) {
    var target = $(input.getAttribute('data-filter-target'));
    var countEl = $(input.getAttribute('data-filter-count'));
    if (!target) return;
    var rows = $all('[data-filter-text]', target);
    var empty = $('.filter-empty', target);
    var noun = input.getAttribute('data-filter-noun') || 'items';
    function update() {
      var q = input.value.trim().toLowerCase(), shown = 0;
      rows.forEach(function (r) {
        var hit = !q || r.getAttribute('data-filter-text').toLowerCase().indexOf(q) !== -1;
        r.hidden = !hit; if (hit) shown++;
      });
      if (empty) empty.hidden = shown !== 0;
      if (countEl) countEl.textContent = q ? shown + ' of ' + rows.length + ' ' + noun : rows.length + ' ' + noun;
    }
    input.addEventListener('input', update);
    input.addEventListener('keydown', function (e) { if (e.key === 'Escape') { input.value = ''; update(); } });
    update();
  }

  function bindChecklist(input) {
    var list = $(input.getAttribute('data-checklist-filter'));
    if (!list) return;
    var items = $all('.checklist-item', list), empty = $('.checklist-empty', list), count = $('.checklist-count', list);
    function refreshCount() { var n = $all('input:checked', list).length; if (count) count.textContent = n ? n + ' selected' : ''; }
    input.addEventListener('input', function () {
      var q = input.value.trim().toLowerCase(), shown = 0;
      items.forEach(function (it) { var hit = !q || it.getAttribute('data-filter-text').toLowerCase().indexOf(q) !== -1; it.hidden = !hit; if (hit) shown++; });
      if (empty) empty.hidden = shown !== 0 || !items.length;
    });
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') e.preventDefault(); });
    list.addEventListener('change', refreshCount);
    refreshCount();
  }

  /* ---------------- Clickable rows ---------------- */
  /* ---------------- Sortable tables ----------------
     <table data-sortable> with <th data-sort>. A cell can carry data-sort-value. */
  function bindSortable(table) {
    var body = table.tBodies[0]; if (!body) return;
    var headers = $all('thead th', table);
    headers.forEach(function (th, index) {
      if (!th.hasAttribute('data-sort')) return;
      var btn = document.createElement('button');
      btn.type = 'button'; btn.className = 'sort-btn';
      while (th.firstChild) btn.appendChild(th.firstChild);
      var arrow = document.createElement('i'); arrow.className = 'bi bi-arrow-down-up sort-arrow'; arrow.setAttribute('aria-hidden', 'true');
      btn.appendChild(arrow); th.appendChild(btn);
      btn.addEventListener('click', function () {
        var asc = th.getAttribute('aria-sort') !== 'ascending';
        headers.forEach(function (h) { h.removeAttribute('aria-sort'); var a = h.querySelector('.sort-arrow'); if (a) a.className = 'bi bi-arrow-down-up sort-arrow'; });
        th.setAttribute('aria-sort', asc ? 'ascending' : 'descending');
        arrow.className = 'bi ' + (asc ? 'bi-arrow-up' : 'bi-arrow-down') + ' sort-arrow';
        var rows = $all('tr', body).filter(function (r) { return !r.classList.contains('filter-empty'); });
        function key(row) {
          var cell = row.cells[index]; if (!cell) return '';
          return (cell.hasAttribute('data-sort-value') ? cell.getAttribute('data-sort-value') : cell.textContent).trim().toLowerCase();
        }
        rows.sort(function (a, b) {
          var x = key(a), y = key(b);
          if (!x && y) return 1; if (x && !y) return -1;           // empty values always last
          var r = x.localeCompare(y, undefined, { numeric: true, sensitivity: 'base' });
          return asc ? r : -r;
        });
        var tail = $('.filter-empty', body);
        rows.forEach(function (r) { body.insertBefore(r, tail); });
      });
    });
  }

  function setupRowLinks() {
    document.addEventListener('click', function (e) {
      var row = e.target.closest('tr[data-href]');
      if (!row || e.target.closest('a, button, input, label, form, .dropdown, .select-col')) return;
      if (e.ctrlKey || e.metaKey) { window.open(row.getAttribute('data-href'), '_blank'); return; }
      window.location = row.getAttribute('data-href');
    });
  }

  /* ---------------- Markdown extras: highlight + copy code ---------------- */
  function enhanceMarkdown(container) {
    $all('pre > code', container).forEach(function (code) {
      if (window.hljs && !code.dataset.highlighted) { try { hljs.highlightElement(code); } catch (e) {} }
      var pre = code.parentNode;
      if (pre.querySelector('.code-copy')) return;
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'btn btn-copy code-copy'; b.setAttribute('aria-label', 'Copy code'); b.title = 'Copy code';
      b.innerHTML = '<i class="bi bi-copy" aria-hidden="true"></i>';
      b.addEventListener('click', function () { copyText(code.innerText).then(function () { flashCopied(b); toast('Code copied'); }); });
      pre.appendChild(b);
    });
  }
  window.pgEnhanceMarkdown = enhanceMarkdown;

  /* ---------------- Note editor live preview ---------------- */
  function bindEditor(textarea) {
    var preview = $(textarea.getAttribute('data-preview'));
    var url = textarea.getAttribute('data-preview-url');
    var status = $(textarea.getAttribute('data-preview-status'));
    if (!preview || !url) return;
    var last = null;
    var render = debounce(function () {
      if (textarea.value === last) return;
      last = textarea.value;
      if (status) status.textContent = 'Updating…';
      var body = new URLSearchParams(); body.set('content', textarea.value);
      fetch(url, { method: 'POST', headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/x-www-form-urlencoded' }, body: body })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          preview.innerHTML = d.html || '<p class="text-body-tertiary">Nothing to preview yet.</p>';
          enhanceMarkdown(preview);
          if (status) status.textContent = '';
        })
        .catch(function () { if (status) status.textContent = 'Preview unavailable'; });
    }, 300);
    textarea.addEventListener('input', render);
    render();

    // Tab key inserts two spaces instead of leaving the editor; Esc then Tab still leaves it.
    var escaped = false;
    textarea.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { escaped = true; return; }
      if (e.key === 'Tab' && !escaped && !e.shiftKey) {
        e.preventDefault();
        var s = textarea.selectionStart, en = textarea.selectionEnd;
        textarea.setRangeText('  ', s, en, 'end');
        render();
      }
      escaped = false;
    });

    var grid = textarea.closest('.editor-grid');
    $all('[data-editor-mode]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        grid.setAttribute('data-mode', btn.getAttribute('data-editor-mode'));
        $all('[data-editor-mode]').forEach(function (b) { var on = b === btn; b.classList.toggle('active', on); b.setAttribute('aria-selected', on ? 'true' : 'false'); });
      });
    });

    // Warn before leaving with unsaved changes
    var form = textarea.form, dirty = false;
    if (form) {
      form.addEventListener('input', function () { dirty = true; });
      form.addEventListener('submit', function () { dirty = false; });
      window.addEventListener('beforeunload', function (e) { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
      document.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); dirty = false; form.requestSubmit ? form.requestSubmit() : form.submit(); }
      });
    }
  }

  /* ---------------- Init ---------------- */
  document.addEventListener('DOMContentLoaded', function () {
    applyTheme(themePref());
    $all('[data-theme-value]').forEach(function (b) {
      b.addEventListener('click', function () { setTheme(b.getAttribute('data-theme-value')); });
    });

    if (window.bootstrap) {
      $all('.toast.show').forEach(function (el) {
        var inst = bootstrap.Toast.getOrCreateInstance(el);
        if (el.getAttribute('data-bs-autohide') !== 'false') setTimeout(function () { inst.hide(); }, parseInt(el.getAttribute('data-bs-delay') || '5000', 10));
      });
      $all('[data-bs-toggle="tooltip"]').forEach(function (el) { new bootstrap.Tooltip(el); });
    }

    setupConfirm();
    setupRowLinks();

    // Copy buttons: data-copy-text="literal" or data-copy="#inputSelector"
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-copy], [data-copy-text]');
      if (!btn) return;
      var text = btn.hasAttribute('data-copy-text') ? btn.getAttribute('data-copy-text') : ($(btn.getAttribute('data-copy')) || {}).value;
      if (!text) { toast('Nothing to copy yet', 'warning'); return; }
      copyText(text).then(function () { flashCopied(btn); toast(btn.getAttribute('data-copy-message') || 'Copied to clipboard'); })
        .catch(function () { toast('Copy failed. Select the text and copy it manually.', 'danger'); });
    });

    // Reveal masked values (data-reveal next to .secret-value) and toggle password inputs
    document.addEventListener('click', function (e) {
      var rev = e.target.closest('[data-reveal]');
      if (rev) {
        var sv = rev.parentNode.querySelector('.secret-value');
        var shown = sv.dataset.shown === '1';
        sv.firstElementChild.textContent = shown ? '••••••••••••' : sv.getAttribute('data-secret');
        sv.dataset.shown = shown ? '0' : '1';
        rev.querySelector('i').className = shown ? 'bi bi-eye' : 'bi bi-eye-slash';
        rev.setAttribute('aria-label', (shown ? 'Show' : 'Hide') + rev.getAttribute('aria-label').replace(/^(Show|Hide)/, ''));
        return;
      }
      var tog = e.target.closest('[data-pw-toggle]');
      if (tog) {
        var input = $(tog.getAttribute('data-pw-toggle'));
        var show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        tog.querySelector('i').className = show ? 'bi bi-eye-slash' : 'bi bi-eye';
        tog.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
        tog.setAttribute('aria-pressed', show ? 'true' : 'false');
        return;
      }
      var gen = e.target.closest('[data-pw-generate]');
      if (gen) {
        var target = $(gen.getAttribute('data-pw-generate'));
        var lenInput = $(gen.getAttribute('data-pw-length'));
        target.value = generatePassword(lenInput ? parseInt(lenInput.value, 10) : 20);
        target.type = 'text';
        var t2 = $('[data-pw-toggle="' + gen.getAttribute('data-pw-generate') + '"]');
        if (t2) { t2.querySelector('i').className = 'bi bi-eye-slash'; t2.setAttribute('aria-label', 'Hide password'); }
        target.dispatchEvent(new Event('input', { bubbles: true }));
        toast('Strong password generated');
      }
    });

    $all('[data-pw-strength]').forEach(bindStrength);
    $all('[data-pw-match]').forEach(bindMatch);
    $all('[data-username-check]').forEach(bindUsernameCheck);
    $all('[data-filter-target]').forEach(bindListFilter);
    $all('table[data-sortable]').forEach(bindSortable);
    $all('[data-checklist-filter]').forEach(bindChecklist);
    $all('textarea[data-preview]').forEach(bindEditor);
    $all('.markdown-body').forEach(enhanceMarkdown);

    // Auto-submit filter selects
    $all('select[data-autosubmit]').forEach(function (s) { s.addEventListener('change', function () { s.form.requestSubmit ? s.form.requestSubmit() : s.form.submit(); }); });

    // Prevent double submits: disable the clicked submit button after the form submits.
    document.addEventListener('submit', function (e) {
      if (e.defaultPrevented) return;
      var btn = e.submitter;
      if (btn && !btn.hasAttribute('data-no-busy') && !e.target.hasAttribute('data-confirm-pending')) {
        setTimeout(function () { btn.disabled = true; btn.classList.add('is-busy'); }, 0);
      }
    });

    // "Go back" buttons on the error pages (no inline onclick: the content security policy forbids it)
    $all('[data-history-back]').forEach(function (btn) {
      btn.addEventListener('click', function () { window.history.back(); });
    });

    // Keyboard: "/" or Ctrl/Cmd+K focuses global search
    var search = $('#globalSearch');
    document.addEventListener('keydown', function (e) {
      if (!search) return;
      var tag = (e.target.tagName || '').toLowerCase();
      var typing = tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable;
      if ((e.key === '/' && !typing) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k')) {
        e.preventDefault(); search.focus(); search.select();
      }
    });
  });
})();
