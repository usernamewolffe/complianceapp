// ui/static/core/js/htmx-hooks.js
(function () {
  if (!window.htmx) return;

  // Show a "busy" cursor during HTMX requests
  document.addEventListener('htmx:send', function () {
    document.documentElement.classList.add('hx-busy');
  });
  document.addEventListener('htmx:afterOnLoad', function () {
    document.documentElement.classList.remove('hx-busy');
  });
  document.addEventListener('htmx:responseError', function (e) {
    console.warn('HTMX request failed', e.detail.xhr && e.detail.xhr.status);
  });
})();
