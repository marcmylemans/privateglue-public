/* Extra fields on a credential: show/hide on the credential page, rows in the form.
   Copying uses the app's own data-copy buttons. */
(function () {
  'use strict';

  function all(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }

  /* ---------- Show and hide (credential page and form) ---------- */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-fields-toggle]');
    if (!btn) return;
    var target = document.querySelector(btn.getAttribute('data-fields-toggle'));
    if (!target) return;
    var show;
    if (target.tagName === 'TEXTAREA') {
      show = target.hidden;
      target.hidden = !show;
      var mask = btn.parentNode.querySelector('[data-fields-mask]');
      if (mask) mask.value = mask.getAttribute(show ? 'data-fields-mask-shown' : 'data-fields-mask');
    } else {
      show = target.type === 'password';
      target.type = show ? 'text' : 'password';
    }
    btn.querySelector('i').className = show ? 'bi bi-eye-slash' : 'bi bi-eye';
    btn.setAttribute('aria-label', (show ? 'Hide' : 'Show') + btn.getAttribute('aria-label').replace(/^(Show|Hide)/, ''));
    btn.setAttribute('aria-pressed', show ? 'true' : 'false');
  });

  /* ---------- The form ---------- */
  function setupEditor(editor) {
    var list = editor.querySelector('[data-fields-rows]');
    var addBar = editor.querySelector('[data-fields-add]');
    var full = editor.querySelector('[data-fields-full]');
    var max = parseInt(editor.getAttribute('data-fields-max') || '20', 10);
    var seq = 0;

    function template(name, token) {
      var tpl = editor.querySelector('template[data-fields-template="' + name + '"]');
      var holder = document.createElement('div');
      holder.innerHTML = tpl.innerHTML.split('__TOKEN__').join(token);
      return holder;
    }

    function activeRows() {
      return all('[data-fields-row]', list).filter(function (row) {
        var check = row.querySelector('[data-fields-remove-check]');
        return !(check && check.checked);
      });
    }

    function refresh() {
      var isFull = activeRows().length >= max;
      all('[data-fields-preset]', addBar).forEach(function (b) { b.disabled = isFull; });
      full.hidden = !isFull;
      addBar.classList.toggle('mt-3', list.querySelector('[data-fields-row]') !== null);
    }

    // A filled-in value needs a name. Existing rows always need one.
    function syncRequired(row) {
      var label = row.querySelector('[data-fields-label]');
      var value = row.querySelector('[data-fields-value]');
      if (!label || label.disabled) return;
      label.required = row.querySelector('input[name^="fields_id_"]') !== null || !!(value && value.value);
    }

    function swapValue(row, kind) {
      var slot = row.querySelector('[data-fields-value-slot]');
      var old = slot.querySelector('[data-fields-value]');
      var token = row.querySelector('input[name="fields_row"]').value;
      var keep = row.hasAttribute('data-fields-keep');
      var fresh = template(kind + (keep ? '-keep' : ''), token);
      var input = fresh.querySelector('[data-fields-value]');
      if (old && old.value) input.value = old.value;
      slot.innerHTML = '';
      while (fresh.firstChild) slot.appendChild(fresh.firstChild);
      syncRequired(row);
    }

    function addRow(label, kind) {
      seq += 1;
      var holder = template('row', 'j' + seq);
      var row = holder.querySelector('[data-fields-row]');
      row.querySelector('[data-fields-label]').value = label;
      var select = row.querySelector('[data-fields-kind]');
      select.value = kind;
      list.appendChild(row);
      if (kind !== 'secret') swapValue(row, kind);
      refresh();
      (label ? row.querySelector('[data-fields-value]') : row.querySelector('[data-fields-label]')).focus();
    }

    addBar.hidden = false;
    refresh();

    addBar.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-fields-preset]');
      if (!btn || btn.disabled) return;
      addRow(btn.getAttribute('data-fields-preset'), btn.getAttribute('data-fields-preset-kind'));
    });

    list.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-fields-remove]');
      if (!btn) return;
      var row = btn.closest('[data-fields-row]');
      var next = row.nextElementSibling || row.previousElementSibling;
      row.remove();
      refresh();
      var focusTo = next && next.querySelector ? next.querySelector('[data-fields-label]') : null;
      (focusTo || addBar.querySelector('[data-fields-preset]')).focus();
    });

    list.addEventListener('change', function (e) {
      var row = e.target.closest('[data-fields-row]');
      if (!row) return;
      if (e.target.matches('[data-fields-kind]')) swapValue(row, e.target.value);
      if (e.target.matches('[data-fields-remove-check]')) {
        var removing = e.target.checked;
        row.classList.toggle('pgf-removed', removing);
        all('[data-fields-label], [data-fields-kind], [data-fields-value], [data-fields-toggle]', row).forEach(function (el) { el.disabled = removing; });
        var note = row.querySelector('[data-fields-removed-note]');
        if (note) note.hidden = !removing;
        all('[data-fields-value-slot] .form-text', row).forEach(function (el) { el.hidden = removing; });
        syncRequired(row);
        refresh();
      }
    });

    list.addEventListener('input', function (e) {
      var row = e.target.closest('[data-fields-row]');
      if (row) syncRequired(row);
    });

    all('[data-fields-row]', list).forEach(syncRequired);
  }

  document.addEventListener('DOMContentLoaded', function () {
    all('[data-fields-editor]').forEach(setupEditor);
  });
})();
