// Added to every page of a recording. The browser films a page by capturing frames when it repaints, and a page that
// sits still stops producing them, so the recorder can end the video early and lose everything after. One corner pixel
// that changes by 1/255 of brightness is invisible, and keeps the frames coming.
(() => {
  const ID = '__studio_keepalive';
  const start = () => {
    if (!document.documentElement || document.getElementById(ID)) return;
    const dot = document.createElement('div');
    dot.id = ID;
    dot.style.cssText = 'position:fixed;left:0;top:0;width:1px;height:1px;pointer-events:none;z-index:2147483647;background:#000;';
    dot.animate([{ backgroundColor: '#000000' }, { backgroundColor: '#010101' }], { duration: 120, iterations: Infinity, direction: 'alternate' });
    document.documentElement.appendChild(dot);
  };
  start();
  document.addEventListener('DOMContentLoaded', start);
})();
