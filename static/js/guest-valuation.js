/* Camera capture and submission for the public "check my item's value" form. */
(function () {
  'use strict';

  const MIN_PHOTOS = 6;
  const MAX_PHOTOS = 15;
  const $ = id => document.getElementById(id);

  const form = $('guestValueForm');
  const conditionInputs = form.querySelectorAll('input[name="condition"]');
  const categorySelect = $('category');
  const descriptionField = $('description');
  const usageGroup = $('usageDurationGroup');
  const usageInput = $('usage_duration');
  const fileUploadArea = $('fileUploadArea');
  const cameraPanel = $('cameraPanel');
  const cameraPreview = $('cameraPreview');
  const cameraStatus = $('cameraStatus');
  const captureBtn = $('capturePhotoBtn');
  const stopBtn = $('stopCameraBtn');
  const captureStatus = $('cameraCaptureStatus');
  const photoCount = $('cameraPhotoCount');
  const previewBox = $('imagesPreviewContainer');
  const previewGrid = $('imagesPreviewGrid');
  const countLabel = $('imageCount');
  const addMoreBtn = $('addMoreBtn');
  const clearAllBtn = $('clearAllBtn');
  const submitBtn = $('submitBtn');
  const errorBox = $('guestFormError');
  const overlay = $('aiValuationOverlay');
  const subtitle = $('aiValuationSubtitle');
  const loader = ValuationLoader.create({
    loading: $('aiValuationLoading'),
    icon: $('aiLoaderIcon'),
    phrase: $('aiLoaderPhrase'),
    timer: $('aiLoaderTimer'),
    bar: $('aiLoaderBar')
  });
  const photoMeterBar = $('photoMeterBar');
  const photoMeterText = $('photoMeterText');

  let photos = [];
  let previewUrls = [];
  let stream = null;
  let ready = false;
  let busy = false;
  let requestId = 0;
  let sequence = 0;
  let opener = null;

  function currentCondition() {
    const checked = form.querySelector('input[name="condition"]:checked');
    return checked ? checked.value : '';
  }

  function showError(message) {
    errorBox.textContent = message || '';
    errorBox.hidden = !message;
    if (message) errorBox.scrollIntoView({behavior: 'smooth', block: 'center'});
  }

  function setStatus(message) {
    cameraStatus.textContent = message;
    captureStatus.textContent = message;
  }

  function toggleUsage() {
    const used = currentCondition() === 'Fairly Used';
    usageGroup.hidden = !used;
    if (!used) usageInput.value = '';
  }

  // ---------- Description guidance ----------
  // What the AI needs per category. The placeholder disappears once the visitor types, so the key
  // points are also shown as chips under the box.
  const GUIDE = {
    'Phones & Gadgets': {
      basics: 'Brand, model, storage and colour (e.g. iPhone 12, 128GB, black)',
      works: 'Battery health %, screen and touch, cameras, speakers, charging port, Face ID or fingerprint',
      extras: 'Charger, box, receipt, network or iCloud/Google account lock',
      chips: ['Model & storage', 'Battery health', 'Screen & body damage', 'Repairs', 'Network / account lock', 'Charger & box']
    },
    'Consumer Electronics': {
      basics: 'Brand, model, year bought, screen size and key specs',
      works: 'Power-on, display or picture, sound, ports, remote and every function you tested',
      extras: 'Remote, cables, warranty, original box',
      chips: ['Model & year', 'Screen size / specs', 'What you tested', 'Faults', 'Cables & remote', 'Warranty']
    },
    'Fashion Accessories': {
      basics: 'Type, brand, material, size and colour',
      works: 'Clasps, zips, straps, stitching, glass or lens, watch movement or battery',
      extras: 'Receipt or proof it is genuine, box or dust bag',
      chips: ['Brand & type', 'Material & size', 'Wear & marks', 'Genuine proof', 'Box / dust bag']
    },
    'Footwear': {
      basics: 'Brand, model, size (say EU, UK or US), colour and material',
      works: 'Sole and heel wear, creasing, stitching, glue or separation, inside lining',
      extras: 'Original box, extra laces, insoles',
      chips: ['Brand & model', 'Size (EU/UK/US)', 'Sole & heel wear', 'Creasing', 'Original box']
    },
    'Beauty & Personal Care': {
      basics: 'Brand, product type, shade or scent, and size or volume',
      works: 'Seal intact, amount left, texture and smell, packaging damage',
      extras: 'Expiry or batch date, where it was bought',
      chips: ['Brand & product', 'Size / volume', 'Sealed or opened', 'Amount left', 'Expiry date']
    },
    'Gaming & Accessories': {
      basics: 'Console, game or accessory name, model, storage size and region',
      works: 'Buttons, analog stick drift, disc reading, ports, HDMI output, online connection, overheating or fan noise',
      extras: 'Controllers, cables, games or discs included, account or online locks',
      chips: ['Model & storage', 'Stick drift / buttons', 'Disc & ports', 'Online / account lock', 'Controllers & cables']
    },
    'Kitchen Wares & Appliances': {
      basics: 'Type, brand, model, capacity or size, power rating and material',
      works: 'Heating, blending or cooking functions, buttons and dials, lids, seals, cords and plugs',
      extras: 'Parts and accessories included, manual, warranty',
      chips: ['Brand & model', 'Capacity & power', 'What works', 'Dents & rust', 'Parts included']
    }
  };
  const DEFAULT_GUIDE = {
    basics: 'Brand, model, size, colour and key features',
    works: 'Every function or feature you can test',
    extras: 'Accessories, box, receipt or warranty included',
    chips: ['Brand & model', 'Size & colour', 'What works', 'Damage', 'Accessories']
  };

  function buildPlaceholder(condition, category) {
    const g = GUIDE[category] || DEFAULT_GUIDE;
    if (condition === 'Brand New') {
      return [
        'Tell us exactly what you have. The more detail, the more accurate the estimate.',
        '',
        'THE ITEM',
        '• ' + g.basics,
        '• When and where you bought it, and the price you paid if you remember',
        '',
        'PACKAGING & EXTRAS',
        '• Sealed or opened, and whether the box and seals are intact',
        '• ' + g.extras,
        '',
        'ANYTHING ELSE',
        '• Any defects, or say "no defects"'
      ].join('\n');
    }
    return [
      'Be honest and specific. Accurate details give you a fairer estimate.',
      '',
      'THE ITEM',
      '• ' + g.basics,
      '• Year bought and how long you have used it',
      '',
      'WHAT WORKS AND WHAT DOES NOT',
      '• Check: ' + g.works,
      '• Anything faulty, weak or that only works sometimes',
      '',
      'CONDITION',
      '• Scratches, cracks, dents or stains, and exactly where',
      '• Repairs, replaced parts or anything missing',
      '',
      'WHAT COMES WITH IT',
      '• ' + g.extras
    ].join('\n');
  }

  // The placeholder is clipped (not scrollable), so size the box to show all of it.
  function fitToPlaceholder() {
    if (descriptionField.value) {
      descriptionField.style.minHeight = '160px';   // once typing starts, the long placeholder no longer needs the space
      return;
    }
    const style = getComputedStyle(descriptionField);
    const mirror = document.createElement('div');
    mirror.style.cssText = 'position:absolute;visibility:hidden;white-space:pre-wrap;overflow-wrap:break-word;pointer-events:none;';
    mirror.style.width = descriptionField.clientWidth + 'px';
    mirror.style.font = style.font;
    mirror.style.lineHeight = style.lineHeight;
    mirror.style.padding = style.padding;
    mirror.style.boxSizing = 'border-box';
    mirror.textContent = descriptionField.placeholder;
    document.body.appendChild(mirror);
    const needed = mirror.offsetHeight + 8;
    document.body.removeChild(mirror);
    descriptionField.style.minHeight = Math.max(200, needed) + 'px';
  }

  function updateGuidance() {
    const category = categorySelect.value;
    descriptionField.placeholder = buildPlaceholder(currentCondition() || 'Fairly Used', category);
    const list = $('guideList');
    if (list) {
      list.textContent = '';
      (GUIDE[category] || DEFAULT_GUIDE).chips.forEach(text => {
        const chip = document.createElement('li');
        chip.textContent = text;
        list.appendChild(chip);
      });
    }
    fitToPlaceholder();
  }

  function updateDescriptionMeter() {
    const length = descriptionField.value.trim().length;
    $('descCount').textContent = descriptionField.value.length + ' / 2000';
    const bar = $('descMeterBar');
    const text = $('descMeterText');
    let level = 'low';
    let message = 'Add details so the AI can estimate accurately.';
    if (length >= 150) {
      level = 'great';
      message = 'Great. Detailed descriptions give the most accurate estimates.';
    } else if (length >= 60) {
      level = 'ok';
      message = 'Good start. Add condition, damage and what is included for a closer estimate.';
    } else if (length >= 20) {
      level = 'ok';
      message = 'A little more detail will improve the estimate.';
    }
    bar.dataset.level = level;
    bar.style.width = Math.min(100, Math.round(length / 150 * 100)) + '%';
    text.textContent = message;
  }

  conditionInputs.forEach(input => input.addEventListener('change', () => { toggleUsage(); updateGuidance(); }));
  categorySelect.addEventListener('change', updateGuidance);
  descriptionField.addEventListener('input', () => { updateDescriptionMeter(); fitToPlaceholder(); });
  window.addEventListener('resize', fitToPlaceholder);
  toggleUsage();
  updateGuidance();
  updateDescriptionMeter();

  function updateCaptureButton() {
    photoCount.textContent = photos.length + ' / ' + MAX_PHOTOS + ' photos';
    captureBtn.disabled = busy || !ready || !stream || cameraPreview.readyState < 2
      || !cameraPreview.videoWidth || photos.length >= MAX_PHOTOS;
  }

  const torch = ItemCamera.bindTorch($('photoFlashBtn'), setStatus);
  const readiness = ItemCamera.bindReadiness(cameraPreview, $('photoFocusBtn'),
    isReady => { ready = isReady; updateCaptureButton(); }, setStatus);
  $('photoFlashBtn').addEventListener('click', () => readiness.settle());

  function stopCamera() {
    requestId++;
    torch.reset();
    readiness.reset();
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      stream = null;
    }
    cameraPreview.srcObject = null;
    cameraPreview.pause();
    if (cameraPanel.open) cameraPanel.close();
    document.body.classList.remove('item-camera-open');
    fileUploadArea.disabled = false;
    addMoreBtn.disabled = false;
    updateCaptureButton();
    if (opener && !document.hidden) (photos.length ? addMoreBtn : opener).focus({preventScroll: true});
    opener = null;
  }

  async function openCamera() {
    if (photos.length >= MAX_PHOTOS) {
      cameraStatus.textContent = 'Maximum ' + MAX_PHOTOS + ' photos reached. Remove a photo to retake it.';
      return;
    }
    if (stream) return;
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      cameraStatus.textContent = 'In-page capture requires HTTPS and a supported browser. Open the secure site on a camera-enabled device.';
      return;
    }
    const id = ++requestId;
    opener = document.activeElement;
    cameraPanel.showModal();
    document.body.classList.add('item-camera-open');
    fileUploadArea.disabled = true;
    addMoreBtn.disabled = true;
    setStatus('Waiting for camera permission. Please allow access to take your item photos.');
    try {
      const opened = await ItemCamera.openStream('photo', () => id === requestId && !document.hidden);
      if (!opened) return;
      if (id !== requestId || document.hidden) {
        opened.getTracks().forEach(track => track.stop());
        return;
      }
      stream = opened;
      torch.attach(opened);
      opened.getVideoTracks().forEach(track => track.addEventListener('ended', () => {
        if (stream === opened) {
          stopCamera();
          setStatus('Camera access ended. Open the camera again to continue taking photos.');
        }
      }));
      cameraPreview.srcObject = opened;
      await cameraPreview.play();
      if (id !== requestId) return;
      readiness.attach(opened);
      updateCaptureButton();
    } catch (error) {
      if (id !== requestId) return;
      stopCamera();
      const messages = {
        NotAllowedError: 'Camera permission was denied. Allow camera access in your browser settings, then try again.',
        NotFoundError: 'No camera was found. Use a camera-enabled phone or computer.',
        NotReadableError: 'The camera is unavailable or in use by another app. Close that app and try again.',
        OverconstrainedError: 'This camera cannot provide a supported preview. Try another camera-enabled device.'
      };
      setStatus(messages[error.name] || 'The camera could not start. Check camera permissions or try another browser.');
    } finally {
      if (id === requestId) {
        fileUploadArea.disabled = false;
        addMoreBtn.disabled = false;
      }
    }
  }

  function updatePhotoMeter() {
    const count = photos.length;
    photoMeterBar.style.width = Math.min(100, Math.round(count / MIN_PHOTOS * 100)) + '%';
    photoMeterBar.dataset.level = count >= MIN_PHOTOS ? 'great' : 'low';
    photoMeterText.textContent = count >= MIN_PHOTOS
      ? count + ' photos taken. You are ready' + (count < MAX_PHOTOS ? ', or add up to ' + (MAX_PHOTOS - count) + ' more.' : '.')
      : count + ' of ' + MIN_PHOTOS + ' photos taken (minimum). You can add up to ' + MAX_PHOTOS + '.';
  }

  function renderPreviews() {
    previewUrls.forEach(url => URL.revokeObjectURL(url));
    previewUrls = [];
    previewGrid.textContent = '';
    countLabel.textContent = photos.length;
    updateCaptureButton();
    updatePhotoMeter();
    previewBox.hidden = !photos.length;
    fileUploadArea.hidden = photos.length > 0;
    photos.forEach((file, index) => {
      const url = URL.createObjectURL(file);
      previewUrls.push(url);
      const tile = document.createElement('div');
      tile.className = 'gv-photo';
      const image = document.createElement('img');
      image.src = url;
      image.alt = 'Captured photo ' + (index + 1);
      const number = document.createElement('span');
      number.className = 'gv-photo__num';
      number.textContent = index + 1;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'gv-photo__remove';
      remove.title = 'Remove photo ' + (index + 1);
      remove.setAttribute('aria-label', 'Remove photo ' + (index + 1));
      remove.textContent = '✕';
      remove.addEventListener('click', () => {
        photos.splice(index, 1);
        renderPreviews();
        cameraStatus.textContent = 'Photo removed. Open the camera to take a replacement from another angle.';
      });
      tile.append(image, number, remove);
      previewGrid.appendChild(tile);
    });
  }

  fileUploadArea.addEventListener('click', openCamera);
  addMoreBtn.addEventListener('click', openCamera);
  stopBtn.addEventListener('click', () => {
    stopCamera();
    setStatus('Camera closed. Your photos are kept; open the camera to take more.');
  });
  cameraPanel.addEventListener('cancel', event => { event.preventDefault(); stopBtn.click(); });
  cameraPanel.addEventListener('close', () => {
    if (!cameraPanel.open && (stream || document.body.classList.contains('item-camera-open'))) stopCamera();
  });
  cameraPreview.addEventListener('loadeddata', updateCaptureButton);
  cameraPreview.addEventListener('playing', updateCaptureButton);
  window.addEventListener('pagehide', stopCamera);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopCamera();
      setStatus('Camera paused while the page was hidden. Open it again to continue.');
    }
  });

  captureBtn.addEventListener('click', async () => {
    if (captureBtn.disabled || !readiness.isReady() || !stream
        || !stream.getVideoTracks().some(track => track.readyState === 'live')) return;
    const id = requestId;
    busy = true;
    updateCaptureButton();
    try {
      const blob = await ItemCamera.capturePhoto(cameraPreview, stream);
      if (id !== requestId) return;
      photos.push(new File([blob], 'item-camera-' + (++sequence) + '.jpg', {type: 'image/jpeg'}));
      renderPreviews();
      setStatus('Photo ' + photos.length + ' saved. ' + (photos.length < MIN_PHOTOS
        ? 'Take at least ' + (MIN_PHOTOS - photos.length) + ' more from different angles.'
        : 'Take more photos or tap Done to review them.'));
      if (photos.length === MAX_PHOTOS) {
        stopCamera();
        setStatus('All ' + MAX_PHOTOS + ' photos taken. Remove any photo to retake it, or get your estimate.');
      }
    } catch (error) {
      if (id === requestId) setStatus('Photo capture failed. No photo was added. Please try again.');
    } finally {
      busy = false;
      updateCaptureButton();
    }
  });

  clearAllBtn.addEventListener('click', () => {
    stopCamera();
    photos = [];
    renderPreviews();
    cameraStatus.textContent = 'Photos removed. Take at least ' + MIN_PHOTOS + ' new photos from different angles.';
  });

  function openModal(message) {
    subtitle.textContent = message;
    overlay.hidden = false;
    document.body.classList.add('item-camera-open');   // stops the page behind from scrolling
    loader.start();
  }

  function closeModal() {
    loader.stop();
    overlay.hidden = true;
    document.body.classList.remove('item-camera-open');
  }

  function finishWithError(message) {
    showError(message);
    submitBtn.disabled = false;
    submitBtn.classList.remove('loading');
  }

  function markInvalid(...fields) {
    form.querySelectorAll('.gv-field.is-invalid').forEach(field => field.classList.remove('is-invalid'));
    fields.forEach(field => field && field.closest('.gv-field').classList.add('is-invalid'));
  }

  function fail(message, field) {
    markInvalid(field);
    showError(message);
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    showError('');
    markInvalid();
    const nameField = $('name');
    if (!currentCondition()) {
      showError('Please choose whether the item is brand new or fairly used.');
      return;
    }
    if (currentCondition() === 'Fairly Used' && !usageInput.value.trim()) {
      fail('Please tell us how long you have used this item.', usageInput);
      return;
    }
    if (nameField.value.trim().length < 3) {
      fail('Please enter the item name (at least 3 characters).', nameField);
      return;
    }
    if (descriptionField.value.trim().length < 20) {
      fail('Please describe your item in at least 20 characters. More detail gives a better estimate.', descriptionField);
      return;
    }
    if (photos.length < MIN_PHOTOS) {
      cameraStatus.textContent = 'Please take at least ' + MIN_PHOTOS + ' camera photos before submitting.';
      cameraStatus.scrollIntoView({behavior: 'smooth', block: 'center'});
      return;
    }
    stopCamera();

    const data = new FormData();
    const csrf = form.querySelector('[name="csrf_token"]');
    if (csrf) data.append('csrf_token', csrf.value);
    data.append('name', nameField.value);
    data.append('description', descriptionField.value);
    data.append('condition', currentCondition());
    data.append('usage_duration', usageInput.value);
    data.append('category', categorySelect.value);
    photos.forEach(file => data.append('images', file));

    submitBtn.disabled = true;
    submitBtn.classList.add('loading');
    openModal('Uploading your photos…');
    const xhr = new XMLHttpRequest();
    xhr.open('POST', form.action, true);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.upload.addEventListener('progress', e => {
      if (!e.lengthComputable) return;
      subtitle.textContent = 'Uploading your photos… ' + Math.min(99, Math.round(e.loaded / e.total * 100)) + '%';
    });
    xhr.addEventListener('load', () => {
      let result = {};
      try { result = JSON.parse(xhr.responseText); } catch (error) { /* handled below */ }
      if (xhr.status === 409 && result.redirect_url) {
        window.location.href = result.redirect_url;   // this browser already has an estimate
        return;
      }
      if (!result.success) {
        closeModal();
        finishWithError(result.error || 'We could not submit your item. Please try again.');
        return;
      }
      subtitle.textContent = 'Analyzing your item…';
      pollForResult(result.redirect_url);
    });
    xhr.addEventListener('error', () => {
      closeModal();
      finishWithError('Network error while uploading. Please try again.');
    });
    xhr.send(data);
  });

  // The AI runs in the background; wait here (with the loader) until it is ready, then open the result page.
  function pollForResult(resultUrl) {
    const statusUrl = form.dataset.statusUrl;
    const giveUpAt = Date.now() + 5 * 60 * 1000;
    let networkErrors = 0;

    function next(delay) { setTimeout(check, delay); }

    function check() {
      if (Date.now() > giveUpAt) {
        window.location.href = resultUrl;   // the result page keeps waiting and can be reopened later
        return;
      }
      fetch(statusUrl, {headers: {'Accept': 'application/json'}, credentials: 'same-origin'})
        .then(response => response.json().catch(() => ({status: 'missing'})))
        .then(data => {
          networkErrors = 0;
          if (data.status === 'processing') {
            next(2500);
          } else if (data.status === 'ready') {
            loader.finish(() => { window.location.href = resultUrl; });
          } else {
            closeModal();
            finishWithError(data.status === 'failed'
              ? (data.error || 'We could not estimate this item right now. Please try again.')
              : 'Your estimate could not be found. Please try again.');
          }
        })
        .catch(() => {
          networkErrors += 1;
          if (networkErrors >= 5) {
            window.location.href = resultUrl;
          } else {
            next(4000);
          }
        });
    }
    next(2000);
  }
})();
