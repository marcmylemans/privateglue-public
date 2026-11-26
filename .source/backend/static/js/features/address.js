/* Address feature: offer addresses built from the devices ticked under "Used on devices". */
(function () {
  'use strict';

  function init() {
    var field = document.querySelector('[data-address-field]');
    if (!field) return;
    var input = field.querySelector('input[name="address"]');
    var box = field.querySelector('[data-address-suggestions]');
    var list = document.getElementById('addressSuggestions');
    var form = input ? input.form : null;
    if (!input || !box || !form) return;

    var hints = {};
    field.querySelectorAll('[data-address-hints] li').forEach(function (li) {
      var id = li.getAttribute('data-device');
      (hints[id] = hints[id] || []).push(li.getAttribute('data-value'));
    });

    function ticked() {
      var values = [];
      form.querySelectorAll('input[type="checkbox"][name="devices"]:checked').forEach(function (cb) {
        (hints[cb.value] || []).forEach(function (v) { if (values.indexOf(v) === -1) values.push(v); });
      });
      return values;
    }

    function render() {
      var values = ticked();
      box.querySelectorAll('button').forEach(function (b) { b.remove(); });
      list.textContent = '';
      values.forEach(function (v) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'chip mono';
        b.textContent = v;
        b.setAttribute('aria-label', 'Use ' + v + ' as the address');
        b.addEventListener('click', function () {
          input.value = v;
          input.focus();
        });
        box.appendChild(b);
        var o = document.createElement('option');
        o.value = v;
        list.appendChild(o);
      });
      box.hidden = values.length === 0;
    }

    form.addEventListener('change', function (e) {
      if (e.target && e.target.name === 'devices') render();
    });
    render();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
