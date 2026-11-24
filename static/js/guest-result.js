/* Guest estimate result page: value count-up, expiry countdown, photo viewer, and the waiting state. */
(function () {
  'use strict';

  const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Count the estimate up from zero
  const amount = document.querySelector('[data-count-to]');
  if (amount) {
    const target = Number(amount.dataset.countTo);
    if (!reduceMotion && Number.isFinite(target) && target > 0) {
      const duration = 1100;
      const started = performance.now();
      const step = now => {
        const progress = Math.min(1, (now - started) / duration);
        const eased = 1 - Math.pow(1 - progress, 3);
        amount.textContent = Math.round(target * eased).toLocaleString('en-US');
        if (progress < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }
  }

  // "Saved for 2 days 14 hours" countdown
  const expiry = document.querySelector('[data-expires]');
  if (expiry) {
    const ends = Date.parse(expiry.dataset.expires);
    const paint = () => {
      const minutes = Math.floor((ends - Date.now()) / 60000);
      if (!Number.isFinite(minutes)) return;
      if (minutes <= 0) { expiry.textContent = 'less than a minute'; return; }
      const days = Math.floor(minutes / 1440);
      const hours = Math.floor((minutes % 1440) / 60);
      const parts = [];
      if (days) parts.push(days + (days === 1 ? ' day' : ' days'));
      if (hours || !days) parts.push(hours + (hours === 1 ? ' hour' : ' hours'));
      if (!days && !hours) parts.push(minutes + ' min');
      expiry.textContent = parts.join(' ');
    };
    paint();
    setInterval(paint, 60000);
  }

  // Tap a photo to enlarge it
  const box = document.getElementById('grLightbox');
  if (box && typeof box.showModal === 'function') {
    const image = box.querySelector('img');
    const caption = box.querySelector('[data-caption]');
    document.querySelectorAll('[data-photo]').forEach(button => {
      button.addEventListener('click', () => {
        image.src = button.dataset.photo;
        image.alt = button.dataset.alt || '';
        caption.textContent = button.dataset.alt || '';
        box.showModal();
      });
    });
    box.querySelector('button').addEventListener('click', () => box.close());
    box.addEventListener('click', event => { if (event.target === box) box.close(); });
  }

  // Waiting state: same loader as the upload modal, then reload when the estimate is ready
  const waiting = document.getElementById('grWaiting');
  if (waiting && window.ValuationLoader) {
    const loader = ValuationLoader.create({
      loading: document.getElementById('aiValuationLoading'),
      icon: document.getElementById('aiLoaderIcon'),
      phrase: document.getElementById('aiLoaderPhrase'),
      timer: document.getElementById('aiLoaderTimer'),
      bar: document.getElementById('aiLoaderBar')
    });
    loader.start();
    const poll = () => {
      fetch(waiting.dataset.statusUrl, {headers: {'Accept': 'application/json'}, credentials: 'same-origin'})
        .then(r => (r.ok ? r.json() : {status: 'missing'}))
        .then(data => {
          if (data.status === 'processing') setTimeout(poll, 1500);
          else loader.finish(() => window.location.reload());
        })
        .catch(() => setTimeout(poll, 4000));
    };
    setTimeout(poll, 1500);
  }
})();
