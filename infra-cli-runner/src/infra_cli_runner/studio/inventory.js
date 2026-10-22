// Runs in the inspected page through page.evaluate. Fixed runner code: nothing from a caller is ever interpolated.
// Reports what a person could act on, plus the headings, and keeps the elements in window.__studioCandidates so the
// runner can check, by identity, that a target it proposes points at the element it came from.
() => {
  const ACTIONABLE = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], ' +
    '[role=tab], [role=menuitem], [role=checkbox], [role=switch], [role=option], [tabindex="0"]';
  const HEADINGS = 'h1, h2, h3';
  const MAX_NAME = 200;

  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();

  const collect = (root, selector, found) => {
    found.push(...root.querySelectorAll(selector));
    for (const element of root.querySelectorAll('*')) {
      if (element.shadowRoot) collect(element.shadowRoot, selector, found);
    }
    return found;
  };

  const visible = (element) => {
    const rect = element.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return false;
    const style = getComputedStyle(element);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    return !element.closest('[aria-hidden="true"], [inert]');
  };

  const roleOf = (element) => {
    const explicit = clean(element.getAttribute('role')).split(' ')[0];
    if (explicit) return explicit;
    const tag = element.tagName.toLowerCase();
    if (tag === 'a') return element.hasAttribute('href') ? 'link' : '';
    if (tag === 'button') return 'button';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'select') return element.multiple || element.size > 1 ? 'listbox' : 'combobox';
    if (/^h[1-6]$/.test(tag)) return 'heading';
    if (tag === 'input') {
      const type = (element.getAttribute('type') || 'text').toLowerCase();
      if (type === 'checkbox' || type === 'radio') return type;
      if (['button', 'submit', 'reset', 'image'].includes(type)) return 'button';
      if (type === 'range') return 'slider';
      if (type === 'number') return 'spinbutton';
      if (type === 'search') return 'searchbox';
      if (type === 'password' || type === 'file' || type === 'color') return '';
      return 'textbox';
    }
    return '';
  };

  const labelledBy = (element) => {
    const root = element.getRootNode();
    const ids = clean(element.getAttribute('aria-labelledby')).split(' ').filter(Boolean);
    return clean(ids.map((id) => root.getElementById ? root.getElementById(id) : null)
      .filter(Boolean).map((node) => node.textContent).join(' '));
  };

  const ownText = (element) => {
    const tag = element.tagName.toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select' ? '' : clean(element.innerText);
  };

  const nameOf = (element) => {
    const tag = element.tagName.toLowerCase();
    let name = clean(element.getAttribute('aria-label')) || labelledBy(element);
    if (!name && element.labels && element.labels.length) {
      name = clean(Array.from(element.labels).map((label) => label.textContent).join(' '));
    }
    if (!name && tag === 'input') {
      const type = (element.getAttribute('type') || 'text').toLowerCase();
      if (['submit', 'button', 'reset'].includes(type)) name = clean(element.value) || clean(element.getAttribute('title'));
      else if (type === 'image') name = clean(element.alt);
      else name = clean(element.placeholder) || clean(element.getAttribute('title'));
    }
    if (!name) name = ownText(element);
    if (!name) {
      const image = element.querySelector('img[alt]');
      name = clean(image ? image.alt : '') || clean(element.getAttribute('title'));
    }
    return name;
  };

  const cssPath = (element) => {
    const parts = [];
    let current = element;
    while (current && current.nodeType === 1) {
      const root = current.getRootNode();
      if (current.id && root.getElementById && root.getElementById(current.id) === current) {
        parts.unshift('#' + CSS.escape(current.id));
        break;
      }
      const tag = current.tagName.toLowerCase();
      const parent = current.parentElement;
      if (!parent) { parts.unshift(tag); break; }
      const same = Array.from(parent.children).filter((child) => child.tagName === current.tagName);
      parts.unshift(same.length > 1 ? `${tag}:nth-of-type(${same.indexOf(current) + 1})` : tag);
      current = parent;
    }
    return parts.join(' > ');
  };

  const headingElements = collect(document, HEADINGS, []).filter(visible);

  const sectionOf = (element) => {
    if (element.closest('nav, [role=navigation]')) return 'navigation';
    const header = element.closest('header, [role=banner]');
    if (header && !header.closest('article, section, main')) return 'header';
    const footer = element.closest('footer, [role=contentinfo]');
    if (footer && !footer.closest('article, section, main')) return 'footer';
    let found = null;
    for (const heading of headingElements) {
      if (heading === element) continue;
      const position = heading.compareDocumentPosition(element);
      if (position & Node.DOCUMENT_POSITION_DISCONNECTED) continue;
      if (position & Node.DOCUMENT_POSITION_FOLLOWING) found = heading;
      else if (position & Node.DOCUMENT_POSITION_PRECEDING) break;
    }
    return found ? clean(found.innerText) : null;
  };

  const pageWidth = Math.max(document.documentElement.scrollWidth, window.innerWidth);
  const pageHeight = Math.max(document.documentElement.scrollHeight, window.innerHeight);
  const fraction = (value, whole) => Math.min(1, Math.max(0, Math.round((value / whole) * 10000) / 10000));

  const stateOf = (element) => {
    const state = [];
    if (element.disabled || element.getAttribute('aria-disabled') === 'true') state.push('disabled');
    if (element.getAttribute('aria-expanded') === 'true') state.push('expanded');
    if (element.checked || element.getAttribute('aria-checked') === 'true') state.push('checked');
    if (element.getAttribute('aria-selected') === 'true') state.push('selected');
    return state;
  };

  window.__studioCandidates = [];
  const items = [];
  const add = (element, kind) => {
    const rect = element.getBoundingClientRect();
    const name = nameOf(element);
    const index = window.__studioCandidates.push(element) - 1;
    items.push({
      index,
      kind,
      role: roleOf(element),
      name: name.slice(0, MAX_NAME),
      name_complete: name.length <= MAX_NAME,
      text: ownText(element).slice(0, MAX_NAME),
      level: kind === 'heading' ? Number(element.tagName.slice(1)) || 2 : 0,
      test_id: element.getAttribute('data-testid') || '',
      dom_id: element.id || '',
      css_path: cssPath(element),
      box: {
        x: fraction(rect.left + window.scrollX, pageWidth),
        y: fraction(rect.top + window.scrollY, pageHeight),
        width: fraction(rect.width, pageWidth),
        height: fraction(rect.height, pageHeight),
      },
      in_first_viewport: rect.bottom > 0 && rect.top < window.innerHeight && rect.right > 0 && rect.left < window.innerWidth,
      section: kind === 'element' ? sectionOf(element) : null,
      state: stateOf(element),
    });
  };

  const seen = new Set();
  for (const element of collect(document, ACTIONABLE, [])) {
    if (seen.has(element) || !visible(element)) continue;
    seen.add(element);
    add(element, 'element');
  }
  for (const element of headingElements) add(element, 'heading');

  return {
    title: document.title || '',
    page_width: pageWidth,
    page_height: pageHeight,
    items,
  };
}
