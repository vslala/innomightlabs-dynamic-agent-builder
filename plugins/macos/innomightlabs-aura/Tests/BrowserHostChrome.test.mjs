import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once, EventEmitter } from 'node:events';
import { mkdtemp, rm, access, mkdir, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createRequire } from 'node:module';
import { BrowserHost } from '../Sources/Aura/Resources/aura-browser-host.mjs';

// Opt-in: use the consent-installed engine, or a temporary pinned install. Never downloads a browser.
// AURA_BROWSER_ENGINE_DIR=/path/containing/node_modules node --test Tests/BrowserHostChrome.test.mjs
const engine = process.env.AURA_BROWSER_ENGINE_DIR;
const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
let available = false;
if (engine) {
  try {
    await access(chrome);
    const require = createRequire(join(engine, 'package.json'));
    available = !!require('playwright-core').chromium;
  } catch { /* Explicit skip when Chrome or the consent-installed engine is absent. */ }
}
const listen = async server => { server.listen(0, '127.0.0.1'); await once(server, 'listening'); return `http://127.0.0.1:${server.address().port}`; };
const pacing = { moveSeconds: 0, steps: 1, typeDelayMs: 0 };
async function waitForErrorPage(page) {
  // PW's navigation waiter rejects on the blocked request before Chromium commits its error page.
  for (let i = 0; i < 250; i++) {
    if (page.url() === 'chrome-error://chromewebdata/') return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  assert.fail('Chromium did not commit the blocked-navigation error document');
}

test('native wheel captures root and two overflow targets, flushes before click and immediate Finish, and replays exactly',
  { skip: !available, timeout: 30000 }, async t => {
    const previousCwd = process.cwd(), directory = await mkdtemp(join(tmpdir(), 'aura-scroll-'));
    const events = [];
    const site = createServer((request, response) => {
      response.setHeader('Content-Type', 'text/html');
      response.end(`<style>body{margin:0;min-height:4000px}.panel{width:240px;height:180px;overflow:auto;display:inline-block;overscroll-behavior:contain}.content{width:900px;height:1600px}</style>
        <div class="panel" data-testid="first" role="region" aria-label="First"><div class="content">First content</div></div>
        <div class="panel" data-testid="second" role="region" aria-label="Second"><div class="content">Second content</div></div>
        <button style="position:fixed;right:20px;top:20px">Continue</button>`);
    });
    const base = await listen(site);
    const host = new BrowserHost(event => events.push(event));
    t.after(async () => {
      await host.close().catch(() => {});
      site.closeAllConnections(); await new Promise(resolve => site.close(resolve));
      process.chdir(previousCwd); await rm(directory, { recursive: true, force: true });
    });
    process.chdir(engine);
    await host.launch({ profileDir: join(directory, 'profile'), startURL: base, allowedOrigins: [base],
      window: { width: 1280, height: 800 }, capture: true });
    await host.navigateForHandover(base);
    const wheel = async (x, y, dx, dy) => {
      await host.page.mouse.move(x, y); await host.page.mouse.wheel(dx, dy);
      await host.page.waitForTimeout(60);
    };
    await wheel(100, 80, 35, 200);
    await wheel(350, 80, 20, 150);
    await host.page.getByRole('button', { name: 'Continue' }).click();
    await host.page.waitForTimeout(30);
    const beforeClick = events.filter(e => e.event === 'captured').map(e => e.interaction);
    assert.deepEqual(beforeClick.map(i => i.kind), ['scroll', 'scroll', 'click']);
    assert.deepEqual(beforeClick.slice(0, 2).map(i => i.target.candidates[0].testId), ['first', 'second']);
    assert.ok(beforeClick[0].x > 0 && beforeClick[0].y > 0);
    await wheel(100, 80, 15, 100);
    await wheel(350, 80, 10, 80);
    await wheel(800, 500, 0, 240);
    const response = await host.command({ cmd: 'flushCapture' });
    assert.equal(response.interactions.length, 3, 'Finish before 400 ms retains both containers and root');
    assert.deepEqual(response.interactions.slice(0, 2).map(i => i.target.candidates[0].testId), ['first', 'second']);
    const root = response.interactions[2];
    assert.equal(root.kind, 'scroll'); assert.equal(root.target, undefined); assert.ok(root.y > 0);
    await host.page.waitForTimeout(450);
    assert.equal(events.filter(e => e.event === 'captured').length, 3, 'flush response is not emitted again');
    assert.deepEqual(await host.flushCapture(), { interactions: [] });
    await host.close();
    host.userControl = false;
    await host.launch({ profileDir: join(directory, 'replay'), startURL: base, allowedOrigins: [base],
      window: { width: 1280, height: 800 }, capture: false });
    await host.perform({ action: 'goto', url: base }, pacing);
    for (const to of [...beforeClick.slice(0, 2), ...response.interactions]) await host.perform({ action: 'scroll', to }, pacing);
    const actual = await host.page.evaluate(() => ({ root: document.scrollingElement.scrollTop,
      panels: [...document.querySelectorAll('.panel')].map(el => ({ x: el.scrollLeft, y: el.scrollTop })) }));
    assert.equal(actual.root, root.y);
    assert.deepEqual(actual.panels, response.interactions.slice(0, 2).map(i => ({ x: i.x, y: i.y })));
    await assert.rejects(host.perform({ action: 'scroll', to: { x: 0, y: 200, target: { candidates: [{ css: '.missing' }] } } }, pacing), { code: 'elementNotFound' });
    await assert.rejects(host.perform({ action: 'scroll', to: { x: 0, y: 200, target: { candidates: [{ css: '.panel' }] } } }, pacing), { code: 'ambiguousLocator' });
    await assert.rejects(host.perform({ action: 'scroll', to: { x: 0, y: 999999 } }, pacing), { code: 'scrollPositionNotReached' });
  });

test('native chat input captures before synchronous submit, coalesces edits, protects secrets and replays exact messages',
  { skip: !available, timeout: 60000 }, async t => {
    const previousCwd = process.cwd(), directory = await mkdtemp(join(tmpdir(), 'aura-chat-'));
    const events = [];
    const site = createServer((request, response) => {
      response.setHeader('Content-Type', 'text/html; charset=utf-8');
      response.end(`<label>Message<textarea id="message" rows="8" cols="80"></textarea></label><button id="send">Send</button>
        <div id="editor" contenteditable="true" role="textbox" aria-placeholder="Draft"></div>
        <input id="plain" size="80" placeholder="Notes"><button id="other">Other</button>
        <div id="panel" style="position:fixed;right:0;top:0;width:200px;height:180px;overflow:auto">
          <div style="height:1500px">Scrollable panel</div>
        </div>
        <input id="password" type="password"><input id="email" type="email">
        <div id="otp" contenteditable="true" aria-label="Verification code"></div>
        <label>API key<div id="credential" contenteditable="plaintext-only"></div></label>
        <div id="secret" contenteditable="true" aria-placeholder="Password"></div>
        <script>
          window.messages = [];
          const message = document.querySelector('#message'), editor = document.querySelector('#editor');
          const submit = () => { if (message.value) messages.push(message.value); message.value = ''; };
          message.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); submit(); }
          });
          document.querySelector('#send').addEventListener('click', submit);
          editor.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
              e.preventDefault(); messages.push(editor.innerText); editor.textContent = '';
            }
          });
        </script>`);
    });
    const base = await listen(site);
    const host = new BrowserHost(event => events.push(event));
    t.after(async () => {
      await host.close().catch(() => {});
      site.closeAllConnections(); await new Promise(resolve => site.close(resolve));
      process.chdir(previousCwd); await rm(directory, { recursive: true, force: true });
    });
    process.chdir(engine);
    const launch = profile => ({ profileDir: join(directory, profile), startURL: base, allowedOrigins: [base],
      window: { width: 1280, height: 800 }, capture: profile === 'capture' });
    await host.launch(launch('capture'));
    await host.navigateForHandover(base);
    const captured = () => events.filter(e => e.event === 'captured').map(e => e.interaction);
    await host.page.click('#message');
    await host.page.keyboard.type('Hello ');
    await host.page.keyboard.insertText('👋 世界'); // Native insertText follows the paste/input path.
    await host.page.keyboard.press('Enter');
    await host.page.keyboard.type('line one');
    await host.page.keyboard.press('Shift+Enter');
    await host.page.keyboard.insertText('  café 🌈  ');
    await host.page.keyboard.press('Enter');
    await host.page.keyboard.insertText('Click sends\nexact pasted text');
    await host.page.click('#send');
    await host.page.click('#editor');
    await host.page.keyboard.insertText('Editor 🧑🏽‍💻');
    await host.page.keyboard.press('Shift+Enter');
    await host.page.keyboard.insertText('next line');
    const editorText = await host.page.locator('#editor').innerText();
    await host.page.keyboard.press('Enter');
    await host.page.waitForTimeout(50);
    const actions = captured();
    assert.deepEqual(actions.map(i => i.kind), ['input', 'press', 'input', 'press', 'input', 'click', 'input', 'press']);
    const expected = ['Hello 👋 世界', 'line one\n  café 🌈  ', 'Click sends\nexact pasted text', editorText];
    assert.deepEqual(actions.filter(i => i.kind === 'input').map(i => i.value), expected);
    assert.deepEqual(actions[0].target.candidates.find(c => c.role), { role: 'textbox', name: 'Message' });
    assert.equal(await host.page.getByRole('textbox', { name: 'Message', exact: true }).count(), 1);
    assert.deepEqual(await host.page.evaluate(() => messages), expected);
    const editorTarget = actions.at(-2).target;
    assert.equal(JSON.stringify(editorTarget).includes('Editor 🧑🏽‍💻'), false, 'typed contents never become locator names');
    assert.equal(editorTarget.candidates.some(c => c.text), false);

    await host.page.click('#message');
    const keyStart = captured().length;
    for (const key of ['Enter', 'Enter', 'Tab', 'Shift+Tab', 'Control+Enter', 'Meta+Enter', 'Alt+Escape']) {
      await host.page.keyboard.press(key);
    }
    await host.page.waitForTimeout(50);
    assert.deepEqual(captured().slice(keyStart).filter(i => i.kind === 'press').map(i => i.key),
      ['Enter', 'Enter', 'Tab', 'Shift+Tab', 'Control+Enter', 'Meta+Enter', 'Alt+Escape']);

    await host.page.click('#message');
    const imeStart = captured().length;
    const cdp = await host.context.newCDPSession(host.page);
    await cdp.send('Input.imeSetComposition', { text: '仮', selectionStart: 1, selectionEnd: 1 });
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 229 });
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 229 });
    await cdp.send('Input.insertText', { text: '確定' });
    await host.page.keyboard.press('Tab');
    await host.page.waitForTimeout(50);
    assert.deepEqual(captured().slice(imeStart).filter(i => i.kind !== 'scroll').map(i => i.kind), ['input', 'press']);
    assert.equal(captured().slice(imeStart).find(i => i.kind === 'input').value, '確定');
    assert.equal(captured().at(-1).key, 'Tab', 'IME confirmation Enter is not a submit');
    await cdp.detach();

    await host.page.click('#plain');
    await host.page.waitForTimeout(30);
    const mixedStart = captured().length;
    await host.page.keyboard.type('before wheel');
    await host.page.mouse.move(1150, 70);
    await host.page.mouse.wheel(0, 200);
    await host.page.waitForTimeout(60);
    await host.page.keyboard.insertText(' after wheel');
    await host.page.keyboard.press('Escape');
    await host.page.waitForTimeout(30);
    assert.deepEqual(captured().slice(mixedStart).map(i => i.kind), ['input', 'scroll', 'input', 'press'],
      'pending text and scroll retain their cross-type order');
    await host.page.keyboard.insertText(' blur');
    await host.page.locator('#other').focus();
    await host.page.waitForTimeout(30);
    assert.equal(captured().filter(i => i.kind === 'input').at(-1).value, 'before wheel after wheel blur', 'blur flushes the still-focused typing run');

    for (const selector of ['#password', '#email', '#otp', '#credential', '#secret']) {
      await host.page.click(selector);
      await host.page.keyboard.insertText('never-send-this-secret');
      await host.page.keyboard.press('Meta+Enter');
    }
    await host.page.click('#plain');
    await host.page.keyboard.press('ControlOrMeta+A');
    await host.page.keyboard.press('Backspace');
    await host.page.keyboard.type('still focused ');
    await host.page.keyboard.insertText('Unicode 🐝');
    const pending = await host.flushCapture();
    assert.deepEqual(pending.interactions.map(i => i.kind), ['input']);
    assert.equal(pending.interactions[0].value, 'still focused Unicode 🐝');
    assert.equal(JSON.stringify([...events, pending]).includes('never-send-this-secret'), false);
    assert.ok(captured().some(i => i.kind === 'sensitiveInput'));
    const count = captured().length;
    await host.page.waitForTimeout(450);
    assert.equal(captured().length, count, 'Finish drains queued inputs without duplicate delivery');
    assert.deepEqual(await host.flushCapture(), { interactions: [] });

    await host.close(); host.userControl = false;
    await host.launch(launch('replay'));
    await host.perform({ action: 'goto', url: base }, pacing);
    for (const interaction of actions) {
      const action = interaction.kind === 'input'
        ? { action: 'fill', target: interaction.target, value: { literal: interaction.value } }
        : interaction.kind === 'press' ? { action: 'press', key: interaction.key }
        : { action: 'click', target: interaction.target };
      await host.perform(action, pacing);
    }
    assert.deepEqual(await host.page.evaluate(() => messages), expected, 'replay submits every complete message exactly once');
  });

test('native capture names honor label priority without using live editable label references',
  { skip: !available, timeout: 30000 }, async t => {
    const previousCwd = process.cwd(), directory = await mkdtemp(join(tmpdir(), 'aura-labels-'));
    const events = [];
    const site = createServer((request, response) => {
      response.setHeader('Content-Type', 'text/html');
      response.end(`<span id="primary">Primary name</span><label for="priority">Associated name</label>
        <input id="priority" aria-labelledby="primary" aria-label="Secondary name">
        <div id="donor" contenteditable="true">never-reference-live-secret</div>
        <input id="reference" aria-labelledby="donor" aria-label="Safe fallback">
        <div id="self" contenteditable="true" role="textbox" aria-labelledby="self" aria-label="Self editor"></div>
        <span id="mixed">Stable label <span contenteditable="true">never-reference-live-secret</span></span>
        <input id="nested" aria-labelledby="mixed">
        <textarea id="textarea-label">never-reference-live-secret</textarea>
        <input id="native-reference" aria-labelledby="textarea-label" aria-label="Native fallback">
        <span id="guarded-name">Guarded field</span>
        <input id="guarded" aria-labelledby="guarded-name" aria-label="Email address">`);
    });
    const base = await listen(site);
    const host = new BrowserHost(event => events.push(event));
    t.after(async () => {
      await host.close().catch(() => {});
      site.closeAllConnections(); await new Promise(resolve => site.close(resolve));
      process.chdir(previousCwd); await rm(directory, { recursive: true, force: true });
    });
    process.chdir(engine);
    await host.launch({ profileDir: join(directory, 'profile'), startURL: base, allowedOrigins: [base],
      window: { width: 1280, height: 800 }, capture: true });
    await host.navigateForHandover(base);
    for (const selector of ['#priority', '#reference', '#self', '#nested', '#native-reference']) {
      await host.page.locator(selector).focus();
      await host.page.keyboard.insertText('ordinary text');
      await host.page.keyboard.press('Tab');
    }
    await host.page.waitForTimeout(50);
    const inputs = events.filter(e => e.event === 'captured' && e.interaction.kind === 'input').map(e => e.interaction);
    assert.equal(inputs.length, 5);
    assert.deepEqual(inputs.map(i => i.target.candidates.find(c => c.role)?.name),
      ['Primary name', 'Safe fallback', 'Self editor', 'Stable label', 'Native fallback']);
    assert.equal(await host.page.getByRole('textbox', { name: 'Primary name', exact: true }).count(), 1);
    assert.equal(JSON.stringify(inputs.map(i => i.target)).includes('ordinary text'), false);
    assert.equal(JSON.stringify(events).includes('never-reference-live-secret'), false);
    await assert.rejects(host.ensureSafeInput(host.page.locator('#guarded')), { code: 'sensitiveInput' });
    await host.page.locator('#guarded').focus();
    await host.page.keyboard.insertText('never-send-guarded-value');
    const pending = await host.flushCapture();
    assert.equal(JSON.stringify([...events, pending]).includes('never-send-guarded-value'), false);
    assert.ok(events.some(e => e.interaction?.kind === 'sensitiveInput'));
  });

test('real pinned engine: blank launch, redirect-hop prevention, subframes, credential labels and recoverable handover',
  { skip: !available, timeout: 60000 }, async t => {
    const previousCwd = process.cwd(), directory = await mkdtemp(join(tmpdir(), 'aura-browser-host-chrome-'));
    const requests = [], events = [];
    const external = createServer((request, response) => {
      requests.push(request.url);
      response.setHeader('Content-Type', 'text/html');
      response.end('<html><body>Local external-origin fixture</body></html>');
    });
    const other = await listen(external);
    let startRequests = 0, base;
    const site = createServer((request, response) => {
      if (request.url === '/redirect-one') { response.writeHead(302, { Location: `${base}/redirect-two` }); response.end(); }
      else if (request.url === '/redirect-two') { response.writeHead(307, { Location: `${other}/blocked-hop` }); response.end(); }
      else if (request.url === '/handover-start') { response.writeHead(302, { Location: `${other}/manual` }); response.end(); }
      else if (request.url === '/post-redirect') { response.writeHead(307, { Location: `${other}/blocked-post` }); response.end(); }
      else {
        if (request.url === '/start') startRequests++;
        response.setHeader('Content-Type', 'text/html');
        // localhost versus 127.0.0.1 exercises a cross-site (out-of-process) iframe, not just a different port.
        response.end(request.url === '/frames' ? `<iframe src="${other.replace('127.0.0.1', 'localhost')}/frame"></iframe>` :
          '<html><body><span id="identity">Email address</span><span id="description">Account</span><input id="f1" aria-labelledby="description identity"></body></html>');
      }
    });
    base = await listen(site);
    const notifications = new EventEmitter();
    const host = new BrowserHost(event => { events.push(event); notifications.emit(event.event, event); });
    t.after(async () => {
      await host.close().catch(() => {});
      site.closeAllConnections(); external.closeAllConnections();
      await Promise.all([new Promise(resolve => site.close(resolve)), new Promise(resolve => external.close(resolve))]);
      process.chdir(previousCwd);
      await rm(directory, { recursive: true, force: true });
    });
    process.chdir(engine);
    // A fresh profile misses the Restore pages bubble left by an interrupted prior session.
    const profile = join(directory, 'profile');
    await mkdir(join(profile, 'Default'), { recursive: true });
    await writeFile(join(profile, 'Default', 'Preferences'), JSON.stringify({ profile: { exit_type: 'Crashed', exited_cleanly: false } }));
    const session = await host.launch({ profileDir: profile, startURL: `${base}/start`,
      allowedOrigins: [base], window: { width: 1280, height: 800 }, capture: false });
    assert.ok(session.chromePid > 0);
    const commandLine = execFileSync('/bin/ps', ['-p', String(session.chromePid), '-o', 'args='], { encoding: 'utf8' });
    assert.match(commandLine, /(?:^|\s)--hide-crash-restore-bubble(?:\s|$)/);
    assert.equal(host.page.url(), 'about:blank');
    assert.equal(startRequests, 0, 'launch must not visit startURL');
    const calibration = await host.calibration();
    assert.ok(calibration.viewport.width > 0);
    const image = await host.page.screenshot();
    assert.deepEqual([...image.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);

    await assert.rejects(host.navigateForHandover(`${base}/start`), { code: 'userControlRequired' });
    await host.setUserControl(true);
    await host.navigateForHandover(`${base}/start`);
    assert.equal(startRequests, 1); assert.equal(host.calibrating, false);
    await assert.rejects(host.perform({ action: 'wait', seconds: 0 }, pacing), { code: 'userControl' });
    await assert.rejects(host.navigateForHandover(`${other}/disallowed-initial`), { code: 'originRefused' });
    assert.equal(requests.includes('/disallowed-initial'), false);
    const handoverEventCount = events.length;
    await host.navigateForHandover(`${base}/handover-start`);
    assert.equal(host.page.url(), `${other}/manual`);
    assert.equal(events.length, handoverEventCount, 'handover navigation must not publish page events');
    await assert.rejects(host.setUserControl(false), { code: 'notReady' });
    assert.equal(host.userControl, true);
    await host.navigateForHandover(`${base}/start`);
    await host.setUserControl(false);

    await assert.rejects(host.perform({ action: 'goto', url: `${base}/redirect-one` }, pacing));
    await waitForErrorPage(host.page);
    assert.equal(requests.includes('/blocked-hop'), false, 'external redirect hop reached the server');
    assert.ok(events.some(e => e.event === 'navigationRefused' && e.url === `${other}/blocked-hop`));
    await host.perform({ action: 'goto', url: `${base}/start` }, pacing);
    // A 307 must not send the original POST body to a disallowed origin either.
    const postBlocked = once(notifications, 'navigationRefused');
    await host.page.evaluate(() => {
      const form = document.createElement('form'); form.method = 'POST'; form.action = '/post-redirect';
      document.body.append(form); form.submit();
    });
    assert.equal((await postBlocked)[0].url, `${other}/blocked-post`);
    await waitForErrorPage(host.page);
    assert.equal(requests.includes('/blocked-post'), false);

    const frameLoaded = new Promise(resolve => external.on('request', request => { if (request.url === '/frame') resolve(); }));
    await host.perform({ action: 'goto', url: `${base}/frames` }, pacing);
    await frameLoaded;
    assert.ok(requests.includes('/frame'), 'HTTP(S) subframes must load even outside handover');
    await host.perform({ action: 'goto', url: `${base}/start` }, pacing);
    const target = { candidates: [{ css: '#f1' }] };
    await assert.rejects(host.perform({ action: 'fill', target, value: { literal: 'non-secret-test-value' } }, pacing), { code: 'sensitiveInput' });
    await host.page.locator('#f1').focus();
    await assert.rejects(host.perform({ action: 'press', key: 'Enter' }, pacing), { code: 'sensitiveInput' });
    assert.equal(await host.page.locator('#f1').inputValue(), '');

    await host.setUserControl(true);
    const handoverFrameLoaded = new Promise(resolve => external.on('request', request => { if (request.url === '/frame') resolve(); }));
    await host.navigateForHandover(`${base}/frames`);
    await handoverFrameLoaded;
    await host.page.goto(`${other}/manual`);
    const popupCreated = host.context.waitForEvent('page');
    await host.page.evaluate(url => window.open(url), `${other}/popup`);
    const popup = await popupCreated;
    await popup.waitForLoadState('domcontentloaded');
    await assert.rejects(host.setUserControl(false), { code: 'notReady' });
    assert.equal(host.userControl, true); assert.equal(popup.isClosed(), false); assert.equal(host.page.isClosed(), false);
    await host.page.goto(`${base}/start`);
    await host.setUserControl(false);
    assert.equal(popup.isClosed(), true);
    assert.ok((await host.metrics()).width > 0);

    const deniedPopup = host.context.waitForEvent('page');
    await host.page.evaluate(url => window.open(url), `${other}/popup-denied`);
    const denied = await deniedPopup;
    if (!denied.isClosed()) await denied.waitForEvent('close');
    assert.equal(requests.includes('/popup-denied'), false, 'a refused popup must not issue a document request');
  });

test('real Chrome: a demonstration describes clicks and typing semantically and never a credential',
  { skip: !available, timeout: 60000 }, async t => {
    const previousCwd = process.cwd(), directory = await mkdtemp(join(tmpdir(), 'aura-capture-chrome-'));
    const events = [];
    const listen2 = async server => { server.listen(0, '127.0.0.1'); await once(server, 'listening'); return `http://127.0.0.1:${server.address().port}`; };
    const page = '<html><body><nav><a href="/next">Open settings</a></nav>' +
      '<button data-testid="create-agent">Create agent</button><button id="dup">Save</button><button id="dup2">Save</button>' +
      '<label for="site">Website</label><input id="site" type="text">' +
      '<label for="pw">Password</label><input id="pw" type="password"></body></html>';
    const external = createServer((request, response) => { response.setHeader('Content-Type', 'text/html'); response.end('<html><body><button id="idp">Continue</button></body></html>'); });
    const other = await listen2(external);
    const site = createServer((request, response) => { response.setHeader('Content-Type', 'text/html'); response.end(page); });
    const base = await listen2(site);
    const host = new BrowserHost(event => events.push(event));
    t.after(async () => {
      await host.close().catch(() => {});
      site.closeAllConnections(); external.closeAllConnections();
      await Promise.all([new Promise(resolve => site.close(resolve)), new Promise(resolve => external.close(resolve))]);
      process.chdir(previousCwd);
      await rm(directory, { recursive: true, force: true });
    });
    const captured = () => events.filter(e => e.event === 'captured').map(e => e.interaction);
    const settle = () => new Promise(resolve => setTimeout(resolve, 150));
    process.chdir(engine);
    await host.launch({ profileDir: join(directory, 'profile'), startURL: `${base}/start`, allowedOrigins: [base],
      window: { width: 1280, height: 800 }, capture: true });
    assert.equal(host.userControl, true, 'the user holds the browser for the whole demonstration');
    await assert.rejects(host.perform({ action: 'wait', seconds: 0 }, pacing), { code: 'userControl' });
    await assert.rejects(host.setUserControl(false), { code: 'capturing' });
    await host.navigateForHandover(`${base}/start`);
    assert.ok(events.some(e => e.event === 'navigated' && e.clean === true), 'navigation is reported, with whether the URL is clean');

    await host.page.click('[data-testid=create-agent]'); await settle();
    const click = captured().at(-1);
    assert.equal(click.kind, 'click');
    assert.deepEqual(click.target.candidates[0], { testId: 'create-agent' });
    assert.ok(click.target.candidates.some(c => c.role === 'button' && c.name === 'Create agent'));
    assert.ok(click.rect.width > 0 && click.target.hintRect.width > 0);

    // Two buttons with the same name cannot be told apart by role and name, so that candidate is withheld.
    await host.page.click('#dup'); await settle();
    const ambiguous = captured().at(-1);
    assert.equal(ambiguous.kind, 'click');
    assert.equal(ambiguous.target.candidates.some(c => c.role === 'button' && c.name === 'Save'), false);
    assert.ok(ambiguous.target.candidates.some(c => c.css), 'but a structural path still identifies it');

    const before = captured().length;
    await host.page.click('#site'); await settle();
    assert.equal(captured().length, before, 'focusing a text field is not a step');
    await host.page.keyboard.type('https://example.com');
    await host.page.click('[data-testid=create-agent]'); await settle();
    const typed = captured().filter(c => c.kind === 'input');
    assert.equal(typed.length, 1, 'typing is one step, not one per keystroke');
    assert.equal(typed[0].value, 'https://example.com');
    assert.deepEqual(typed[0].target.candidates.find(c => c.role), { role: 'textbox', name: 'Website' });

    await host.page.click('#pw'); await settle();
    await host.page.keyboard.type('hunter2-not-a-real-password');
    await host.page.keyboard.press('Tab'); await settle();
    assert.ok(captured().some(c => c.kind === 'sensitiveInput'), 'a credential field is reported as a handover, with no value');
    assert.equal(JSON.stringify(events).includes('hunter2'), false, 'the typed secret appears in no event');

    await host.page.keyboard.press('Escape'); await settle();
    assert.deepEqual(captured().at(-1), { kind: 'press', key: 'Escape' });

    const count = captured().length;
    await host.page.goto(`${other}/idp`);
    await host.page.click('#idp'); await settle();
    assert.equal(captured().length, count, 'a page on another origin, such as an identity provider, is never described');
  });
