/* Shared "while you wait" loader for the AI valuation modal: rotating phrases with animated icons,
   an elapsed timer and an easing progress bar. Used by /upload and the public /value/start page.
   Usage: const loader = ValuationLoader.create({loading, icon, phrase, timer, bar});
          loader.start(); loader.stop(); loader.finish(callback);  */
(function () {
  'use strict';

  const ICONS = {
    scan: '<svg viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/></svg>',
    chart: '<svg viewBox="0 0 24 24"><path d="M5 20V13"/><path d="M12 20V5"/><path d="M19 20V9"/></svg>',
    coin: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/></svg>',
    sparkle: '<svg viewBox="0 0 24 24"><path d="M11 3l1.8 5.2L18 10l-5.2 1.8L11 17l-1.8-5.2L4 10l5.2-1.8z"/><path d="M19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"/></svg>',
    bolt: '<svg viewBox="0 0 24 24"><path d="M13 2L5 13h6l-1 9 8-11h-6z"/></svg>',
    check: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>'
  };

  // [text, icon]
  const TECHNICAL = [
    ['Initializing Valuation Engine…', 'bolt'],
    ['Analyzing Item Details…', 'scan'],
    ['Processing Visual Data…', 'scan'],
    ['Identifying Product Features…', 'scan'],
    ['Cross-Referencing Specifications…', 'chart'],
    ['Running Predictive Analysis…', 'chart'],
    ['Evaluating Market Signals…', 'chart'],
    ['Calibrating Price Estimates…', 'coin'],
    ['Validating Product Information…', 'scan'],
    ['Optimizing Valuation Accuracy…', 'bolt'],
    ['Examining Market Patterns…', 'chart'],
    ['Calculating Depreciation…', 'coin'],
    ['Comparing Similar Products…', 'scan'],
    ['Assessing Item Condition…', 'scan'],
    ['Generating Value Predictions…', 'chart']
  ];

  const WORKING = [
    ['Decoding Your Item\u2019s Worth…', 'sparkle'],
    ['Crunching the Numbers…', 'coin'],
    ['Connecting the Dots…', 'sparkle'],
    ['Measuring Market Demand…', 'chart'],
    ['Uncovering Hidden Value…', 'sparkle'],
    ['Scanning the Value Universe…', 'scan'],
    ['Putting Our Algorithms to Work…', 'bolt'],
    ['Fine-Tuning the Figures…', 'coin'],
    ['Balancing the Equation…', 'coin'],
    ['Hunting for the Best Estimate…', 'scan'],
    ['Turning Data Into Value…', 'coin'],
    ['Checking Every Detail…', 'scan'],
    ['Consulting the Digital Brain…', 'bolt'],
    ['Solving the Value Puzzle…', 'sparkle'],
    ['Preparing Your BXC Estimate…', 'coin']
  ];

  const PLAYFUL = [
    ['Waking Up the AI Brain…', 'bolt'],
    ['Asking the Algorithms Nicely…', 'sparkle'],
    ['Searching for Hidden Treasure…', 'sparkle'],
    ['Giving Our Robots Some Coffee…', 'bolt'],
    ['Teaching Numbers to Behave…', 'coin'],
    ['Doing Some Digital Detective Work…', 'scan'],
    ['Convincing the Calculator…', 'coin'],
    ['Checking If It\u2019s Secretly Gold…', 'coin'],
    ['Making the Math Make Sense…', 'chart'],
    ['Finding Your Item\u2019s Superpower…', 'bolt'],
    ['Negotiating With the Numbers…', 'coin'],
    ['Running on Pure Intelligence…', 'bolt']
  ];

  const NEARLY_THERE = [
    ['Almost Done Being a Genius…', 'sparkle'],
    ['Making Your Item Feel Important…', 'sparkle'],
    ['Getting Your BXC Ready…', 'coin']
  ];

  // Shown quickly once the real result has arrived
  const FINALE = [
    ['Finalizing Your Estimate…', 'check'],
    ['Preparing Your Results…', 'check'],
    ['Valuation Complete!', 'check']
  ];

  // Technical first, then working/playful phrases alternating, then the "almost done" lines.
  // The last phrase is held if the request runs longer than the sequence.
  const QUEUE = (function () {
    const queue = TECHNICAL.map(phrase => ({ phrase, phase: 'technical' }));
    const max = Math.max(WORKING.length, PLAYFUL.length);
    for (let i = 0; i < max; i++) {
      if (WORKING[i]) queue.push({ phrase: WORKING[i], phase: 'middle' });
      if (PLAYFUL[i]) queue.push({ phrase: PLAYFUL[i], phase: 'middle' });
    }
    NEARLY_THERE.forEach(phrase => queue.push({ phrase, phase: 'middle' }));
    return queue;
  })();

  function create(els) {
    const TRANSITION_MS = 220;
    const EXPECTED_SECONDS = 40;
    let phraseTimer = null;
    let tickTimer = null;
    let swapTimer = null;
    let startedAt = 0;
    let index = 0;
    let running = false;

    function formatElapsed(seconds) {
      return Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0');
    }

    function setIcon(name) {
      els.icon.className = 'aiv-icon aiv-ico-' + name;
      els.icon.innerHTML = ICONS[name];
      // Restart the pop-in animation on every swap
      void els.icon.offsetWidth;
      els.icon.classList.add('pop');
    }

    function showPhrase(entry, animate) {
      clearTimeout(swapTimer);
      const apply = function () {
        els.phrase.textContent = entry[0];
        setIcon(entry[1]);
      };
      if (!animate) {
        els.phrase.className = 'aiv-phrase';
        apply();
        return;
      }
      // Slide the old phrase up and fade out, then bring the new one up from below
      els.phrase.classList.add('is-out');
      swapTimer = setTimeout(function () {
        apply();
        els.phrase.classList.remove('is-out');
        els.phrase.classList.add('is-in');
        void els.phrase.offsetWidth;
        els.phrase.classList.remove('is-in');
      }, TRANSITION_MS);
    }

    function durationFor(phase) {
      return phase === 'technical' ? 1500 + Math.random() * 400 : 2000 + Math.random() * 500;
    }

    function scheduleNext() {
      const current = QUEUE[index];
      phraseTimer = setTimeout(function () {
        if (!running || index >= QUEUE.length - 1) return;
        index += 1;
        showPhrase(QUEUE[index].phrase, true);
        scheduleNext();
      }, durationFor(current.phase));
    }

    function tick() {
      const seconds = Math.floor((Date.now() - startedAt) / 1000);
      els.timer.textContent = formatElapsed(seconds);
      // Eases toward 95% so it keeps moving without promising a finish time
      els.bar.style.width = (95 * (1 - Math.exp(-seconds / (EXPECTED_SECONDS / 2)))) + '%';
    }

    function clearTimers() {
      clearTimeout(phraseTimer);
      clearTimeout(swapTimer);
      clearInterval(tickTimer);
      phraseTimer = swapTimer = tickTimer = null;
    }

    function start() {
      clearTimers();
      running = true;
      index = 0;
      startedAt = Date.now();
      els.loading.classList.remove('is-done');
      els.timer.textContent = '0:00';
      els.bar.style.transition = 'none';
      els.bar.style.width = '0%';
      void els.bar.offsetWidth;
      els.bar.style.transition = '';
      showPhrase(QUEUE[0].phrase, false);
      tickTimer = setInterval(tick, 1000);
      scheduleNext();
    }

    function stop() {
      running = false;
      clearTimers();
    }

    // Plays the short "result ready" messages, then calls done()
    function finish(done) {
      if (!running) {
        done();
        return;
      }
      running = false;
      clearTimers();
      tick();
      els.bar.style.width = '100%';
      let step = 0;
      const playStep = function () {
        showPhrase(FINALE[step], true);
        if (step === FINALE.length - 1) els.loading.classList.add('is-done');
        step += 1;
        if (step < FINALE.length) {
          phraseTimer = setTimeout(playStep, 650);
        } else {
          phraseTimer = setTimeout(done, 800);
        }
      };
      playStep();
    }

    return { start: start, stop: stop, finish: finish };
  }

  window.ValuationLoader = { create: create };
})();
