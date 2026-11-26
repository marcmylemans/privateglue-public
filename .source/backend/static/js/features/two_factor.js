/* Two-factor sign-in: "Download as text" for the recovery codes. Copying uses the shared
   data-copy buttons. Everything else works without this file. */
(function () {
  'use strict';
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-tf-download]');
    if (!btn) return;
    var source = document.querySelector(btn.getAttribute('data-tf-download'));
    if (!source || !source.value) return;
    var blob = new Blob([source.value], { type: 'text/plain' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = btn.getAttribute('data-tf-filename') || 'recovery-codes.txt';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    if (window.pgToast) window.pgToast('Recovery codes downloaded');
  });
})();
