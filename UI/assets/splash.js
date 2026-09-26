(() => {
  const splash = document.getElementById('madad-splash');
  if (!splash) return;

  const minimumDisplayMs = 1850;
  const startedAt = performance.now();
  let dismissalScheduled = false;

  const dismissSplash = () => {
    if (dismissalScheduled) return;
    dismissalScheduled = true;

    const remaining = Math.max(0, minimumDisplayMs - (performance.now() - startedAt));
    window.setTimeout(() => {
      splash.classList.add('is-leaving');
      splash.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('madad-is-loading');

      window.setTimeout(() => splash.remove(), 650);
    }, remaining);
  };

  if (document.readyState === 'complete') {
    dismissSplash();
  } else {
    window.addEventListener('load', dismissSplash, { once: true });
    window.setTimeout(dismissSplash, 2800);
  }
})();
