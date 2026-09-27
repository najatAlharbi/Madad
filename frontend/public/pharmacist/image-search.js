(() => {
  const root = document.getElementById('madad-interfaces');
  const el = id => root.querySelector('#photo-' + id);
  let stream = null, imageUrl = null, generation = 0, selected = false, selectedFile = null;
  const say = (message, error = false) => { el('panel').hidden = false; el('status').textContent = message; el('status').classList.toggle('is-error', error); };
  const stop = () => { generation++; if (stream) stream.getTracks().forEach(track => track.stop()); stream = null; el('video').srcObject = null; el('live').hidden = true; el('camera').disabled = false; };
  const clear = () => { if (imageUrl) URL.revokeObjectURL(imageUrl); imageUrl = null; selected = false; selectedFile = null; window.MadadMedicine.clear(); el('preview').removeAttribute('src'); el('review').hidden = true; };
  async function preview(file) {
    if (!file) return;
    stop(); clear();
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { say('Choose a JPG, PNG or WebP image. Convert unsupported formats before uploading.', true); return; }
    if (!file.size || file.size > 10 * 1024 * 1024) { say('Choose a non-empty image smaller than 10 MB.', true); return; }
    const ticket = ++generation, url = URL.createObjectURL(file), image = new Image();
    image.onload = () => { if(ticket !== generation) { URL.revokeObjectURL(url); return; } imageUrl = url; selected = true; selectedFile = file; el('preview').src = url; el('review').hidden = false; say('Photo ready. Select Search this image for candidate matches.'); };
    image.onerror = () => { URL.revokeObjectURL(url); if(ticket === generation) say('This image could not be opened. Please choose another photo.', true); };
    image.src = url;
  }
  el('upload').addEventListener('click', () => el('file').click());
  el('fallback').addEventListener('click', () => el('native').click());
  ['file', 'native'].forEach(id => el(id).addEventListener('change', event => { preview(event.target.files[0]); event.target.value = ''; }));
  el('camera').addEventListener('click', async () => {
    stop(); const ticket = generation; el('fallback').hidden = false;
    if (!navigator.mediaDevices?.getUserMedia || !window.isSecureContext) { say('Live camera is unavailable here. Use the device camera button below, or upload a photo. Live camera requires HTTPS or localhost.', true); return; }
    el('camera').disabled = true; say('Allow camera access to photograph the medicine.');
    try {
      const incoming = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
      if(ticket !== generation) { incoming.getTracks().forEach(track => track.stop()); return; }
      stream = incoming; el('video').srcObject = stream; el('live').hidden = false; await el('video').play();
      if(ticket !== generation) return;
      say('Keep the pills in focus, then select Take photo.');
    } catch (error) { if(ticket !== generation) return; stop(); say(error.name === 'NotAllowedError' ? 'Camera access was denied. Allow access in your browser or upload a photo.' : 'The camera could not be opened. Check it is available, or upload a photo.', true); }
  });
  el('capture').addEventListener('click', () => {
    const video = el('video'); if(!video.videoWidth) { say('Wait for the camera preview, then try again.', true); return; }
    const ticket = generation, canvas = document.createElement('canvas'), scale = Math.min(1, 1600 / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale); canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(blob => { if(ticket !== generation) return; if(blob) preview(blob); else say('Capture failed. Please try again.', true); }, 'image/jpeg', 0.9);
  });
  el('close').addEventListener('click', () => { stop(); el('fallback').hidden = true; el('panel').hidden = !selected; el('camera').focus(); });
  el('remove').addEventListener('click', () => { stop(); clear(); el('fallback').hidden = true; el('panel').hidden = true; el('upload').focus(); });
  window.addEventListener('madad-name-search', () => { stop(); clear(); el('panel').hidden = true; el('fallback').hidden = true; });
  el('search').addEventListener('click', async () => {
    if(!selectedFile) return;
    const ticket = ++generation; window.MadadMedicine.clear(); say('Analyzing image…');
    try {
      const response = await fetch('/api/medicine/predict', { method: 'POST', headers: {'Content-Type': selectedFile.type}, body: selectedFile });
      const result = await response.json(); if(ticket !== generation) return;
      if(!response.ok) throw new Error(result.error || (typeof result.detail === 'string' ? result.detail : result.detail?.message) || 'Recognition unavailable.');
      window.MadadMedicine.candidates(result.candidates);
      say('Candidate matches only: this model knows 20 products and may misidentify other objects or medicines. Verify NDC, imprint and prescription.');
    } catch(error) { if(ticket === generation) say(error.message, true); }
  });
  root.querySelectorAll('[data-pharmacist-view]').forEach(button => button.addEventListener('click', () => { if(button.dataset.pharmacistView !== 'search') stop(); }));
  root.querySelector('#madad-continue-dispensing').addEventListener('click', stop);
  document.addEventListener('visibilitychange', () => { if(document.hidden) stop(); });
  window.addEventListener('pagehide', () => { stop(); clear(); });
  root.addEventListener('keydown', event => { if(event.key === 'Escape') stop(); });
})();
