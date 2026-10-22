// Added to every page of a recorded walkthrough. A headless browser draws no pointer, so without this a demo shows
// things being clicked by nothing. Built with DOM calls only: pages that require Trusted Types refuse innerHTML.
(() => {
  if (window.__studioCursorInstalled) return;
  window.__studioCursorInstalled = true;
  const SVG = 'http://www.w3.org/2000/svg';
  let cursor = null;

  const ensure = () => {
    if (cursor && cursor.isConnected) return cursor;
    cursor = document.createElement('div');
    cursor.id = '__studio_cursor';
    cursor.style.cssText = 'position:fixed;left:0;top:0;width:24px;height:24px;margin:0;pointer-events:none;' +
      'z-index:2147483647;will-change:transform;';
    const svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', '24');
    svg.setAttribute('height', '24');
    const arrow = document.createElementNS(SVG, 'path');
    arrow.setAttribute('d', 'M4 2 L4 20 L9 15 L13 23 L16 21.5 L12 14 L19 14 Z');
    arrow.setAttribute('fill', '#111');
    arrow.setAttribute('stroke', '#fff');
    arrow.setAttribute('stroke-width', '1.5');
    svg.appendChild(arrow);
    cursor.appendChild(svg);
    document.documentElement.appendChild(cursor);
    return cursor;
  };

  const place = (x, y) => { ensure().style.transform = `translate(${x - 4}px, ${y - 2}px)`; };

  const ripple = (x, y) => {
    const ring = document.createElement('div');
    ring.style.cssText = `position:fixed;left:${x - 18}px;top:${y - 18}px;width:36px;height:36px;border-radius:50%;` +
      'border:3px solid rgba(37,99,235,.9);pointer-events:none;z-index:2147483647;';
    document.documentElement.appendChild(ring);
    ring.animate([{ transform: 'scale(.3)', opacity: 1 }, { transform: 'scale(1.2)', opacity: 0 }],
      { duration: 450, easing: 'ease-out' }).onfinish = () => ring.remove();
  };

  addEventListener('mousemove', (event) => place(event.clientX, event.clientY), true);
  addEventListener('mousedown', (event) => { place(event.clientX, event.clientY); ripple(event.clientX, event.clientY); }, true);
})();
