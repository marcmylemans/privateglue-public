/* Activity log: report clicks on buttons that carry data-audit, and show exact times in the
 * browser's own time zone. Never blocks or delays the click itself. */
(function () {
  'use strict';

  var meta = document.querySelector('meta[name="csrf-token"]');
  var CSRF = meta ? meta.getAttribute('content') : '';

  function send(action, target) {
    var body = new URLSearchParams();
    body.set('action', action);
    body.set('target', target);
    try {
      fetch('/activity/event', {
        method: 'POST', keepalive: true, credentials: 'same-origin',
        headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body
      }).catch(function () {});
    } catch (e) { /* a log must never get in the way */ }
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-audit]');
    if (!btn) return;
    var action = btn.getAttribute('data-audit');
    var target = btn.getAttribute('data-audit-target') || '';
    if (!action || !target) return;
    // Let the page's own handlers run first, then look: a show/hide toggle only counts
    // when it showed something.
    setTimeout(function () {
      if (btn.hasAttribute('aria-pressed') && btn.getAttribute('aria-pressed') !== 'true') return;
      send(action, target);
    }, 0);
  });

  function localTitles() {
    var fmt;
    try { fmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' }); } catch (e) { return; }
    Array.prototype.forEach.call(document.querySelectorAll('time[data-audit-time]'), function (el) {
      var d = new Date(el.getAttribute('datetime'));
      if (!isNaN(d.getTime())) el.title = fmt.format(d);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', localTitles);
  else localTitles();
})();
