// Attachments: check size before sending, so a file that is too large or empty gets a
// plain message at once instead of a long upload. The form works without this script.
(function () {
  'use strict';
  var forms = document.querySelectorAll('form[data-attachments-upload]');
  Array.prototype.forEach.call(forms, function (form) {
    var input = form.querySelector('input[type="file"]');
    var help = form.querySelector('[data-default-text]');
    var button = form.querySelector('button[type="submit"]');
    var max = parseInt(form.getAttribute('data-max-bytes'), 10) || 0;
    if (!input) return;

    function say(text, problem) {
      if (!help) return;
      help.textContent = text || help.getAttribute('data-default-text');
      help.classList.toggle('text-danger', !!problem);
    }

    function check() {
      var file = input.files && input.files[0];
      if (!file) { say(); return true; }
      if (max && file.size > max) {
        say('That file is too large. Files can be up to ' + Math.round(max / 1048576) + ' MB.', true);
        return false;
      }
      if (file.size === 0) {
        say('That file is empty.', true);
        return false;
      }
      say();
      return true;
    }

    input.addEventListener('change', check);
    form.addEventListener('submit', function (e) {
      if (!check()) { e.preventDefault(); input.focus(); return; }
      if (button) {
        button.disabled = true;
        button.dataset.label = button.dataset.label || button.innerHTML;
        button.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Uploading…';
      }
    });
    // Coming back with the Back button shows the page as it was left: make the button usable again.
    window.addEventListener('pageshow', function () {
      if (button && button.dataset.label) { button.disabled = false; button.innerHTML = button.dataset.label; }
    });
  });
})();
