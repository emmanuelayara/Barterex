// Load after static/js/camera.js in a browser, then await runCameraQualityTests().
window.runCameraQualityTests = async function () {
  const saved = new Map(['ImageCapture', 'MediaRecorder', 'Image'].map(key => [key, Object.getOwnPropertyDescriptor(window, key)]));
  const mediaDescriptor = Object.getOwnPropertyDescriptor(navigator, 'mediaDevices');
  const createElement = document.createElement;
  const warn = console.warn;
  const passed = [];
  const warnings = [];
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const reject = async (action, name) => {
    try { await action(); } catch (error) { assert(error.name === name, `Expected ${name}, got ${error.name}`); return; }
    throw new Error(`Expected ${name}`);
  };
  const camera = () => {
    const track = {readyState: 'live', stop() { this.readyState = 'ended'; }};
    return {getTracks: () => [track], getVideoTracks: () => [track]};
  };
  const media = {};
  Object.defineProperty(navigator, 'mediaDevices', {configurable: true, value: media});
  console.warn = (...args) => warnings.push(args);
  try {
    let requests = [];
    let stream = camera();
    let adjustments;
    stream.getVideoTracks()[0].getCapabilities = () => ({
      focusMode: ['manual', 'continuous'], exposureMode: ['continuous'], whiteBalanceMode: ['continuous']
    });
    stream.getVideoTracks()[0].applyConstraints = async constraints => { adjustments = constraints; };
    media.getUserMedia = async constraints => { requests.push(constraints); return stream; };
    assert(await ItemCamera.openStream('photo', () => true) === stream, 'Photo stream not returned');
    assert(requests[0].video.width.ideal === 4096 && requests[0].video.height.ideal === 3072, 'Photos must request 4096x3072');
    assert(requests[0].audio === false && requests[0].video.facingMode.ideal === 'environment', 'Rear camera/no audio changed');
    assert(adjustments.advanced[0].focusMode === 'continuous' && adjustments.advanced[0].exposureMode === 'continuous'
      && adjustments.advanced[0].whiteBalanceMode === 'continuous', 'Continuous adjustments not requested');
    passed.push('12 MP photo preview preference, rear camera, no audio and continuous adjustments');

    requests = [];
    stream = camera();
    await ItemCamera.openStream('video', () => true);
    assert(requests[0].video.width.ideal === 3840 && requests[0].video.height.ideal === 2160
      && requests[0].video.frameRate.max === 30, 'Video must request 4K/30fps');
    passed.push('4K video preferences with unsupported autofocus omitted');

    requests = [];
    media.getUserMedia = async constraints => {
      requests.push(constraints);
      if (requests.length < 3) throw new DOMException('Resolution unavailable', 'OverconstrainedError');
      return stream;
    };
    await ItemCamera.openStream('photo', () => true);
    assert(requests.map(r => r.video.width.ideal).join(',') === '4096,3840,1920', 'Photo resolution fallback incorrect');
    passed.push('Photo resolution fallback to 1080p');

    requests = [];
    media.getUserMedia = async constraints => {
      requests.push(constraints);
      if (requests.length < 4) throw new DOMException('Resolution unavailable', 'OverconstrainedError');
      return stream;
    };
    await ItemCamera.openStream('video', () => true);
    assert(requests[0].video.width.ideal === 3840 && requests[1].video.width.ideal === 1920
      && requests[2].video.width.ideal === 1280 && !requests[3].video.width, 'Video defaults fallback incorrect');
    passed.push('Video resolution fallback through 1080p/720p to device defaults');

    requests = [];
    media.getUserMedia = async constraints => {
      requests.push(constraints);
      throw new DOMException('Denied', 'NotAllowedError');
    };
    await reject(() => ItemCamera.openStream('video', () => true), 'NotAllowedError');
    assert(requests.length === 1, 'Permission denials must not retry');
    passed.push('Permission errors propagate without retries');

    let current = true;
    stream = camera();
    media.getUserMedia = async () => { current = false; return stream; };
    assert(await ItemCamera.openStream('photo', () => current) === null, 'Cancelled request returned a stream');
    assert(stream.getTracks()[0].readyState === 'ended', 'Cancelled request leaked tracks');
    passed.push('Late permission streams released after cancellation');

    let attempts = 0;
    current = true;
    media.getUserMedia = async () => { attempts++; current = false; throw new DOMException('Unsupported', 'OverconstrainedError'); };
    assert(await ItemCamera.openStream('video', () => current) === null && attempts === 1, 'Cancelled request retried');
    passed.push('Cancellation prevents fallback retries');

    stream = camera();
    media.getUserMedia = async () => stream;
    stream.getTracks()[0].getCapabilities = () => ({focusMode: ['continuous']});
    stream.getTracks()[0].applyConstraints = async () => { throw new DOMException('Unsupported', 'NotSupportedError'); };
    assert(await ItemCamera.openStream('video', () => true) === stream, 'Unsupported autofocus blocked camera');
    passed.push('Unsupported continuous adjustment keeps camera defaults');
    stream.getTracks()[0].getCapabilities = () => { throw new DOMException('Unavailable', 'NotSupportedError'); };
    assert(await ItemCamera.openStream('video', () => true) === stream, 'Unsupported capabilities blocked camera');
    passed.push('Unsupported capability inspection keeps camera defaults');
    stream.getTracks()[0].getCapabilities = () => ({focusMode: ['continuous']});
    stream.getTracks()[0].applyConstraints = async () => { throw new DOMException('Lost camera', 'NotReadableError'); };
    await reject(() => ItemCamera.openStream('video', () => true), 'NotReadableError');
    assert(stream.getTracks()[0].readyState === 'ended', 'Failed setup leaked tracks');
    passed.push('Unexpected setup failures propagate and release tracks');

    const recorderOptions = [];
    window.MediaRecorder = class {
      constructor(input, options) { recorderOptions.push(options); this.stream = input; }
    };
    ItemCamera.createRecorder(stream, 'video/mp4');
    assert(recorderOptions[0].videoBitsPerSecond === 10000000 && recorderOptions[0].mimeType === 'video/mp4', 'Video quality incorrect');
    stream.getVideoTracks()[0].getSettings = () => ({width: 3840, height: 2160});
    ItemCamera.createRecorder(stream, 'video/mp4');
    assert(recorderOptions[1].videoBitsPerSecond === 20000000, '4K bitrate incorrect');
    passed.push('10 Mbps HD and 20 Mbps 4K encoding requested');
    recorderOptions.length = 0;
    window.MediaRecorder = class {
      constructor(input, options) {
        recorderOptions.push(options);
        if (options.videoBitsPerSecond) throw new DOMException('Unsupported', 'NotSupportedError');
      }
    };
    ItemCamera.createRecorder(stream, 'video/webm');
    assert(recorderOptions.length === 2 && !recorderOptions[1].videoBitsPerSecond, 'Bitrate fallback incorrect');
    passed.push('Unsupported bitrate falls back to browser encoding');

    let canvas;
    let draws = [];
    let qualities = [];
    let sizes = [100];
    document.createElement = function (tag, ...args) {
      if (tag !== 'canvas') return createElement.call(document, tag, ...args);
      canvas = {
        getContext: () => ({drawImage: (...args) => draws.push(args)}),
        toBlob: (callback, type, quality) => {
          assert(type === 'image/jpeg', 'Captured photo must be JPEG');
          qualities.push(quality);
          callback({size: sizes.shift()});
        }
      };
      return canvas;
    };
    const preview = {videoWidth: 3840, videoHeight: 2160};
    window.ImageCapture = undefined;
    await ItemCamera.capturePhoto(preview, camera());
    assert(canvas.width === 3840 && canvas.height === 2160 && draws[0][0] === preview, 'Live frame dimensions changed');
    assert(qualities[0] === 0.95, 'JPEG must start at 95% quality');
    passed.push('High-quality live-frame capture without ImageCapture');

    window.Image = class {
      constructor() { this.naturalWidth = 6000; this.naturalHeight = 4000; }
      set src(value) { this.onload(); }
    };
    window.ImageCapture = class { async takePhoto() { return new Blob(['native still']); } };
    sizes = [100];
    draws = [];
    await ItemCamera.capturePhoto(preview, camera());
    assert(canvas.width === 6000 && canvas.height === 4000 && draws[0][0] !== preview, 'Native still frame not preserved');
    passed.push('Native still capture retains 6000px detail under the 6144px cap');
    window.Image = class {
      constructor() { this.naturalWidth = 8000; this.naturalHeight = 6000; }
      set src(value) { this.onload(); }
    };
    sizes = [100];
    await ItemCamera.capturePhoto(preview, camera());
    assert(canvas.width === 6144 && canvas.height === 4608, 'Oversized still dimensions must be bounded proportionally');
    passed.push('Large stills are bounded to 6144px with aspect ratio preserved');

    const nativeJpeg = new Blob(['native JPEG'], {type: 'image/jpeg'});
    let photoSettings;
    window.ImageCapture = class {
      async getPhotoCapabilities() { return {imageWidth: {max: 8000}, imageHeight: {max: 6000}}; }
      async takePhoto(settings) { photoSettings = settings; return nativeJpeg; }
    };
    const original = await ItemCamera.capturePhoto(preview, camera());
    assert(original === nativeJpeg, 'Native JPEG must not be re-encoded in the browser');
    assert(photoSettings.imageWidth === 8000 && photoSettings.imageHeight === 6000, 'Maximum still dimensions not requested');
    passed.push('Maximum still resolution requested and native JPEG preserved');
    let nativeAttempts = 0;
    window.ImageCapture = class {
      async getPhotoCapabilities() { return {imageWidth: {max: 8000}, imageHeight: {max: 6000}}; }
      async takePhoto(settings) {
        nativeAttempts++;
        if (settings) throw new DOMException('Unavailable resolution', 'OverconstrainedError');
        return nativeJpeg;
      }
    };
    assert(await ItemCamera.capturePhoto(preview, camera()) === nativeJpeg && nativeAttempts === 2,
      'Rejected maximum still settings must retry default native capture');
    passed.push('Unsupported maximum photo resolution retries native defaults');

    window.ImageCapture = class { async takePhoto() { throw new DOMException('Unavailable', 'NotSupportedError'); } };
    sizes = [100];
    await ItemCamera.capturePhoto(preview, camera());
    assert(canvas.width === 3840, 'Native still failure did not fall back');
    passed.push('Unsupported native still capture falls back to live frame');

    window.ImageCapture = undefined;
    sizes = [6 * 1024 * 1024, 5 * 1024 * 1024 + 1, 100];
    qualities = [];
    await ItemCamera.capturePhoto(preview, camera());
    assert(qualities.join(',') === '0.95,0.9,0.85', 'Size-based JPEG fallback incorrect');
    sizes = [10 * 1024 * 1024, 10 * 1024 * 1024, 10 * 1024 * 1024];
    await reject(() => ItemCamera.capturePhoto(preview, camera()), 'Error');
    passed.push('Oversize JPEGs recompress, then report an explicit failure');

    document.createElement = createElement;
    window.Image = saved.get('Image').value;
    const source = document.createElement('canvas');
    source.width = 640;
    source.height = 480;
    source.videoWidth = 640;
    source.videoHeight = 480;
    source.getContext('2d').fillRect(0, 0, 640, 480);
    const jpeg = await ItemCamera.capturePhoto(source, camera());
    const decoded = await createImageBitmap(jpeg);
    assert(jpeg.type === 'image/jpeg' && decoded.width === 640 && decoded.height === 480, 'Real JPEG failed or was upscaled');
    decoded.close();
    passed.push('Real JPEG encoding, decoding and no upscaling');

    const flash = document.createElement('button');
    const flashErrors = [];
    const torch = ItemCamera.bindTorch(flash, message => flashErrors.push(message));
    assert(torch.attach(camera()) === false, 'Unsupported torch must report unavailable');
    assert(flash.hidden && flash.disabled, 'Unsupported torch must remain hidden');
    const torchStream = camera();
    const torchTrack = torchStream.getVideoTracks()[0];
    let lit = false;
    torchTrack.getCapabilities = () => ({torch: true});
    torchTrack.getSettings = () => ({torch: lit});
    torchTrack.applyConstraints = async constraints => { lit = constraints.advanced[0].torch; };
    assert(torch.attach(torchStream) === true, 'Supported torch must report available');
    assert(!flash.hidden && !flash.disabled, 'Supported torch not enabled');
    flash.click();
    await Promise.resolve();
    await Promise.resolve();
    assert(lit && flash.getAttribute('aria-pressed') === 'true', 'Torch failed to turn on');
    flash.click();
    await Promise.resolve();
    await Promise.resolve();
    assert(!lit && flash.getAttribute('aria-pressed') === 'false', 'Torch failed to turn off');
    torchTrack.applyConstraints = async () => { throw new DOMException('Denied', 'NotAllowedError'); };
    flash.click();
    await Promise.resolve();
    await Promise.resolve();
    assert(flashErrors.length === 1 && !flash.disabled && flash.getAttribute('aria-pressed') === 'false',
      'Torch failures must be visible and not claim success');
    let completeTorch;
    torchTrack.applyConstraints = () => new Promise(resolve => { completeTorch = resolve; });
    flash.click();
    torch.reset();
    completeTorch();
    await Promise.resolve();
    await Promise.resolve();
    assert(flash.hidden && flash.disabled && flash.getAttribute('aria-pressed') === 'false',
      'Late torch completion must not re-enable a closed camera');
    passed.push('Torch capability detection, on/off, explicit errors and late-operation cleanup');
    assert(warnings.length >= 8, 'Compatibility fallbacks must log warnings');
    return {passed, count: passed.length};
  } finally {
    document.createElement = createElement;
    console.warn = warn;
    if (mediaDescriptor) Object.defineProperty(navigator, 'mediaDevices', mediaDescriptor);
    else delete navigator.mediaDevices;
    for (const [key, descriptor] of saved) {
      if (descriptor) Object.defineProperty(window, key, descriptor);
      else delete window[key];
    }
  }
};
