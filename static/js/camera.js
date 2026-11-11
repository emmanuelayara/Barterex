(function () {
  'use strict';

  async function openStream(kind, isCurrent) {
    const sizes = [[3840, 2160], [1920, 1080], [1280, 720]];
    const profiles = sizes.map(([width, height]) => ({
      facingMode: {ideal: 'environment'}, width: {ideal: width}, height: {ideal: height},
      frameRate: {ideal: 30, max: 30}
    }));
    profiles.push({facingMode: {ideal: 'environment'}});
    for (let index = 0; index < profiles.length; index++) {
      if (!isCurrent()) return null;
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({audio: false, video: profiles[index]});
      } catch (error) {
        if (error.name !== 'OverconstrainedError' || index === profiles.length - 1) throw error;
        console.warn('Camera quality settings unavailable; trying a lower resolution:', error);
        continue;
      }
      if (!isCurrent()) {
        stream.getTracks().forEach(track => track.stop());
        return null;
      }
      try {
        const track = stream.getVideoTracks()[0];
        if (track && typeof track.getCapabilities === 'function' && typeof track.applyConstraints === 'function') {
          const capabilities = track.getCapabilities();
          const continuous = {};
          for (const setting of ['focusMode', 'exposureMode', 'whiteBalanceMode']) {
            if (capabilities[setting] && capabilities[setting].includes('continuous')) continuous[setting] = 'continuous';
          }
          if (Object.keys(continuous).length) {
            await track.applyConstraints({advanced: [continuous]});
          }
        }
      } catch (error) {
        if (['OverconstrainedError', 'NotSupportedError'].includes(error.name)) {
          console.warn('Continuous camera adjustments unavailable; keeping device defaults:', error);
        } else {
          stream.getTracks().forEach(track => track.stop());
          throw error;
        }
      }
      if (!isCurrent()) {
        stream.getTracks().forEach(track => track.stop());
        return null;
      }
      return stream;
    }
  }

  async function capturePhoto(preview, stream) {
    const track = stream.getVideoTracks()[0];
    let photo = null;
    if (typeof window.ImageCapture === 'function') {
      try {
        const capture = new ImageCapture(track);
        if (typeof capture.takePhoto === 'function') {
          let settings = {};
          if (typeof capture.getPhotoCapabilities === 'function') {
            try {
              const capabilities = await capture.getPhotoCapabilities();
              if (capabilities.imageWidth && capabilities.imageHeight) {
                settings = {imageWidth: capabilities.imageWidth.max, imageHeight: capabilities.imageHeight.max};
              }
            } catch (error) {
              if (!['NotSupportedError', 'OperationError', 'UnknownError'].includes(error.name)) throw error;
              console.warn('Still-photo resolution controls unavailable; using camera defaults:', error);
            }
          }
          try {
            photo = await capture.takePhoto(settings);
          } catch (error) {
            if (!['NotSupportedError', 'OverconstrainedError'].includes(error.name) || !Object.keys(settings).length) throw error;
            console.warn('Maximum still-photo resolution unavailable; using camera defaults:', error);
            photo = await capture.takePhoto();
          }
        }
      } catch (error) {
        if (!['NotSupportedError', 'OperationError', 'UnknownError', 'InvalidStateError'].includes(error.name)) throw error;
        console.warn('Full-resolution still capture unavailable; saving the live camera frame:', error);
      }
      // Keep a native JPEG intact when it already fits the upload budget.
      if (photo && photo.type === 'image/jpeg' && photo.size <= 5 * 1024 * 1024) return photo;
    }
    let source = preview;
    let photoUrl = null;
    try {
      if (photo) {
        photoUrl = URL.createObjectURL(photo);
        source = await new Promise((resolve, reject) => {
          const image = new Image();
          image.onload = () => resolve(image);
          image.onerror = () => reject(new Error('The camera photo could not be decoded.'));
          image.src = photoUrl;
        });
      }
      const width = photo ? source.naturalWidth : preview.videoWidth;
      const height = photo ? source.naturalHeight : preview.videoHeight;
      if (!width || !height) throw new Error('The camera is not ready to take a photo.');
      const scale = Math.min(1, 4096 / Math.max(width, height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Image capture is not supported by this browser.');
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = 'high';
      context.drawImage(source, 0, 0, canvas.width, canvas.height);
      for (const quality of [0.95, 0.9, 0.85]) {
        const blob = await new Promise((resolve, reject) => {
          canvas.toBlob(result => result ? resolve(result) : reject(new Error('The camera photo could not be saved.')), 'image/jpeg', quality);
        });
        if (blob.size <= 5 * 1024 * 1024) return blob;
      }
      throw new Error('The camera photo is too large. Try moving back or reducing detail in the background.');
    } finally {
      if (photoUrl) URL.revokeObjectURL(photoUrl);
    }
  }

  function createRecorder(stream, mimeType) {
    try {
      const track = stream.getVideoTracks()[0];
      const settings = typeof track.getSettings === 'function' ? track.getSettings() : {};
      const bitrate = settings.width * settings.height > 1920 * 1080 ? 20000000 : 10000000;
      return new MediaRecorder(stream, {mimeType, videoBitsPerSecond: bitrate});
    } catch (error) {
      if (error.name !== 'NotSupportedError') throw error;
      console.warn('High-quality video encoding unavailable; using the browser bitrate:', error);
      return new MediaRecorder(stream, {mimeType});
    }
  }

  function bindTorch(button, reportError) {
    let track = null;
    let generation = 0;
    let enabled = false;
    function reset() {
      generation++;
      track = null;
      enabled = false;
      button.hidden = true;
      button.disabled = true;
      button.textContent = 'Flash off';
      button.setAttribute('aria-pressed', 'false');
    }
    reset();
    function attach(stream) {
      reset();
      const candidate = stream.getVideoTracks()[0];
      if (!candidate || typeof candidate.getCapabilities !== 'function'
          || typeof candidate.applyConstraints !== 'function') return;
      try {
        if (candidate.getCapabilities().torch !== true) return;
      } catch (error) {
        console.warn('Camera torch capabilities unavailable:', error);
        return;
      }
      track = candidate;
      const settings = typeof track.getSettings === 'function' ? track.getSettings() : {};
      enabled = settings.torch === true;
      button.textContent = enabled ? 'Flash on' : 'Flash off';
      button.setAttribute('aria-pressed', String(enabled));
      button.hidden = false;
      button.disabled = false;
    }
    button.addEventListener('click', async () => {
      if (!track || button.disabled) return;
      const activeTrack = track;
      const token = generation;
      const requested = !enabled;
      button.disabled = true;
      try {
        await activeTrack.applyConstraints({advanced: [{torch: requested}]});
        if (token !== generation) return;
        const settings = typeof activeTrack.getSettings === 'function' ? activeTrack.getSettings() : {};
        if (typeof settings.torch === 'boolean' && settings.torch !== requested) {
          throw new Error('The device did not change its camera light.');
        }
        enabled = requested;
        button.textContent = enabled ? 'Flash on' : 'Flash off';
        button.setAttribute('aria-pressed', String(enabled));
      } catch (error) {
        if (token !== generation) return;
        console.warn('Camera torch could not be changed:', error);
        reportError('The camera light could not be changed. Try again or use better room lighting.');
      } finally {
        if (token === generation) button.disabled = false;
      }
    });
    return {attach, reset};
  }

  window.ItemCamera = {openStream, capturePhoto, createRecorder, bindTorch};
})();
