/* Dates to watch: add and remove rows on the device form. Without JavaScript the form
 * shows one empty row and a date is removed by clearing it. */
(function () {
  'use strict';

  var list = document.querySelector('[data-dates-rows]');
  var tpl = document.getElementById('datesRowTemplate');
  var addBtn = document.querySelector('[data-dates-add]');
  if (!list || !tpl || !addBtn) return;

  var max = parseInt(list.getAttribute('data-dates-max'), 10) || 12;
  var counter = 1000;

  function rows() { return Array.prototype.slice.call(list.querySelectorAll('[data-dates-row]')); }
  function isEmpty(row) {
    return Array.prototype.every.call(row.querySelectorAll('input'), function (i) { return !i.value; });
  }
  function update() {
    addBtn.disabled = rows().length >= max;
  }
  function wire(row) {
    var btn = row.querySelector('[data-dates-remove]');
    if (!btn) return;
    btn.hidden = false;
    btn.addEventListener('click', function () {
      var next = row.nextElementSibling || row.previousElementSibling;
      row.remove();
      update();
      var focus = next && next.querySelector('select, input');
      (focus || addBtn).focus();
    });
  }

  // With script, the spare empty row is only needed when there are no dates yet.
  var current = rows();
  if (current.length > 1 && isEmpty(current[current.length - 1])) current[current.length - 1].remove();
  rows().forEach(wire);

  addBtn.hidden = false;
  addBtn.addEventListener('click', function () {
    if (rows().length >= max) return;
    counter += 1;
    var holder = document.createElement('div');
    holder.innerHTML = tpl.innerHTML.replace(/__N__/g, String(counter));
    var row = holder.querySelector('[data-dates-row]');
    list.appendChild(row);
    wire(row);
    update();
    var first = row.querySelector('select');
    if (first) first.focus();
  });
  update();
})();
