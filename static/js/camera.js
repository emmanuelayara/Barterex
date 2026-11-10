(function () {
  'use strict';

  async function openStream(kind, isCurrent) {
    const sizes = kind === 'photo' ? [[3840, 2160], [1920, 1080], [1280, 720]] : [[1920, 1080], [1280, 720]];
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
        if (typeof capture.takePhoto === 'function') photo = await capture.takePhoto();
      } catch (error) {
        if (!['NotSupportedError', 'OperationError', 'UnknownError', 'InvalidStateError'].includes(error.name)) throw error;
        console.warn('Full-resolution still capture unavailable; saving the live camera frame:', error);
      }
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
        if (blob.size <= 9 * 1024 * 1024) return blob;
      }
      throw new Error('The camera photo is too large. Try moving back or reducing detail in the background.');
    } finally {
      if (photoUrl) URL.revokeObjectURL(photoUrl);
    }
  }

  function createRecorder(stream, mimeType) {
    try {
      return new MediaRecorder(stream, {mimeType, videoBitsPerSecond: 8000000});
    } catch (error) {
      if (error.name !== 'NotSupportedError') throw error;
      console.warn('High-quality video encoding unavailable; using the browser bitrate:', error);
      return new MediaRecorder(stream, {mimeType});
    }
  }

  window.ItemCamera = {openStream, capturePhoto, createRecorder};
})();
