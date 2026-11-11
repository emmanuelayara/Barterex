// Load after camera.js; uses deterministic time and tracks, not physical hardware.
window.runCameraReadinessTests = async function () {
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const originalInterval = window.setInterval;
  const originalClear = window.clearInterval;
  const nowDescriptor = Object.getOwnPropertyDescriptor(performance, 'now');
  const mediaDescriptor = Object.getOwnPropertyDescriptor(navigator, 'mediaDevices');
  let now = 100;
  let tick;
  let cleared = 0;
  Object.defineProperty(performance, 'now', {configurable: true, value: () => now});
  window.setInterval = callback => { tick = callback; return 123; };
  window.clearInterval = () => { cleared++; };
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true, value: {getSupportedConstraints: () => ({pointsOfInterest: true})}
  });
  const container = document.createElement('div');
  const preview = document.createElement('video');
  const button = document.createElement('button');
  container.append(preview, button);
  document.body.appendChild(container);
  for (const [key, value] of Object.entries({
    currentTime: 0, videoWidth: 4000, videoHeight: 3000, paused: false, readyState: 4
  })) Object.defineProperty(preview, key, {configurable: true, writable: true, value});
  preview.getBoundingClientRect = () => ({left: 0, top: 0, width: 300, height: 600});
  let constraints;
  const track = {
    readyState: 'live', muted: false,
    getCapabilities: () => ({focusMode: ['continuous', 'single-shot']}),
    async applyConstraints(value) { constraints = value; }
  };
  const stream = {getVideoTracks: () => [track]};
  let ready = false;
  const reports = [];
  const control = ItemCamera.bindReadiness(preview, button, value => { ready = value; }, value => reports.push(value));
  const passed = [];
  try {
    control.attach(stream);
    assert(!ready && !button.hidden, 'Startup must wait; supported focus button must show');
    now = 1000;
    tick();
    assert(!ready, 'Static preview metadata must not count as a fresh frame');
    preview.currentTime = 0.1;
    tick();
    assert(ready, 'Fresh live frame after settling should enable capture');
    track.muted = true;
    tick();
    assert(!ready, 'Muted camera must disable capture');
    track.muted = false;
    now = 2600;
    tick();
    assert(!ready, 'Stalled frames must disable capture');
    preview.currentTime = 0.2;
    tick();
    assert(ready, 'Recovered frames should enable capture');
    passed.push('Warmup, advancing frames, muted tracks, stalls and recovery');

    preview.dispatchEvent(new MouseEvent('click', {clientX: 0, clientY: 300}));
    assert(!ready && button.disabled, 'Focus request must pause capture');
    await Promise.resolve();
    await Promise.resolve();
    const point = constraints.advanced[0].pointsOfInterest[0];
    assert(point.x === 0.3125 && point.y === 0.5, 'Cover-crop coordinates must map to the sensor');
    assert(constraints.advanced[0].focusMode === 'single-shot', 'Single-shot focus should be preferred');
    now = 3000;
    preview.currentTime = 0.3;
    tick();
    assert(!ready, 'Shutter must wait while focus settles');
    now = 3500;
    preview.currentTime = 0.4;
    tick();
    assert(ready, 'Shutter must recover after focus settling');
    button.click();
    await Promise.resolve();
    await Promise.resolve();
    assert(constraints.advanced[0].pointsOfInterest[0].x === 0.5, 'Accessible button must focus the centre');
    passed.push('Tap-to-focus, cover-crop mapping, centre button and post-focus settling');

    track.applyConstraints = async () => { throw new DOMException('Unsupported', 'OverconstrainedError'); };
    button.click();
    await Promise.resolve();
    await Promise.resolve();
    assert(reports.some(value => value.includes('could not focus')), 'Focus failure must be surfaced');
    passed.push('Focus failures explicitly reported without claiming focus lock');

    let complete;
    track.applyConstraints = () => new Promise(resolve => { complete = resolve; });
    button.click();
    const reportCount = reports.length;
    control.reset();
    complete();
    await Promise.resolve();
    await Promise.resolve();
    assert(button.hidden && button.disabled && !ready && reports.length === reportCount,
      'Late focus completion must not revive closed-camera UI');
    assert(cleared > 0, 'Reset must release timers');
    passed.push('Cancellation clears timers and ignores late focus completion');

    track.getCapabilities = () => ({});
    control.attach(stream);
    assert(button.hidden, 'Unsupported focus must not be advertised');
    now += 11000;
    tick();
    assert(reports.some(value => value.includes('not delivering ready frames')), 'Readiness timeout must be explicit');
    passed.push('Unsupported focus retains defaults and camera readiness timeouts are visible');
    return {passed, count: passed.length};
  } finally {
    control.reset();
    container.remove();
    window.setInterval = originalInterval;
    window.clearInterval = originalClear;
    if (nowDescriptor) Object.defineProperty(performance, 'now', nowDescriptor);
    else delete performance.now;
    if (mediaDescriptor) Object.defineProperty(navigator, 'mediaDevices', mediaDescriptor);
    else delete navigator.mediaDevices;
  }
};
