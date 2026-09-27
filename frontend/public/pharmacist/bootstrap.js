(async () => {
 try {
  const response = await fetch('/api/medicine/catalog');
  if(!response.ok) throw new Error('Medicine catalog unavailable. Start the backend on port 8000, then reload.');
  window.MADAD_MEDICINE_CATALOG = await response.json();
  for (const src of ['app.js', 'image-search.js']) {
   await new Promise((resolve,reject) => {const script=document.createElement('script');script.src=src;script.onload=resolve;script.onerror=reject;document.body.append(script)});
  }
 } catch(error) { document.getElementById('madad-pharmacist-feedback').textContent=error.message || 'Unable to load the interface. Reload to retry.'; }
})();