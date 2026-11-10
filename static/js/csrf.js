(function () {
  'use strict';
  const token = document.querySelector('meta[name="csrf-token"]').content;
  const unsafe = method => !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method.toUpperCase());
  const local = url => new URL(url, location.href).origin === location.origin;
  function protectForms() {
    document.querySelectorAll('form').forEach(form => {
      if (!unsafe(form.method || 'GET') || !local(form.action || location.href)) return;
      if (!form.querySelector('input[name="csrf_token"]')) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'csrf_token';
        input.value = token;
        form.appendChild(input);
      }
    });
  }
  document.addEventListener('DOMContentLoaded', protectForms);
  document.addEventListener('submit', protectForms, true);
  const originalFetch = window.fetch;
  window.fetch = function (input, options) {
    const url = input instanceof Request ? input.url : input;
    const method = options?.method || (input instanceof Request ? input.method : 'GET');
    if (unsafe(method) && local(url)) {
      const headers = new Headers(options?.headers || (input instanceof Request ? input.headers : undefined));
      headers.set('X-CSRFToken', token);
      options = {...options, headers};
    }
    return originalFetch.call(this, input, options);
  };
  const open = XMLHttpRequest.prototype.open;
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url, ...args) {
    this.csrfRequired = unsafe(method) && local(url);
    return open.call(this, method, url, ...args);
  };
  XMLHttpRequest.prototype.send = function (body) {
    if (this.csrfRequired) this.setRequestHeader('X-CSRFToken', token);
    return send.call(this, body);
  };
})();
