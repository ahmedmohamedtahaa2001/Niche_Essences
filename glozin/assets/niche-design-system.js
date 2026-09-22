(() => {
  'use strict';

  const root = document.documentElement;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const touchDevice = window.matchMedia('(pointer: coarse)');
  let frameId = null;

  const updateScrollValue = () => {
    frameId = null;
    if (reducedMotion.matches || touchDevice.matches) {
      root.style.setProperty('--scroll-y', '0');
      return;
    }
    root.style.setProperty('--scroll-y', String(window.scrollY));
  };

  const scheduleScrollUpdate = () => {
    if (frameId === null) frameId = window.requestAnimationFrame(updateScrollValue);
  };

  const updatePerformanceMode = () => {
    root.classList.toggle('perf-lite', reducedMotion.matches || touchDevice.matches);
    updateScrollValue();
  };

  window.addEventListener('scroll', scheduleScrollUpdate, { passive: true });
  reducedMotion.addEventListener?.('change', updatePerformanceMode);
  touchDevice.addEventListener?.('change', updatePerformanceMode);
  updatePerformanceMode();
})();
