import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once, EventEmitter } from 'node:events';
import { BrowserHost, CALIBRATION_URL, navigationAllowed, origin, resolveTarget,
  inputIdentity, installDocumentGuard, sanitizeInteraction, sensitiveInput, validateCandidate, validateLaunch, validatePacing } from '../Sources/Aura/Resources/aura-browser-host.mjs';

const allowed = new Set(['https://example.com']);
const launch = () => ({ profileDir: '/tmp/aura-test-profile', startURL: 'https://example.com/start',
  allowedOrigins: ['https://example.com'], window: { width: 1440, height: 900 } });

test('scroll capture sanitizes ranked targets without turning invalid targets into root scrolls', () => {
  const target = { candidates: [{ testId: 'panel' }, { role: 'region', name: 'Results' }, { css: '#panel' }] };
  assert.deepEqual(sanitizeInteraction({ kind: 'scroll', x: 15, y: 200, target }), { kind: 'scroll', x: 15, y: 200, target });
  assert.deepEqual(sanitizeInteraction({ kind: 'scroll', x: 0, y: 20 }), { kind: 'scroll', x: 0, y: 20 });
  assert.equal(sanitizeInteraction({ kind: 'scroll', x: 0, y: 20, target: { candidates: [{ css: 'iframe' }] } }), null);
  assert.equal(sanitizeInteraction({ kind: 'scroll', x: Infinity, y: 20, target }), null);
});

test('HTTP(S) URLs, canonical origins, credentials and launch bounds', () => {
  assert.equal(origin('https://EXAMPLE.com:443/path'), 'https://example.com');
  for (const url of ['file:///tmp/a', 'data:text/html,hello', 'javascript:alert(1)', 'https://user:secret@example.com']) {
    assert.throws(() => origin(url));
  }
  assert.deepEqual(validateLaunch(launch()), allowed);
  for (const bad of [ { ...launch(), startURL: 'https://evil.com' },
    { ...launch(), allowedOrigins: ['https://example.com/path'] },
    { ...launch(), window: { width: 1000000, height: 900 } } ]) assert.throws(() => validateLaunch(bad));
});

test('handover lifts origins only for HTTP(S); data exception is exact and opt-in', () => {
  assert.equal(navigationAllowed('https://evil.com', allowed, false), false);
  assert.equal(navigationAllowed('https://login.example.org', allowed, true), true);
  assert.equal(navigationAllowed('file:///etc/passwd', allowed, true), false);
  assert.equal(navigationAllowed(CALIBRATION_URL, allowed, false), false);
  assert.equal(navigationAllowed(CALIBRATION_URL, allowed, false, CALIBRATION_URL), true);
  assert.equal(navigationAllowed('data:text/html,other', allowed, false, CALIBRATION_URL), false);
});

test('credential entry is denied across input types, autocomplete and accessible identity', () => {
  for (const field of [{ type: 'password' }, { type: 'email' }, { autocomplete: 'section-login username' },
    { autocomplete: 'one-time-code' }, { name: 'api_key' }, { label: 'Verification code' },
    { placeholder: 'Email address' }, { autocomplete: 'cc-number' }, { id: 'passwordConfirmation' }]) {
    assert.equal(sensitiveInput(field), true, JSON.stringify(field));
  }
  assert.equal(sensitiveInput({ type: 'text', name: 'website', label: 'Website' }), false);
});

test('invalid candidates and iframe locators fail closed', () => {
  for (const c of [{}, { role: 'button' }, { text: 'A', css: 'button' }, { css: 'iframe >> button' },
    { css: 'button', frame: '#login' }, { testId: '' }]) assert.throws(() => validateCandidate(c));
  assert.equal(validateCandidate({ role: 'button', name: 'Create' }), 'role');
  assert.throws(() => validatePacing({ moveSeconds: Infinity, steps: 24, typeDelayMs: 45 }));
});

function fakePage(counts, frame = false) {
  const seen = [];
  const locator = name => {
    seen.push(name);
    return { filter: () => ({ count: async () => counts[name] ?? 0, evaluate: async () => frame }) };
  };
  return { seen, locator, getByRole: (role, opts) => locator(`${role}:${opts.name}`), getByText: text => locator(text) };
}

test('ranked candidates fall back only on zero visible matches', async () => {
  const page = fakePage({ 'button:Create': 1 });
  const result = await resolveTarget(page, { candidates: [{ text: 'Missing' }, { role: 'button', name: 'Create' }] });
  assert.equal(result.matched, 'role');
  assert.deepEqual(page.seen, ['Missing', 'button:Create']);
});

test('ambiguity fails immediately despite hintRect and unique fallback', async () => {
  const page = fakePage({ Duplicate: 2, Unique: 1 });
  await assert.rejects(resolveTarget(page, { candidates: [{ text: 'Duplicate' }, { text: 'Unique' }],
    hintRect: { x: 0, y: 0, width: 10, height: 10 } }), { code: 'ambiguousLocator' });
  assert.deepEqual(page.seen, ['Duplicate']);
  await assert.rejects(resolveTarget(fakePage({ Frame: 1 }, true), { candidates: [{ text: 'Frame' }] }), { code: 'framesUnsupported' });
});

test('premature Resume preserves user control, popups and host and can be retried', async () => {
  const events = [], host = new BrowserHost(e => events.push(e));
  let currentURL = 'https://login.example.org', popupClosed = false;
  const popup = { close: async () => { popupClosed = true; } };
  host.context = { pages: () => [host.page, popup] };
  host.page = { isClosed: () => false, url: () => currentURL };
  host.allowed = allowed;
  await host.setUserControl(true);
  host.event({ event: 'navigated', url: 'secret' });
  assert.deepEqual(events, []);
  await assert.rejects(host.perform({ action: 'wait', seconds: 0 }, { moveSeconds: 0, steps: 1, typeDelayMs: 0 }), { code: 'userControl' });
  await assert.rejects(host.snapshot(), { code: 'userControl' });
  host.calibrating = true; // Calibration's data-URL exception must not bypass resume's origin guard.
  await assert.rejects(host.setUserControl(false), { code: 'notReady' });
  assert.equal(host.userControl, true); assert.equal(popupClosed, false);
  currentURL = 'https://example.com';
  await host.setUserControl(false);
  assert.equal(host.userControl, false); assert.equal(popupClosed, true);
});

test('handover navigation is narrowly granted, validates the initial URL, and retains user control', async () => {
  const events = [], visits = [], host = new BrowserHost(event => events.push(event));
  host.allowed = allowed; host.calibrating = true;
  host.page = { isClosed: () => false, goto: async (url, options) => {
    visits.push(url); assert.equal(options.waitUntil, 'domcontentloaded');
    host.event({ event: 'navigated', url: 'https://idp.example/redirect' });
  } };
  await assert.rejects(host.command({ cmd: 'navigateForHandover', url: 'https://example.com/start' }), { code: 'userControlRequired' });
  host.userControl = true;
  for (const url of ['file:///tmp/fixture', 'data:text/html,fixture', 'https://user:credential@example.com']) {
    await assert.rejects(host.navigateForHandover(url), { code: 'invalidURL' });
  }
  await assert.rejects(host.navigateForHandover('https://idp.example/start'), { code: 'originRefused' });
  assert.deepEqual(visits, []); assert.equal(host.calibrating, true);
  await host.command({ cmd: 'navigateForHandover', url: 'https://example.com/start' });
  assert.deepEqual(visits, ['https://example.com/start']);
  assert.equal(host.calibrating, false); assert.equal(host.userControl, true); assert.deepEqual(events, []);
  for (const action of ['goto', 'click', 'fill', 'press', 'scroll', 'wait']) {
    await assert.rejects(host.perform({ action }, { moveSeconds: 0, steps: 1, typeDelayMs: 0 }), { code: 'userControl' });
  }
});

test('handover is not an action; goto cannot use calibration exception', async () => {
  const host = new BrowserHost(); host.allowed = allowed;
  host.page = { isClosed: () => false, url: () => 'https://example.com' };
  const pacing = { moveSeconds: 0, steps: 1, typeDelayMs: 0 };
  await assert.rejects(host.perform({ action: 'handover', reason: 'login' }, pacing), { code: 'explicitUserControlRequired' });
  await assert.rejects(host.perform({ action: 'goto', url: CALIBRATION_URL }, pacing), { code: 'originRefused' });
});

test('sensitive fill is rejected before any click or value entry', async () => {
  const host = new BrowserHost(); host.allowed = allowed;
  const field = { count: async () => 1, evaluate: async fn => fn.toString().includes('tagName') ? false : { type: 'password' } };
  host.page = { isClosed: () => false, url: () => 'https://example.com', getByText: () => ({ filter: () => field }) };
  host.moveClick = async () => assert.fail('must not click');
  await assert.rejects(host.perform({ action: 'fill', target: { candidates: [{ text: 'Secret' }] }, value: { literal: 'do-not-log-me' } },
    { moveSeconds: 0, steps: 1, typeDelayMs: 0 }), { code: 'sensitiveInput' });
});

test('calibration exposes CSS metrics and ordered 32px inset markers matching its HTML', async () => {
  const host = new BrowserHost(); host.allowed = allowed;
  let visited, painted = false;
  host.page = { isClosed: () => false, url: () => 'about:blank', goto: async url => { visited = url; },
    evaluate: async fn => {
      const previous = globalThis.requestAnimationFrame;
      let frames = 0;
      globalThis.requestAnimationFrame = callback => setTimeout(() => { frames++; callback(); }, 0);
      try { await fn(); painted = frames >= 2; } finally { globalThis.requestAnimationFrame = previous; }
    } };
  host.metrics = async () => ({ width: 800, height: 600, devicePixelRatio: 2 });
  const result = await host.calibration();
  assert.equal(visited, CALIBRATION_URL); assert.equal(painted, true);
  assert.equal(result.viewport.devicePixelRatio, 2);
  assert.deepEqual(result.markers.map(m => m.rect), [
    { x: 32, y: 32, width: 16, height: 16 }, { x: 752, y: 32, width: 16, height: 16 },
    { x: 32, y: 552, width: 16, height: 16 }, { x: 752, y: 552, width: 16, height: 16 },
  ]);
  const html = decodeURIComponent(CALIBRATION_URL.split(',')[1]);
  assert.ok(html.includes('width:16px;height:16px'));
  for (const [i, marker] of result.markers.entries()) {
    assert.ok(html.includes(`${i % 2 ? 'right' : 'left'}:32px;${i < 2 ? 'top' : 'bottom'}:32px;background:rgb(${marker.color})`));
  }
  assert.equal(new Set(result.markers.map(m => m.color.join(','))).size, 4);
});

test('successful actions report geometry, pointer events and paced non-sensitive typing', async () => {
  const events = [], operations = [], host = new BrowserHost(e => events.push(e));
  host.allowed = allowed;
  const field = {
    count: async () => 1,
    evaluate: async (fn, arg) => {
      if (fn.toString().includes('scrollTo')) { operations.push(arg); return true; }
      return fn.toString().includes('tagName') ? false :
        fn.toString().includes('getAttribute') ? { type: 'text', label: 'Website' } : true;
    },
    scrollIntoViewIfNeeded: async () => {},
    boundingBox: async () => ({ x: 20, y: 40, width: 100, height: 30 }),
    click: async () => {}, press: async key => operations.push(key),
    pressSequentially: async character => operations.push(character),
  };
  host.page = {
    isClosed: () => false, url: () => 'https://example.com',
    getByText: () => ({ filter: () => field }), locator: () => field,
    mouse: { move: async () => {}, down: async () => {}, up: async () => {} },
    keyboard: { press: async key => operations.push(key) },
    goto: async url => operations.push(url), evaluate: async (_, arg) => operations.push(arg),
  };
  host.metrics = async () => ({ width: 800, height: 600, devicePixelRatio: 2 });
  const pacing = { moveSeconds: 0, steps: 3, typeDelayMs: 0 };
  const target = { candidates: [{ text: 'Website' }] };
  const outcome = await host.perform({ action: 'click', target }, pacing);
  assert.equal(outcome.matched, 'text'); assert.equal(outcome.rect.width, 100);
  assert.deepEqual(events.map(e => e.event), ['mouseMoved', 'mouseMoved', 'mouseMoved', 'mouseDown', 'mouseUp']);
  assert.deepEqual(events.at(-1), { event: 'mouseUp', x: 70, y: 55 });
  await host.perform({ action: 'fill', target, value: { literal: 'abc' } }, pacing);
  assert.deepEqual(operations, ['ControlOrMeta+A', 'Backspace', 'a', 'b', 'c']);
  await host.perform({ action: 'press', key: 'Enter' }, pacing);
  await host.perform({ action: 'scroll', to: { x: 0, y: 600 } }, pacing);
  await host.perform({ action: 'goto', url: 'https://example.com/next' }, pacing);
  await host.perform({ action: 'wait', seconds: 0 }, pacing);
  assert.deepEqual(operations.slice(-3), ['Enter', { x: 0, y: 600 }, 'https://example.com/next']);
  await assert.rejects(host.perform({ action: 'press', key: 'ControlOrMeta+V' }, pacing), { code: 'invalidKey' });
});

test('check combines URL and visible expectations and never accepts ambiguity', async () => {
  const host = new BrowserHost(); host.allowed = allowed;
  host.page = { ...fakePage({ Ready: 1, Duplicate: 2 }), isClosed: () => false, url: () => 'https://example.com/ready' };
  assert.deepEqual(await host.check({ url: '/ready', visible: { text: 'Ready' } }, 0), { satisfied: true });
  assert.deepEqual(await host.check({ url: '/other' }, 0), { satisfied: false });
  assert.deepEqual(await host.check({ visible: { text: 'Missing' } }, 0), { satisfied: false });
  await assert.rejects(host.check({ visible: { text: 'Duplicate' } }, 0), { code: 'ambiguousLocator' });
});

test('accessible names prioritize references while security scans overridden and deduplicated labels', () => {
  const label = { cloneNode: () => ({ textContent: 'Message', querySelectorAll: () => [] }) };
  const attributes = {};
  const element = { id: 'field', labels: [label], closest: () => label,
    getAttribute: name => attributes[name] ?? null,
    ownerDocument: { getElementById: () => ({ cloneNode: () => ({
      textContent: 'Primary name', querySelectorAll: () => [] }) }) } };
  assert.equal(inputIdentity(element).accessibleName, 'Message');
  assert.equal(inputIdentity(element).label, 'Message', 'the wrapping associated label appears only once');
  attributes['aria-label'] = 'Secondary name';
  assert.equal(inputIdentity(element).accessibleName, 'Secondary name');
  attributes['aria-labelledby'] = 'primary';
  assert.equal(inputIdentity(element).accessibleName, 'Primary name');
  attributes['aria-label'] = 'Email address';
  assert.equal(inputIdentity(element).accessibleName, 'Primary name');
  assert.equal(sensitiveInput(inputIdentity(element)), true, 'overridden labels still enforce privacy');
});

test('aria-labelledby references participate in target and focused-input credential checks', async () => {
  const attributes = { 'aria-labelledby': 'description identity' };
  const element = { id: 'f1', labels: [], getAttribute: name => attributes[name] ?? null,
    ownerDocument: { getElementById: id => ({ cloneNode: () => ({
          textContent: id === 'identity' ? 'Email address' : 'Account', querySelectorAll: () => [] }) }) } };
  assert.equal(sensitiveInput(inputIdentity(element)), true);
  const locator = { count: async () => 1, evaluate: async fn => fn(element) };
  const host = new BrowserHost(); host.page = { locator: () => locator };
  await assert.rejects(host.ensureSafeInput(locator), { code: 'sensitiveInput' });
  await assert.rejects(host.focusedInput(), { code: 'sensitiveInput' });
});

test('CDP guard pauses each redirect hop before dispatch and permits HTTP(S) subframes', async () => {
  const session = new EventEmitter(), commands = [], refused = [];
  session.send = async (method, params) => {
    commands.push({ method, params });
    if (method === 'Page.getFrameTree') return { frameTree: { frame: { id: 'main' } } };
  };
  await installDocumentGuard(session, {
    allowed: (url, main) => navigationAllowed(url, allowed, !main),
    refused: url => refused.push(url), failed: error => assert.fail(error),
  });
  session.emit('Page.frameAttached', { frameId: 'subframe', parentFrameId: 'main' });
  for (const [id, url, frameId] of [['first', 'https://example.com/redirect1', 'main'],
    ['second', 'https://example.com/redirect2', 'main'], ['third', 'https://evil.com/blocked', 'main'],
    ['frame', 'https://external.com/frame', 'subframe'], ['unknown', 'https://evil.com/unknown', 'unknown']]) {
    session.emit('Fetch.requestPaused', { requestId: id, request: { url }, frameId });
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.equal(commands.find(c => c.method === 'Fetch.enable').params.patterns[0].requestStage, 'Request');
  assert.deepEqual(commands.filter(c => c.method.startsWith('Fetch.') && c.method !== 'Fetch.enable').map(c => [c.method, c.params.requestId]),
    [['Fetch.continueRequest', 'first'], ['Fetch.continueRequest', 'second'], ['Fetch.failRequest', 'third'], ['Fetch.continueRequest', 'frame'], ['Fetch.failRequest', 'unknown']]);
  assert.deepEqual(refused, ['https://evil.com/blocked', 'https://evil.com/unknown']);
});

test('navigation event URL redaction', () => {
  const host = new BrowserHost();
  assert.equal(host.safeURL('https://example.com/callback?code=secret#token'), 'https://example.com/callback');
  assert.equal(host.safeURL('data:text/html,secret'), 'about:blank');
});

test('stdio errors are machine codes, never input echoes; EOF cleans up', { timeout: 5000 }, async () => {
  const child = spawn(process.execPath, [new URL('../Sources/Aura/Resources/aura-browser-host.mjs', import.meta.url).pathname], { stdio: ['pipe', 'pipe', 'pipe'] });
  let stdout = '', stderr = '';
  child.stdout.on('data', c => { stdout += c; }); child.stderr.on('data', c => { stderr += c; });
  const exited = once(child, 'exit');
  child.stdin.write('not-json-secret\n');
  child.stdin.write('{"id":1,"cmd":"unknown-secret"}\n');
  await new Promise(resolve => setTimeout(resolve, 100));
  child.stdin.end();
  await exited;
  assert.equal(stderr, ''); assert.ok(!stdout.includes('secret'));
  assert.match(stdout, /invalidRequest/); assert.match(stdout, /unknownCommand/);
});

test('capture accepts only meaningful non-text keys and retains their modifiers', () => {
  for (const key of ['Enter', 'Enter', 'Tab', 'Shift+Tab', 'Shift+Enter', 'Control+Enter', 'Meta+Enter', 'Alt+Escape', 'Control+Alt+Shift+Enter']) {
    assert.deepEqual(sanitizeInteraction({ kind: 'press', key }), { kind: 'press', key });
  }
  for (const key of ['a', 'Meta+a', 'Control+v', 'Shift', 'Untrusted+Enter', 'Enter+a', 'ArrowLeft']) {
    assert.equal(sanitizeInteraction({ kind: 'press', key }), null);
  }
  const target = { candidates: [{ role: 'textbox', name: 'Message' }] };
  const value = '  👋 café 世界\nline two\n  ';
  assert.deepEqual(sanitizeInteraction({ kind: 'input', target, value }), { kind: 'input', target, value });
});

test('a demonstration only reports well-formed, non-credential interactions', () => {
  const rect = { x: 10, y: 20, width: 100, height: 30 };
  const button = { candidates: [{ role: 'button', name: 'Create agent' }, { css: '#create' }], hintRect: rect };
  assert.deepEqual(sanitizeInteraction({ kind: 'click', target: button, rect }),
    { kind: 'click', target: button, rect });
  assert.deepEqual(sanitizeInteraction({ kind: 'input', target: { candidates: [{ role: 'textbox', name: 'Website' }] }, value: 'https://example.com' }),
    { kind: 'input', target: { candidates: [{ role: 'textbox', name: 'Website' }] }, value: 'https://example.com' });
  assert.deepEqual(sanitizeInteraction({ kind: 'press', key: 'Enter' }), { kind: 'press', key: 'Enter' });
  assert.deepEqual(sanitizeInteraction({ kind: 'scroll', x: 0, y: 400 }), { kind: 'scroll', x: 0, y: 400 });
  assert.deepEqual(sanitizeInteraction({ kind: 'sensitiveInput', secret: 'x' }), { kind: 'sensitiveInput' });

  // A second fence behind the page's own: a field that names itself like a credential is never
  // reported, even if the page script said it was fine.
  for (const name of ['Password', 'Email address', 'Verification code', 'API key']) {
    assert.deepEqual(sanitizeInteraction({ kind: 'input', target: { candidates: [{ role: 'textbox', name }] }, value: 'private' }),
      { kind: 'sensitiveInput' }, name);
  }
  // Malformed, oversized or unknown reports are dropped, never repaired.
  for (const bad of [null, 'click', {}, { kind: 'drag' }, { kind: 'click', target: { candidates: [] }, rect },
    { kind: 'click', target: button, rect: { x: 1, y: 1, width: 0, height: 5 } },
    { kind: 'click', target: { candidates: [{ css: 'iframe > button' }] }, rect },
    { kind: 'input', target: button, value: 'x'.repeat(5000) },
    { kind: 'input', target: button, value: 42 },
    { kind: 'press', key: 'a' }, { kind: 'press', key: 'Delete' },
    { kind: 'scroll', x: Infinity, y: 0 }]) assert.equal(sanitizeInteraction(bad), null, JSON.stringify(bad));
});
