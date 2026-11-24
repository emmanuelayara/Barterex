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

  // Polling must continue even when an optional animation asset is unavailable.
  const waiting = document.getElementById('grWaiting');
  if (waiting) {
    let loader = null;
    let timer = null;
    let requestTimer = null;
    let controller = null;
    let stopped = false;
    let finished = false;
    let generation = 0;
    const note = waiting.querySelector('.gr-wait__sub');
    const originalNote = note ? note.textContent : '';
    const quiet = (method, callback) => {
      try {
        if (loader && typeof loader[method] === 'function') loader[method](callback);
      } catch (_) { /* Animation failures must not interrupt status checks. */ }
    };
    try {
      if (window.ValuationLoader) {
        loader = window.ValuationLoader.create({
          loading: document.getElementById('aiValuationLoading'),
          icon: document.getElementById('aiLoaderIcon'),
          phrase: document.getElementById('aiLoaderPhrase'),
          timer: document.getElementById('aiLoaderTimer'),
          bar: document.getElementById('aiLoaderBar')
        });
      }
    } catch (_) { loader = null; }
    quiet('start');

    const next = delay => {
      if (stopped || finished) return;
      clearTimeout(timer);
      timer = setTimeout(poll, delay);
    };
    const reload = () => {
      if (stopped) return;
      stopped = true;
      clearTimeout(timer);
      quiet('stop');
      window.location.reload();
    };
    const complete = ready => {
      finished = true;
      if (!ready || !loader) { reload(); return; }
      // A damaged or cached loader must not swallow the completion callback.
      const current = generation;
      const done = () => { if (current === generation) reload(); };
      timer = setTimeout(done, 2600);
      quiet('finish', done);
    };
    const poll = async () => {
      if (stopped || finished) return;
      const current = generation;
      const requestController = new AbortController();
      controller = requestController;
      requestTimer = setTimeout(() => requestController.abort(), 10000);
      let delay = 4000;
      try {
        const response = await fetch(waiting.dataset.statusUrl, {
          headers: {'Accept': 'application/json'}, credentials: 'same-origin',
          cache: 'no-store', signal: requestController.signal
        });
        if (stopped || current !== generation) return;
        if (response.status === 404) { complete(false); return; }
        if (!response.ok) throw new Error('Status temporarily unavailable');
        const data = await response.json();
        if (stopped || current !== generation) return;
        if (!data || !['processing', 'ready', 'failed', 'missing'].includes(data.status)) {
          throw new Error('Unexpected status response');
        }
        if (note) note.textContent = originalNote;
        if (data.status !== 'processing') { complete(data.status === 'ready'); return; }
        delay = 1500;
      } catch (_) {
        if (!stopped && current === generation && note) {
          note.textContent = 'Connection interrupted. We are checking again; you do not need to upload your photos again.';
        }
      } finally {
        if (current === generation) {
          clearTimeout(requestTimer);
          controller = null;
          next(delay);
        }
      }
    };
    window.addEventListener('pagehide', () => {
      stopped = true;
      generation += 1;
      clearTimeout(timer);
      clearTimeout(requestTimer);
      if (controller) controller.abort();
      controller = null;
      quiet('stop');
    });
    window.addEventListener('pageshow', event => {
      if (!event.persisted) return;
      stopped = finished = false;
      quiet('start');
      next(0);
    });
    next(1500);
  }
})();
