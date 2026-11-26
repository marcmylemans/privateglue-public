/* Tags on credentials: the "+ tag" suggestion buttons under the Tags field on the
   credential form, the same behaviour as on the note form. */
(function () {
  'use strict';
  function bind(input) {
    var section = input.closest('.form-section') || document;
    var buttons = Array.prototype.slice.call(section.querySelectorAll('[data-tags-add]'));
    if (!buttons.length) return;
    function current() {
      return input.value.split(',').map(function (t) { return t.trim(); }).filter(Boolean);
    }
    function sync() {
      var have = current().map(function (t) { return t.toLowerCase(); });
      buttons.forEach(function (b) { b.hidden = have.indexOf(b.getAttribute('data-tags-add').toLowerCase()) !== -1; });
    }
    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var tags = current();
        tags.push(btn.getAttribute('data-tags-add'));
        input.value = tags.join(', ');
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.focus();
      });
    });
    input.addEventListener('input', sync);
    sync();
  }
  function init() { document.querySelectorAll('[data-tags-input]').forEach(bind); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
