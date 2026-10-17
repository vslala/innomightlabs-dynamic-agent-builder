import { createInterface } from 'node:readline';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';


export const MAX_LINE = 2 * 1024 * 1024;
const fail = code => { throw new HostError(code); };
export class HostError extends Error { constructor(code) { super(code); this.code = code; } }
const bounded = (n, min, max) => Number.isFinite(n) && n >= min && n <= max;
const text = (s, max = 2048) => typeof s === 'string' && s.length > 0 && Buffer.byteLength(s) <= max;
export function origin(raw) {
  if (!text(raw, 8192)) fail('invalidURL');
  let url;
  try { url = new URL(raw); } catch { fail('invalidURL'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) fail('invalidURL');
  return url.origin;
}
export function validateLaunch(c) {
  if (!text(c.profileDir, 8192) || !c.profileDir.startsWith('/') || !c.window ||
      !Number.isInteger(c.window.width) || !bounded(c.window.width, 320, 7680) ||
      !Number.isInteger(c.window.height) || !bounded(c.window.height, 240, 4320) ||
      !Array.isArray(c.allowedOrigins) || !bounded(c.allowedOrigins.length, 1, 64)) fail('invalidLaunch');
  const allowed = c.allowedOrigins.map(raw => {
    if (!text(raw)) fail('invalidOrigin');
    const result = origin(raw), u = new URL(raw);
    if (!['', '/'].includes(u.pathname) || u.search || u.hash) fail('invalidOrigin');
    return result;
  });
  if (new Set(allowed).size !== allowed.length || !allowed.includes(origin(c.startURL))) fail('invalidOrigin');
  return new Set(allowed);
}
export function navigationAllowed(url, allowed, userControl, calibrationURL = null) {
  // This exception is exact, host-owned, and is never accepted by goto.
  if (calibrationURL !== null && url === calibrationURL) return true;
  try { return userControl ? !!origin(url) : allowed.has(origin(url)); } catch { return false; }
}
export function validateCandidate(c) {
  if (!c || typeof c !== 'object' || Object.keys(c).some(k => !['testId', 'role', 'name', 'text', 'css'].includes(k))) fail('invalidLocator');
  const kinds = ['testId', 'role', 'text', 'css'].filter(k => c[k] !== undefined);
  if (kinds.length !== 1 || !text(c[kinds[0]]) || (c.role === undefined ? c.name !== undefined : !text(c.name))) fail('invalidLocator');
  if (c.css && /iframe|frame|>>>/i.test(c.css)) fail('framesUnsupported');
  return kinds[0];
}
export function validatePacing(p) {
  if (!p || !bounded(p.moveSeconds, 0, 5) || !Number.isInteger(p.steps) || !bounded(p.steps, 1, 240) ||
      !Number.isInteger(p.typeDelayMs) || !bounded(p.typeDelayMs, 0, 200)) fail('invalidPacing');
}
export function sensitiveInput(info) {
  const type = (info.type ?? '').toLowerCase();
  const autocomplete = (info.autocomplete ?? '').toLowerCase();
  const identity = [info.name, info.id, info.label, info.placeholder].filter(Boolean).join(' ');
  return ['password', 'email', 'hidden', 'file'].includes(type) ||
    /(?:password|username|email|one-time-code|cc-|webauthn)/i.test(autocomplete) ||
    /(?:pass(?:word|code)?|secret|token|api.?key|credential|log.?in|sign.?in|user.?name|e.?mail|otp|verification.?code|credit.?card)/i.test(identity);
}
export function inputIdentity(el) {
  const labelText = node => {
    if (!node || node === el || node.isContentEditable || node.matches?.('input,textarea,[contenteditable]')) return '';
    const copy = node.cloneNode(true);
    for (const field of copy.querySelectorAll('input,textarea,[contenteditable]')) field.remove();
    return copy.textContent;
  };
  const referencedLabels = (el.getAttribute('aria-labelledby') ?? '').split(/\s+/)
    .filter(Boolean).map(id => labelText(el.ownerDocument.getElementById(id)));
  const clean = value => (value ?? '').replace(/\s+/g, ' ').trim();
  const ariaLabel = el.getAttribute('aria-label');
  const associatedLabels = [...new Set([...(el.labels ?? []), el.closest?.('label')].filter(Boolean))].map(labelText);
  return { type: el.getAttribute('type'), autocomplete: el.getAttribute('autocomplete'),
    name: el.getAttribute('name'), id: el.id,
    // Security examines every source, even those overridden in the accessible name.
    label: [ariaLabel, ...associatedLabels, ...referencedLabels].filter(Boolean).join(' '),
    accessibleName: clean(referencedLabels.join(' ')) || clean(ariaLabel) || clean(associatedLabels.join(' ')),
    placeholder: el.getAttribute('placeholder') ?? el.getAttribute('aria-placeholder') };
}

// Fetch pauses every document request before network dispatch, including redirect successors.
// Playwright routing alone only sees the first request of a redirect chain in 1.52.
export async function installDocumentGuard(session, { allowed, refused, failed }) {
  await session.send('Page.enable');
  const tree = (await session.send('Page.getFrameTree')).frameTree;
  let mainFrameID = tree.frame.id;
  const subframes = new Set();
  const rememberChildren = node => {
    for (const child of node.childFrames ?? []) { subframes.add(child.frame.id); rememberChildren(child); }
  };
  rememberChildren(tree);
  session.on('Page.frameAttached', ({ frameId }) => subframes.add(frameId));
  session.on('Page.frameDetached', ({ frameId }) => subframes.delete(frameId));
  session.on('Page.frameNavigated', ({ frame }) => {
    if (!frame.parentId) { mainFrameID = frame.id; subframes.delete(frame.id); }
    else subframes.add(frame.id);
  });
  session.on('Fetch.requestPaused', event => {
    void (async () => {
      // Unknown frame identities fail closed as top-level documents, not unrestricted subframes.
      const main = event.frameId === mainFrameID || !subframes.has(event.frameId);
      if (allowed(event.request.url, main)) {
        await session.send('Fetch.continueRequest', { requestId: event.requestId });
      } else {
        await session.send('Fetch.failRequest', { requestId: event.requestId, errorReason: 'BlockedByClient' });
        if (main) refused(event.request.url);
      }
    })().catch(failed);
  });
  await session.send('Fetch.enable', { patterns: [{ urlPattern: '*', resourceType: 'Document', requestStage: 'Request' }] });
}



// What a demonstration reports, after the host has checked it. The page is the user's own, but the
// script that describes their clicks runs inside it, so nothing it sends is trusted as shaped.
export function sanitizeInteraction(value) {
  if (!value || typeof value !== 'object') return null;
  const rect = r => r && ['x', 'y', 'width', 'height'].every(k => bounded(r[k], -1e6, 1e6)) && r.width > 0 && r.height > 0
    ? { x: r.x, y: r.y, width: r.width, height: r.height } : null;
  const target = t => {
    if (!t || !Array.isArray(t.candidates)) return null;
    const candidates = [];
    for (const c of t.candidates.slice(0, 16)) {
      try { validateCandidate(c); } catch { continue; }
      // A second fence behind the page's own: a field that names itself like a credential is never reported.
      if (sensitiveInput({ label: c.name ?? c.text ?? '', name: c.testId ?? '' })) return 'sensitive';
      candidates.push(c);
    }
    if (!candidates.length) return null;
    const hint = rect(t.hintRect);
    return hint ? { candidates, hintRect: hint } : { candidates };
  };
  switch (value.kind) {
    case 'click': {
      const t = target(value.target), r = rect(value.rect);
      if (t === 'sensitive') return { kind: 'sensitiveInput' };
      return t && r ? { kind: 'click', target: t, rect: r } : null;
    }
    case 'input': {
      const t = target(value.target);
      if (t === 'sensitive') return { kind: 'sensitiveInput' };
      return t && typeof value.value === 'string' && Buffer.byteLength(value.value) <= 4096
        ? { kind: 'input', target: t, value: value.value } : null;
    }
    case 'press':
      return typeof value.key === 'string' && /^(?:(?:Control|Meta|Alt|Shift)\+)*(?:Enter|Escape|Tab)$/.test(value.key) ? { kind: 'press', key: value.key } : null;
    case 'scroll': {
      if (!bounded(value.x, -1e7, 1e7) || !bounded(value.y, -1e7, 1e7)) return null;
      if (value.target == null) return { kind: 'scroll', x: value.x, y: value.y };
      const t = target(value.target);
      if (t === 'sensitive') return { kind: 'sensitiveInput' };
      return t ? { kind: 'scroll', x: value.x, y: value.y, target: t } : null;
    }
    case 'sensitiveInput': return { kind: 'sensitiveInput' };
    default: return null;
  }
}

// Runs inside every top-level document while a demonstration is recorded. It describes what the user
// does in terms a page can be searched for — role and name, test id, text — never coordinates, and
// never reports a field that looks like a credential. Self-contained: it is sent to the page as text.
export function auraCapture(sensitiveInput, inputIdentity) {
  if (window !== window.top) return;
  let stopped = false;
  let delivery = Promise.resolve();
  const send = payload => {
    if (stopped) return;
    delivery = delivery.then(() => window.__auraCapture(payload)).catch(() => {});
  };
  const scrolls = new Map();
  const inputs = new Map();
  const flushScrolls = () => {
    const values = [];
    for (const { timer, interaction } of scrolls.values()) { clearTimeout(timer); values.push(interaction); }
    scrolls.clear();
    return values;
  };
  const flushInputs = () => {
    const values = [];
    for (const [el, interaction] of inputs) {
      values.push(sensitive(el) ? { kind: 'sensitiveInput' } : interaction);
    }
    inputs.clear();
    return values;
  };
  const sendScrolls = () => { for (const interaction of flushScrolls()) send(interaction); };
  const sendInputs = () => { for (const interaction of flushInputs()) send(interaction); };
  const sendPending = () => { sendScrolls(); sendInputs(); };
  window.__auraFlushCapture = async () => {
    const interactions = [...flushScrolls(), ...flushInputs()];
    stopped = true;
    await delivery;
    return interactions;
  };
  const INTERACTIVE = '[contenteditable]:not([contenteditable=false]),button,a[href],input,select,textarea,summary,label,[role=button],[role=link],[role=tab],[role=menuitem],[role=checkbox],[role=switch],[role=option],[onclick]';
  const TEXT_FIELD = el => el.isContentEditable || el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' &&
    !['checkbox', 'radio', 'button', 'submit', 'reset', 'image', 'file', 'range', 'color'].includes((el.getAttribute('type') || 'text').toLowerCase()));
  const clean = s => (s ?? '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const roleOf = el => {
    const explicit = clean(el.getAttribute('role')).split(' ')[0];
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase(), type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'button') return 'button';
    if (tag === 'a' && el.hasAttribute('href')) return 'link';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea' || el.isContentEditable) return 'textbox';
    if (tag === 'summary') return 'button';
    if (/^h[1-6]$/.test(tag)) return 'heading';
    if (tag === 'input') {
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (['button', 'submit', 'reset', 'image'].includes(type)) return 'button';
      return 'textbox';
    }
    return '';
  };
  const contentText = el => {
    if (!el.querySelector('input,textarea,[contenteditable]')) return clean(el.innerText);
    const copy = el.cloneNode(true);
    for (const field of copy.querySelectorAll('input,textarea,[contenteditable]')) field.remove();
    return clean(copy.textContent);
  };
  const nameOf = el => {
    const identity = inputIdentity(el);
    if (identity.accessibleName) return identity.accessibleName;
    // An editor's contents are its value, never a stable accessible name or locator.
    if (TEXT_FIELD(el)) return clean(el.getAttribute('title')) || clean(identity.placeholder);
    if (el.tagName === 'INPUT' && ['button', 'submit', 'reset'].includes((el.getAttribute('type') || '').toLowerCase())) return clean(el.value);
    return contentText(el) || clean(el.getAttribute('alt')) || clean(el.getAttribute('title')) || clean(el.getAttribute('placeholder'));
  };
  const cssPath = el => {
    const parts = [];
    for (let node = el, depth = 0; node && node.nodeType === 1 && depth < 6; node = node.parentElement, depth++) {
      if (node.id && document.querySelectorAll(`#${CSS.escape(node.id)}`).length === 1) { parts.unshift(`#${CSS.escape(node.id)}`); break; }
      const tag = node.tagName.toLowerCase();
      const same = node.parentElement ? [...node.parentElement.children].filter(c => c.tagName === node.tagName) : [node];
      parts.unshift(same.length > 1 ? `${tag}:nth-of-type(${same.indexOf(node) + 1})` : tag);
      if (node === document.body) break;
    }
    return parts.join(' > ');
  };
  const candidatesFor = el => {
    const result = [];
    const attr = ['data-testid', 'data-test', 'data-qa'].find(a => el.hasAttribute(a));
    if (attr) {
      const found = [...document.querySelectorAll(`[data-testid=${JSON.stringify(el.getAttribute(attr))}],[data-test=${JSON.stringify(el.getAttribute(attr))}],[data-qa=${JSON.stringify(el.getAttribute(attr))}]`)].filter(visible);
      if (found.length === 1 && el.getAttribute(attr)) result.push({ testId: el.getAttribute(attr) });
    }
    const role = roleOf(el), name = nameOf(el);
    if (role && name && name.length <= 200) {
      const same = [...document.querySelectorAll(INTERACTIVE + ',[role],h1,h2,h3,h4,h5,h6')]
        .filter(o => visible(o) && roleOf(o) === role && nameOf(o) === name);
      if (same.length === 1) result.push({ role, name });
    }
    const text = contentText(el);
    if (text && text.length <= 120 && !TEXT_FIELD(el)) {
      const holders = [...document.querySelectorAll('body *')].filter(o => visible(o) && clean(o.innerText) === text &&
        ![...o.children].some(c => clean(c.innerText) === text));
      if (holders.length === 1 && holders[0] === el) result.push({ text });
    }
    const css = cssPath(el);
    if (css && !/frame/i.test(css) && document.querySelectorAll(css).length === 1) result.push({ css });
    return result;
  };
  const describe = el => {
    const candidates = candidatesFor(el);
    if (!candidates.length) return null;
    const r = el.getBoundingClientRect();
    return { target: { candidates, hintRect: { x: r.x, y: r.y, width: r.width, height: r.height } },
      rect: { x: r.x, y: r.y, width: r.width, height: r.height } };
  };
  const sensitive = el => el?.tagName && TEXT_FIELD(el) && sensitiveInput(inputIdentity(el));
  const editable = el => {
    if (!(el instanceof Element)) return null;
    if (!el.isContentEditable) return TEXT_FIELD(el) ? el : null;
    while (el.parentElement?.isContentEditable) el = el.parentElement;
    return el;
  };
  const interactive = el => editable(el) ?? el.closest?.(INTERACTIVE) ?? el;

  document.addEventListener('focusin', e => {
    if (!e.isTrusted || stopped) return;
    sendPending();
    if (sensitive(editable(e.target))) send({ kind: 'sensitiveInput' });
  }, true);
  document.addEventListener('blur', e => { if (e.isTrusted && !stopped) sendPending(); }, true);
  // Mouse handlers can submit and clear an editor before click or blur is dispatched.
  document.addEventListener('pointerdown', e => { if (e.isTrusted && !stopped) sendPending(); }, true);
  document.addEventListener('click', e => {
    if (!e.isTrusted || stopped || !(e.target instanceof Element)) return;
    sendPending();
    const el = interactive(e.target);
    if (sensitive(el)) { send({ kind: 'sensitiveInput' }); return; }
    // Focusing a field is not a step on its own: the text typed into it is.
    if (TEXT_FIELD(el)) return;
    const d = describe(el);
    if (d) send({ kind: 'click', ...d });
  }, true);
  document.addEventListener('input', e => {
    const el = editable(e.target);
    if (!e.isTrusted || stopped || !el) return;
    sendScrolls();
    if (sensitive(el)) { inputs.delete(el); send({ kind: 'sensitiveInput' }); return; }
    if (inputs.size && !inputs.has(el)) sendInputs();
    const d = describe(el);
    if (d) inputs.set(el, { kind: 'input', target: d.target,
      value: el.isContentEditable ? el.innerText : el.value });
  }, true);
  document.addEventListener('keydown', e => {
    if (!e.isTrusted || stopped || !['Enter', 'Escape', 'Tab'].includes(e.key) || e.isComposing || e.keyCode === 229) return;
    const el = editable(e.target);
    if (sensitive(el)) { sendPending(); send({ kind: 'sensitiveInput' }); return; }
    // Shift+Enter edits multiline text. Its native input event supplies the newline in the fill.
    if (e.key === 'Enter' && e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey &&
        (el?.tagName === 'TEXTAREA' || el?.isContentEditable)) return;
    // Snapshot before the app's handler: chat submit commonly clears the value synchronously.
    sendPending();
    const key = [e.ctrlKey && 'Control', e.metaKey && 'Meta', e.altKey && 'Alt', e.shiftKey && 'Shift', e.key].filter(Boolean).join('+');
    send({ kind: 'press', key });
  }, true);
  document.addEventListener('scroll', e => {
    if (!e.isTrusted || stopped) return;
    const root = e.target === document || e.target === document.scrollingElement;
    const el = root ? document.scrollingElement : e.target;
    if (!(el instanceof Element) || /^(IFRAME|FRAME)$/.test(el.tagName) || sensitive(el)) return;
    sendInputs();
    const description = root ? null : describe(el);
    if (!root && !description) return;
    const interaction = { kind: 'scroll', x: el.scrollLeft, y: el.scrollTop,
      ...(root ? {} : { target: description.target }) };
    clearTimeout(scrolls.get(el)?.timer);
    // Refresh insertion order too: two containers must keep the order of their latest changes.
    scrolls.delete(el);
    const timer = setTimeout(() => { scrolls.delete(el); send(interaction); }, 400);
    scrolls.set(el, { timer, interaction });
  }, { passive: true, capture: true });
}

export async function resolveTarget(page, target) {
  if (!target || !Array.isArray(target.candidates) || !bounded(target.candidates.length, 1, 16)) fail('invalidLocator');
  for (const c of target.candidates) {
    const kind = validateCandidate(c);
    let locator;
    if (kind === 'testId') {
      // JSON quoting escapes selector string content, rather than interpolating executable selectors.
      const value = JSON.stringify(c.testId);
      locator = page.locator(`[data-testid=${value}], [data-test=${value}], [data-qa=${value}]`);
    } else if (kind === 'role') locator = page.getByRole(c.role, { name: c.name, exact: true });
    else if (kind === 'text') locator = page.getByText(c.text, { exact: true });
    else locator = page.locator(c.css);
    const visible = locator.filter({ visible: true });
    const count = await visible.count();
    if (count > 1) fail('ambiguousLocator');
    if (count === 1) {
      if (await visible.evaluate(el => /^(IFRAME|FRAME)$/.test(el.tagName))) fail('framesUnsupported');
      return { locator: visible, matched: kind };
    }
  }
  fail('elementNotFound');
}

const BACKGROUND = [32, 48, 64];
const COLORS = [[255, 0, 64], [0, 255, 64], [64, 0, 255], [255, 224, 0]];
// Keep markers clear of native rounded corners and the clipped top viewport edge.
const MARKER_INSET = 32, MARKER_SIZE = 16;
const calibrationHTML = `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{margin:0;width:100%;height:100%;overflow:hidden;background:rgb(${BACKGROUND})}i{position:fixed;width:${MARKER_SIZE}px;height:${MARKER_SIZE}px}</style></head><body>${COLORS.map((c, i) => `<i style="${i % 2 ? 'right' : 'left'}:${MARKER_INSET}px;${i < 2 ? 'top' : 'bottom'}:${MARKER_INSET}px;background:rgb(${c})"></i>`).join('')}</body></html>`;
export const CALIBRATION_URL = `data:text/html;charset=utf-8,${encodeURIComponent(calibrationHTML)}`;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

export class BrowserHost {
  constructor(emit = () => {}) {
    this.emit = emit; this.context = null; this.page = null; this.allowed = new Set();
    this.userControl = false; this.capturing = false; this.calibrating = false; this.pointer = { x: 0, y: 0 }; this.chromePid = null;
  }
  // While a demonstration is recorded the user holds the browser the whole time, and what they do is the
  // point, so events are not muted the way they are during a login handover.
  event(value) { if (!this.userControl || this.capturing) this.emit(value); }
  async metrics() {
    return this.page.evaluate(() => ({ width: innerWidth, height: innerHeight, devicePixelRatio }));
  }
  async guard({ allowBlank = false, allowNavigation = false } = {}) {
    if (!this.page || this.page.isClosed()) fail('notRunning');
    if (this.userControl) fail('userControl');
    // An explicit allowlisted goto can recover a browser error document without interacting with it.
    if (allowNavigation || (allowBlank && this.page.url() === 'about:blank')) return;
    if (!navigationAllowed(this.page.url(), this.allowed, false, this.calibrating ? CALIBRATION_URL : null)) fail('originRefused');
  }
  async launch(c) {
    if (this.context) fail('alreadyRunning');
    this.allowed = validateLaunch(c);
    if (c.capture !== undefined && c.capture !== null && typeof c.capture !== 'boolean') fail('invalidLaunch');
    this.capturing = c.capture === true;
    // Import only at launch: pure validation and locator tests do not require Playwright or Chrome.
    // The signed script lives in the app bundle, not beside the consent-installed dependency.
    const engineRequire = createRequire(resolve(process.cwd(), 'package.json'));
    const { chromium } = engineRequire('playwright-core');
    this.context = await chromium.launchPersistentContext(c.profileDir, {
      channel: 'chrome', headless: false, viewport: null, serviceWorkers: 'block',
      // A dedicated profile can retain an unclean-exit marker after cancellation or a crash.
      // Chrome's native restore bubble covers the calibration markers and appears in window captures.
      args: [`--window-size=${c.window.width},${c.window.height}`, '--hide-crash-restore-bubble'],
      ignoreDefaultArgs: ['--enable-automation'], timeout: 30000,
    });
    this.context.setDefaultTimeout(10000);
    this.context.setDefaultNavigationTimeout(20000);
    this.page = this.context.pages()[0] ?? await this.context.newPage();
    // Before the popup's first response Playwright may have no Frame at all. Unknown documents
    // are potential popups, never subframes, and must be refused before route.continue().
    await this.context.route('**/*', async route => {
      const request = route.request();
      if (request.isNavigationRequest()) {
        let frame;
        try { frame = request.frame(); } catch { /* Initial popup request has no Frame yet. */ }
        const main = !frame || frame.parentFrame() === null;
        const popup = !frame || (main && frame.page() !== this.page);
        const permitted = main ? navigationAllowed(request.url(), this.allowed, this.userControl,
          !popup && this.calibrating ? CALIBRATION_URL : null) : navigationAllowed(request.url(), this.allowed, true);
        if (!permitted || (popup && !this.userControl)) {
          if (main) this.event({ event: 'navigationRefused', url: this.safeURL(request.url()) });
          await route.abort(); return;
        }
      }
      await route.continue();
    });
    await installDocumentGuard(await this.context.newCDPSession(this.page), {
      allowed: (url, main) => main ? navigationAllowed(url, this.allowed, this.userControl,
        this.calibrating ? CALIBRATION_URL : null) : navigationAllowed(url, this.allowed, true),
      refused: url => this.event({ event: 'navigationRefused', url: this.safeURL(url) }),
      failed: () => {
        this.emit({ event: 'closed', reason: 'documentGuardFailed' });
        void this.close().catch(() => {});
      },
    });
    this.context.on('page', popup => {
      if (popup !== this.page && !this.userControl) {
        this.event({ event: 'closed', reason: 'popupRefused' });
        void popup.close().catch(() => {});
      }
    });
    for (const extra of this.context.pages()) if (extra !== this.page) await extra.close();
    await this.context.exposeBinding('__auraViewport', ({ page, frame }, value) => {
      if (page === this.page && frame === page.mainFrame() && value &&
          bounded(value.width, 1, 20000) && bounded(value.height, 1, 20000)) {
        this.event({ event: 'viewportResized', width: value.width, height: value.height });
      }
    });
    await this.context.addInitScript(() => {
      if (window !== window.top) return;
      window.addEventListener('resize', () => {
        void window.__auraViewport({ width: innerWidth, height: innerHeight });
      });
    });
    if (this.capturing) {
      await this.context.exposeBinding('__auraCapture', ({ page, frame }, value) => {
        // Only the main frame of the recorded page, and only while it is on an approved origin: an
        // identity provider's page is never described, whatever its script sends.
        if (!this.capturing || page !== this.page || frame !== page.mainFrame()) return;
        if (!navigationAllowed(page.url(), this.allowed, false)) return;
        const interaction = sanitizeInteraction(value);
        if (interaction) this.emit({ event: 'captured', interaction });
      });
      await this.context.addInitScript({ content: `(() => {\n${sensitiveInput}\n${inputIdentity}\n(${auraCapture})(sensitiveInput, inputIdentity);\n})();` });
      this.userControl = true;
    }
    this.page.on('framenavigated', frame => {
      if (frame !== this.page.mainFrame()) return;
      const url = frame.url();
      // A refused network request may commit Chromium's internal error document; it sent no
      // external request and remains non-interactive to the host until an explicit allowlisted goto.
      if (url === 'about:blank' || url === 'chrome-error://chromewebdata/' || (this.calibrating && url === CALIBRATION_URL)) return;
      if (!navigationAllowed(url, this.allowed, this.userControl)) {
        this.event({ event: 'navigationRefused', url: this.safeURL(url) });
        // Defense in depth for non-network commits; Fetch is the pre-dispatch origin guard.
        void this.page.close().catch(() => {});
      } else {
        let clean = false;
        try { const u = new URL(url); clean = !u.search && !u.hash; } catch { /* unparseable is not clean */ }
        this.event({ event: 'navigated', url: this.safeURL(url), clean });
      }
    });
    this.page.on('close', () => this.emit({ event: 'closed', reason: 'pageClosed' }));
    this.context.on('close', () => this.emit({ event: 'closed', reason: 'browserClosed' }));
    const children = processTree();
    const chrome = children.find(p => p.ppid === process.pid && /Google Chrome/.test(p.name));
    if (!chrome) fail('chromePIDUnavailable');
    this.chromePid = chrome.pid;
    // Playwright starts persistent contexts at about:blank. ReplayEngine owns all site navigation.
    if (this.page.url() !== 'about:blank') fail('unexpectedStartupPage');
    return { chromePid: this.chromePid };
  }
  safeURL(raw) {
    // URLs may contain auth codes or tokens. Events contain only origin/path, never query/hash/userinfo.
    try { const u = new URL(raw); return ['http:', 'https:'].includes(u.protocol) ? `${u.origin}${u.pathname}` : 'about:blank'; }
    catch { return 'about:blank'; }
  }
  async setUserControl(enabled) {
    if (typeof enabled !== 'boolean' || !this.context) fail('invalidControl');
    // A demonstration keeps the browser with the user until it is closed.
    if (this.capturing) fail('capturing');
    if (!enabled) {
      if (!this.page || this.page.isClosed()) fail('notRunning');
      // A premature Resume is not a Stop. Preserve the user's login page and popup work.
      if (!navigationAllowed(this.page.url(), this.allowed, false)) fail('notReady');
      for (const page of this.context.pages()) if (page !== this.page) await page.close();
      this.userControl = false;
    } else this.userControl = true;
    return {};
  }
  async navigateForHandover(url) {
    if (!this.userControl) fail('userControlRequired');
    if (!this.page || this.page.isClosed()) fail('notRunning');
    // Only the initial destination is allowlisted. The existing user-control request guard permits
    // HTTP(S) identity-provider redirects, without granting the automated action vocabulary.
    if (!this.allowed.has(origin(url))) fail('originRefused');
    this.calibrating = false;
    await this.page.goto(url, { waitUntil: 'domcontentloaded' });
    return {};
  }
  async flushCapture() {
    if (!this.capturing || !this.page || this.page.isClosed()) return { interactions: [] };
    if (!navigationAllowed(this.page.url(), this.allowed, false)) return { interactions: [] };
    let pending;
    try {
      pending = await this.page.evaluate(async () => {
        // Let native wheel scrolling dispatch its scroll event before taking the final snapshot.
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        return window.__auraFlushCapture ? window.__auraFlushCapture() : [];
      });
    } catch (error) {
      if (!this.page || this.page.isClosed()) return { interactions: [] };
      throw error;
    }
    this.capturing = false;
    return { interactions: pending.map(sanitizeInteraction).filter(Boolean) };
  }
  async ensureSafeInput(locator) {
    const info = await locator.evaluate(inputIdentity);
    if (sensitiveInput(info)) fail('sensitiveInput');
  }
  async focusedInput() {
    const locator = this.page.locator(':focus');
    if (await locator.count()) {
      if (await locator.evaluate(el => /^(IFRAME|FRAME)$/.test(el.tagName))) fail('framesUnsupported');
      await this.ensureSafeInput(locator);
    }
  }
  async moveClick(locator, pacing) {
    await locator.scrollIntoViewIfNeeded();
    const rect = await locator.boundingBox();
    if (!rect) fail('elementNotVisible');
    const start = this.pointer, end = { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
    // Reject covered elements before issuing raw pointer events.
    await locator.click({ trial: true, timeout: 10000 });
    for (let i = 1; i <= pacing.steps; i++) {
      const t = i / pacing.steps, eased = t * t * (3 - 2 * t);
      this.pointer = { x: start.x + (end.x - start.x) * eased, y: start.y + (end.y - start.y) * eased };
      await this.page.mouse.move(this.pointer.x, this.pointer.y);
      this.event({ event: 'mouseMoved', ...this.pointer });
      if (pacing.moveSeconds) await delay(pacing.moveSeconds * 1000 / pacing.steps);
    }
    const stillOnTarget = await locator.evaluate((el, point) => {
      const hit = document.elementFromPoint(point.x, point.y);
      return hit === el || el.contains(hit);
    }, end);
    if (!stillOnTarget) fail('elementMovedOrCovered');
    await this.page.mouse.down(); this.event({ event: 'mouseDown', ...end });
    await this.page.mouse.up(); this.event({ event: 'mouseUp', ...end });
    return rect;
  }
  async waitTarget(target) {
    const until = Date.now() + 10000;
    while (true) {
      try { return await resolveTarget(this.page, target); }
      catch (e) {
        if (e.code !== 'elementNotFound' || Date.now() >= until) throw e;
        await delay(100);
      }
    }
  }
  async perform(action, pacing) {
    await this.guard({ allowNavigation: action?.action === 'goto' }); validatePacing(pacing);
    if (!action || typeof action.action !== 'string') fail('invalidAction');
    let rect, matched;
    switch (action.action) {
      case 'goto':
        if (!navigationAllowed(action.url, this.allowed, false)) fail('originRefused');
        this.calibrating = false;
        await this.page.goto(action.url, { waitUntil: 'domcontentloaded' }); break;
      case 'click': case 'fill': {
        const result = await this.waitTarget(action.target); matched = result.matched;
        if (action.action === 'fill') {
          if (!action.value || Object.keys(action.value).length !== 1 || typeof action.value.literal !== 'string' ||
              Buffer.byteLength(action.value.literal) > 16384) fail('unresolvedInput');
          // Bound visible typing so the command budget cannot be exceeded by an enormous value.
          if (action.value.literal.length * pacing.typeDelayMs > 60000) fail('typingTooLong');
          await this.ensureSafeInput(result.locator);
        }
        rect = await this.moveClick(result.locator, pacing);
        if (action.action === 'fill') {
          await this.focusedInput(); // A click may focus a different, sensitive field.
          await result.locator.press('ControlOrMeta+A');
          await result.locator.press('Backspace');
          for (const character of action.value.literal) {
            await this.ensureSafeInput(result.locator);
            await this.focusedInput();
            // Playwright types a newline as Enter, which can submit and clear a chat editor.
            // Insert line breaks as text instead, just like a multiline paste.
            if (character === '\n' || character === '\r') {
              await this.page.keyboard.insertText(character);
              if (pacing.typeDelayMs) await delay(pacing.typeDelayMs);
            } else {
              await result.locator.pressSequentially(character, { delay: pacing.typeDelayMs });
            }
          }
        }
        break;
      }
      case 'press':
        if (!text(action.key, 128) || !/^(?:(?:ControlOrMeta|Control|Meta|Alt|Shift)\+)*(?:Enter|Escape|Tab|Backspace|Delete|ArrowUp|ArrowDown|ArrowLeft|ArrowRight|Home|End|PageUp|PageDown|Space)$/.test(action.key)) fail('invalidKey');
        await this.focusedInput(); await this.page.keyboard.press(action.key); break;
      case 'scroll': {
        if (!action.to || !bounded(action.to.x, -10000000, 10000000) || !bounded(action.to.y, -10000000, 10000000)) fail('invalidScroll');
        const result = action.to.target == null ? null : await resolveTarget(this.page, action.to.target);
        if (result) matched = result.matched;
        const scroll = async (el, to) => {
          const scroller = to.target == null ? document.scrollingElement : el;
          if (!scroller) return false;
          scroller.scrollTo({ left: to.x, top: to.y, behavior: 'instant' });
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          return Math.abs(scroller.scrollLeft - to.x) <= 1 && Math.abs(scroller.scrollTop - to.y) <= 1;
        };
        const reached = await (result?.locator ?? this.page.locator(':root')).evaluate(scroll, action.to);
        if (!reached) fail('scrollPositionNotReached');
        break;
      }
      case 'wait':
        if (!bounded(action.seconds, 0, 120)) fail('invalidWait');
        await delay(action.seconds * 1000); break;
      case 'handover': fail('explicitUserControlRequired'); break;
      default: fail('unknownAction');
    }
    await this.guard();
    return { rect, matched, viewport: await this.metrics() };
  }
  async check(expectation, timeout) {
    if (!this.page || this.page.isClosed()) fail('notRunning');
    if (!expectation || (!expectation.url && !expectation.visible) || !bounded(timeout, 0, 120)) fail('invalidExpectation');
    if (expectation.url) {
      if (!text(expectation.url, 8192) || (expectation.url.startsWith('/') ? expectation.url.startsWith('//') : !this.allowed.has(origin(expectation.url)))) fail('invalidExpectation');
    }
    if (expectation.visible) validateCandidate(expectation.visible);
    const until = Date.now() + timeout * 1000;
    do {
      let satisfied = true;
      if (expectation.url) {
        const url = new URL(this.page.url());
        satisfied = expectation.url.startsWith('/') ? `${url.pathname}${url.search}${url.hash}` === expectation.url : url.href === new URL(expectation.url).href;
      }
      if (expectation.visible) {
        try { await resolveTarget(this.page, { candidates: [expectation.visible] }); }
        catch (e) { if (e.code !== 'elementNotFound') throw e; satisfied = false; }
      }
      if (satisfied) return { satisfied: true };
      if (Date.now() >= until) break;
      await delay(Math.min(100, until - Date.now()));
    } while (true);
    return { satisfied: false };
  }
  async calibration() {
    await this.guard({ allowBlank: true }); this.calibrating = true;
    try {
      await this.page.goto(CALIBRATION_URL, { waitUntil: 'load' });
      // Two animation frames plus a task boundary let the marker frame reach painting before Aura captures.
      await this.page.evaluate(() => new Promise(resolve => {
        requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(resolve, 0)));
      }));
    }
    catch (e) { this.calibrating = false; throw e; }
    const viewport = await this.metrics(), s = MARKER_SIZE, inset = MARKER_INSET;
    const positions = [[inset, inset], [viewport.width - inset - s, inset],
      [inset, viewport.height - inset - s], [viewport.width - inset - s, viewport.height - inset - s]];
    return { viewport, background: BACKGROUND, markers: positions.map(([x, y], i) => ({ rect: { x, y, width: s, height: s }, color: COLORS[i] })) };
  }
  async snapshot() {
    await this.guard();
    // Deliberately omit all names/text/attributes: these may echo a secret entered during login.
    const snapshot = await this.page.evaluate(() => Array.from(document.querySelectorAll('button,a,input,select,textarea,[role]'))
      .slice(0, 500).map(el => el.tagName.toLowerCase()).join('\n'));
    return { snapshot };
  }
  async command(c) {
    switch (c.cmd) {
      case 'launch': return this.launch(c);
      case 'perform': return this.perform(c.action, c.pacing);
      case 'check': return this.check(c.expectation, c.timeout);
      case 'setUserControl': return this.setUserControl(c.enabled);
      case 'navigateForHandover': return this.navigateForHandover(c.url);
      case 'viewportMetrics': await this.guard({ allowBlank: true }); return this.metrics();
      case 'showCalibrationPage': return this.calibration();
      case 'snapshot': return this.snapshot();
      case 'flushCapture': return this.flushCapture();
      case 'close': await this.close(); return {};
      default: fail('unknownCommand');
    }
  }
  async close() {
    const context = this.context; this.context = null; this.page = null;
    if (context) await context.close();

  }
}

function processTree() {
  try {
    return execFileSync('/bin/ps', ['-axo', 'pid=,ppid=,comm='], { encoding: 'utf8', timeout: 1000, maxBuffer: 4 * MAX_LINE })
      .trim().split('\n').map(line => { const m = line.trim().match(/^(\d+)\s+(\d+)\s+(.+)$/); return m ? { pid: +m[1], ppid: +m[2], name: m[3] } : null; }).filter(Boolean);
  } catch { return []; }
}
function killChildren() {
  const tree = processTree(), descendants = new Set([process.pid]);
  for (let n = 0; n < tree.length; n++) for (const p of tree) if (descendants.has(p.ppid)) descendants.add(p.pid);
  for (const pid of [...descendants].reverse()) if (pid !== process.pid) { try { process.kill(pid, 'SIGKILL'); } catch {} }
}

export function runStdio() {
  const write = value => process.stdout.write(`${JSON.stringify(value)}\n`);
  const host = new BrowserHost(write);
  let busy = false, stopping = false;
  const shutdown = () => {
    if (stopping) return; stopping = true;
    // A wedged Playwright close must not leave the dedicated Chrome profile/process alive.
    const timer = setTimeout(() => { killChildren(); process.exit(0); }, 1000);
    void host.close().catch(() => {}).finally(() => { clearTimeout(timer); killChildren(); process.exit(0); });
  };
  process.on('SIGTERM', shutdown); process.on('SIGINT', shutdown); process.on('disconnect', shutdown);
  process.on('exit', killChildren);
  const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
  // Bound an unterminated line too; readline alone would retain unbounded input.
  let pendingBytes = 0;
  process.stdin.on('data', chunk => {
    for (const byte of chunk) { if (byte === 10) pendingBytes = 0; else if (++pendingBytes > MAX_LINE) { shutdown(); return; } }
  });
  rl.on('close', shutdown);
  rl.on('line', line => {
    if (stopping) return;
    let c;
    try { if (Buffer.byteLength(line) > MAX_LINE) fail('invalidRequest'); c = JSON.parse(line); }
    catch { write({ id: null, ok: false, error: 'invalidRequest' }); return; }
    if (!Number.isSafeInteger(c?.id) || c.id < 1) { write({ id: null, ok: false, error: 'invalidRequest' }); return; }
    if (c.cmd === 'close' && busy) { shutdown(); return; }
    if (busy) { write({ id: c.id, ok: false, error: 'busy' }); return; }
    busy = true;
    const budget = c.cmd === 'perform' ? 135000 : c.cmd === 'check' && bounded(c.timeout, 0, 120) ? c.timeout * 1000 + 5000 : 35000;
    const timer = setTimeout(() => { write({ id: c.id, ok: false, error: 'timedOut' }); shutdown(); }, budget);
    void host.command(c).then(result => write({ id: c.id, ok: true, ...result }), error => {
      // Playwright errors include values, DOM snippets and URLs. Never send or log their messages.
      write({ id: c.id, ok: false, error: error instanceof HostError ? error.code : 'browserFailure' });
      if (c.cmd === 'launch') shutdown();
    }).finally(() => { clearTimeout(timer); busy = false; if (c.cmd === 'close') shutdown(); });
  });
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) runStdio();
