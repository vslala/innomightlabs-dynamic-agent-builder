// Run from spa/: node scripts/artifacts-library.browser.mjs
// Uses existing Playwright/npm-exec caches only; never downloads dependencies or browsers.
// Optional: PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs
// Optional: PLAYWRIGHT_EXECUTABLE_PATH=/absolute/path/to/chromium
import assert from 'node:assert/strict';
import { access, mkdir, readdir } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createServer } from 'vite';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
async function loadPlaywright() {
  if (process.env.PLAYWRIGHT_MODULE) return import(pathToFileURL(resolve(process.env.PLAYWRIGHT_MODULE)).href);
  try { return await import('playwright'); } catch (error) {
    if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error;
  }
  const cache = join(homedir(), '.npm', '_npx');
  for (const entry of (await readdir(cache).catch(() => [])).sort()) {
    try {
      const candidate = await import(pathToFileURL(join(cache, entry, 'node_modules/playwright/index.mjs')).href);
      await access(process.env.PLAYWRIGHT_EXECUTABLE_PATH || candidate.chromium.executablePath());
      return candidate;
    } catch (error) {
      if (error.code !== 'ERR_MODULE_NOT_FOUND' && error.code !== 'ENOENT') throw error;
    }
  }
  throw new Error('Playwright not found. Set PLAYWRIGHT_MODULE to an existing installation.');
}

const long = 'UnbrokenQuarterlyRevenueAndCustomerRetention'.repeat(4);
const ids = { agent: `agent-${long}`, automation: `automation-${long}`, conversation: `conversation-${long}`, skill: `skill-${long}` };
const names = {
  agents: { [ids.agent]: `Research agent ${long}` },
  automations: { [ids.automation]: `Revenue workflow ${long}` },
  conversations: { [ids.conversation]: `Planning conversation ${long}` },
  skills: { [ids.skill]: `Report builder ${long}` },
};
const recent = days => new Date(Date.now() - days * 86400000).toISOString();
const artifact = (key, title, type, days, source) => {
  const [extension, mime] = {
    html_report: ['html', 'text/html'], image: ['png', 'image/png'],
    csv: ['csv', 'text/csv'], text: ['txt', 'text/plain'], json: ['json', 'application/json'],
  }[type];
  return {
    artifact_id: `${key}-${long}`, title, artifact_type: type, filename: `${key}-${long}.${extension}`,
    mime_type: mime, size_bytes: 123456,
    created_at: recent(days), source: { metadata: {}, ...source },
    url: `https://artifact-content.invalid/${key}/download`, view_url: `https://artifact-content.invalid/${key}/view`,
  };
};
const automationSource = {
  agent_id: ids.agent, automation_id: ids.automation, conversation_id: ids.conversation, skill_id: ids.skill,
  automation_run_id: `run-${long}`, automation_node_id: `node-${long}`, message_id: `message-${long}`,
};
const fixtures = [
  artifact('report', `Quarterly report ${long}`, 'html_report', 1, automationSource),
  artifact('image', 'Conversation image', 'image', 2, { agent_id: ids.agent, conversation_id: ids.conversation }),
  artifact('old', 'Archived report', 'html_report', 40, automationSource),
  artifact('csv', 'Recent conversation CSV', 'csv', 3, { agent_id: 'agent-unresolved-long-id-12345678901234567890', conversation_id: 'conversation-unresolved-12345678901234567890' }),
  artifact('unknown', 'Unknown origin notes', 'text', 15, {}),
  artifact('json', 'Recent workflow JSON', 'json', 4, { automation_id: ids.automation }),
];

// Normal-length screenshot data is isolated from the long-name regression fixtures.
const visualFixtures = JSON.parse(JSON.stringify(fixtures).replaceAll(long, '2026')).map((item, index) => ({
  ...item,
  title: ['Quarterly revenue report', 'Customer growth chart', 'Archived revenue report', 'Customer retention data', 'Research notes', 'Workflow results'][index],
  filename: ['quarterly-revenue.html', 'growth-chart.png', 'archived-revenue.html', 'retention.csv', 'research-notes.txt', 'workflow-results.json'][index],
  source: index === 3 ? { ...item.source, agent_id: 'agent-support', conversation_id: 'conversation-support' } : item.source,
}));
const visualNames = {
  agents: { 'agent-2026': 'Research Agent', 'agent-support': 'Support Agent' },
  automations: { 'automation-2026': 'Revenue workflow' },
  conversations: { 'conversation-2026': 'Quarterly planning', 'conversation-support': 'Customer retention' },
  skills: { 'skill-2026': 'Report builder' },
};

// Only shell/data and parent-owned state are synthetic; panel, selects, dialog, and CSS are real.
const entry = `
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { MemoryRouter } from 'react-router-dom';
import { ArtifactsPagePanel } from '/src/pages/dashboard/ArtifactsPagePanel.tsx';
import { ConfirmationDialog } from '/src/components/ui/confirmation-dialog.tsx';
import '/src/index.css';
import '/src/components/dashboard/DashboardLayout.css';
const visual = new URLSearchParams(window.location.search).get('visual') === '1';
const fixtures = visual ? ${JSON.stringify(visualFixtures)} : ${JSON.stringify(fixtures)};
const sourceNames = visual ? ${JSON.stringify(visualNames)} : ${JSON.stringify(names)};
function Harness() {
  const [artifacts, setArtifacts] = useState(fixtures);
  const [selected, setSelected] = useState([]);
  const [pending, setPending] = useState(null);
  const [notification, setNotification] = useState(null);
  return <>
    <ArtifactsPagePanel artifacts={artifacts} sourceNames={sourceNames} selected={selected}
      loading={false} error={null} locked={pending !== null} notification={notification}
      onSelectionChange={setSelected} onReload={() => {}} onDismiss={() => setNotification(null)}
      onDelete={artifact => setPending([artifact.artifact_id])} onBulkDelete={() => setPending([...selected])} />
    <ConfirmationDialog open={pending !== null} onOpenChange={open => { if (!open) setPending(null); }}
      title="Delete selected artifacts?" description={'Delete ' + (pending?.length ?? 0) + ' selected artifacts. This cannot be undone.'}
      confirmText="Delete artifacts" variant="destructive" onConfirm={() => {
        const deleted = pending ?? [];
        setArtifacts(current => current.filter(artifact => !deleted.includes(artifact.artifact_id)));
        setSelected(current => current.filter(id => !deleted.includes(id)));
        setNotification({ variant: 'success', message: deleted.length + ' artifacts deleted.' });
        setPending(null);
      }} />
  </>;
}
function App() {
  const [revision, setRevision] = useState(0);
  window.resetHarness = () => flushSync(() => setRevision(current => current + 1));
  return <MemoryRouter><div className="dashboard-layout">
    <nav data-sidebar aria-label="Fixture sidebar">Dashboard</nav>
    <div className="dashboard-layout__body"><main className="dashboard-layout__main">
      <div className="dashboard-layout__content" data-content><Harness key={revision} /></div>
    </main></div>
  </div></MemoryRouter>;
}
createRoot(document.getElementById('root')).render(<App />);
`;
const shellCss = '[data-sidebar]{width:240px;flex:0 0 240px}@media(max-width:900px){[data-sidebar]{display:none}}';
let server;
let browser;
let failures = 0;
let passes = 0;
let deadline;
let timedOut = false;
const errors = [];
const contentRequests = [];

async function run() {
  const { chromium } = await loadPlaywright();
  server = await createServer({
    root, configFile: join(root, 'vite.config.ts'), logLevel: 'warn',
    server: { host: '127.0.0.1', port: 0, strictPort: false },
    plugins: [{
      name: 'artifacts-library-browser-fixture',
      resolveId(id) { if (id === '/__artifacts-library.tsx') return root + id; },
      load(id) { if (id === root + '/__artifacts-library.tsx') return entry; },
      configureServer(vite) {
        vite.middlewares.use('/__artifacts-library/', async (req, res, next) => {
          if (req.url !== '/' && req.url !== '' && !req.url.startsWith('/?')) return next();
          try {
            const html = await vite.transformIndexHtml('/__artifacts-library/', '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="icon" href="data:,"><style>' + shellCss + '</style></head><body style="margin:0"><div id="root"></div><script type="module" src="/__artifacts-library.tsx"></script></body></html>');
            res.setHeader('Content-Type', 'text/html');
            res.end(html);
          } catch (error) { next(error); }
        });
      },
    }],
  });
  await server.listen();
  const address = server.httpServer.address();
  assert.ok(address && typeof address === 'object');
  browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : {}) });
  for (const width of [320, 390, 768, 1024, 1440]) for (const theme of ['light', 'dark']) {
    const label = `${width}px ${theme}`;
    const page = await browser.newPage({ viewport: { width, height: 900 }, colorScheme: theme, reducedMotion: 'reduce' });
    page.setDefaultTimeout(2500);
    page.on('pageerror', error => errors.push({ label, error: String(error) }));
    await page.route('**/*', route => {
      const request = route.request();
      const url = new URL(request.url());
      // Fail closed: browsing metadata must never fetch artifact bytes, signed URLs, or APIs.
      if (url.hostname === 'artifact-content.invalid' || /\/artifacts(?:\/|\?|$)/.test(url.pathname) || ['fetch', 'xhr'].includes(request.resourceType())) {
        contentRequests.push({ label, url: request.url(), type: request.resourceType() });
        return route.abort();
      }
      return route.continue();
    });
    await page.addInitScript(theme => {
          document.addEventListener('DOMContentLoaded', () => { document.documentElement.dataset.theme = theme; }, { once: true });
        }, theme);
    await page.goto(`http://127.0.0.1:${address.port}/__artifacts-library/`);
    await page.getByRole('heading', { name: 'Artifacts', exact: true }).waitFor();
    const search = page.getByRole('searchbox', { name: 'Search artifacts and sources' });
    const title = index => page.getByRole('button', { name: `Show details: ${fixtures[index].title}`, exact: true });
    const checkbox = index => page.getByRole('checkbox', { name: `Select artifact: ${fixtures[index].title}`, exact: true });
    const rows = () => page.locator('li').filter({ has: page.locator('button[aria-label^="Show details:"]') });
    const count = async expected => {
      await page.getByRole('status').filter({ hasText: `${expected} of 6 loaded` }).waitFor();
      assert.equal(await rows().count(), expected, 'Matching row count');
    };
    async function select(label, option) {
      await page.getByRole('combobox', { name: label, exact: true }).click();
      await page.getByRole('option', { name: option, exact: true }).click();
    }
    async function reset() {
      await page.keyboard.press('Escape');
      await page.evaluate(() => window.resetHarness());
      await title(0).waitFor();
      assert.equal(await search.inputValue(), '');
    }
    async function check(name, test) {
      if (timedOut) throw new Error('Browser regression deadline reached');
      try {
        await reset();
        const evidence = await test();
        passes++;
        console.log('PASS', label, name, JSON.stringify(evidence ?? {}));
      } catch (error) {
        failures++;
        console.error('FAIL', label, name, error.stack ?? String(error));
      }
    }
    async function noOverflow(stage) {
      const evidence = await page.evaluate(() => {
        const nodes = [document.documentElement, document.body, document.querySelector('main'), document.querySelector('[data-content]'), document.querySelector('section[aria-labelledby="artifacts-heading"]')];
        return nodes.map(el => ({ tag: el.tagName, class: el.className, client: el.clientWidth, scroll: el.scrollWidth, left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right }));
      });
      assert.ok(evidence.every(el => el.scroll <= el.client + 1 && el.left >= -1 && el.right <= width + 1), `${stage} overflow: ${JSON.stringify(evidence)}`);
      return evidence;
    }
    await check('layout, long metadata, title activation, inspector placement', async () => {
      await count(6);
      const shell = await page.locator('main').evaluate(el => ({ padding: getComputedStyle(el).paddingLeft, sidebar: document.querySelector('[data-sidebar]').getBoundingClientRect().width, theme: document.documentElement.dataset.theme }));
      assert.equal(shell.theme, theme);
      assert.equal(shell.sidebar, width > 900 ? 240 : 0);
      if (width <= 640) assert.equal(shell.padding, '16px');
      const dimensions = await noOverflow('initial long title/filename/source names');
      await title(1).click();
      assert.equal(await title(1).getAttribute('aria-pressed'), 'true');
      assert.equal(await title(0).getAttribute('aria-pressed'), 'false');
      assert.equal(await page.locator('button[aria-label^="Show details:"][aria-pressed="true"]').count(), 1);
      const activeRow = rows().filter({ has: title(1) });
      const inline = activeRow.locator('section[aria-label^="Details for"]');
      const side = page.getByRole('complementary', { name: 'Selected artifact details' });
      assert.equal(await inline.isVisible(), width < 1280, 'Inline inspector belongs to active row below desktop breakpoint');
      assert.equal(await side.isVisible(), width >= 1280, 'Desktop side inspector breakpoint');
      if (width >= 1280) {
        const a = await activeRow.boundingBox(), b = await side.boundingBox();
        assert.ok(b.x >= a.x + a.width, `Side inspector must be alongside results: ${JSON.stringify({ a, b })}`);
      } else {
        const a = await title(1).boundingBox(), b = await inline.boundingBox();
        assert.ok(b.y >= a.y + a.height, 'Inline inspector follows its active title in the same row');
      }
      assert.equal(await checkbox(1).isChecked(), false, 'Inspecting must not select for deletion');
      await title(0).click();
      await noOverflow('reactivated longest artifact');
      return { shell, dimensions };
    });
    await check('format tiles, metadata-only cover, and technical details keyboard disclosure', async () => {
      for (const [index, format] of [[0, 'HTML'], [1, 'PNG'], [3, 'CSV']]) {
        const row = rows().filter({ has: title(index) });
        await row.getByRole('img', { name: `${format} file`, exact: true }).and(row.locator(':scope > [role="img"]')).waitFor();
      }
      const inspector = page.locator('section[aria-label^="Details for"]').filter({ visible: true });
      await inspector.getByRole('img', { name: 'HTML file', exact: true }).waitFor();
      assert.equal(await inspector.locator('img, iframe, canvas').count(), 0, 'Cover must show format, not artifact content');
      const technical = inspector.locator('details');
      const summary = technical.locator(':scope > summary');
      assert.equal(await technical.getAttribute('open'), null, 'Technical details start collapsed');
      assert.equal(await technical.locator('code').first().isVisible(), false);
      await summary.focus();
      await page.keyboard.press('Enter');
      await technical.locator('code').first().waitFor();
      assert.notEqual(await technical.getAttribute('open'), null);
      assert.deepEqual(await technical.locator('code').allTextContents(), [
        fixtures[0].artifact_id, ids.agent, ids.automation, automationSource.automation_run_id,
        automationSource.automation_node_id, ids.conversation, automationSource.message_id, ids.skill,
      ], 'Expanded disclosure preserves every full, untruncated ID');
      const bounds = await technical.locator('code').evaluateAll(nodes => nodes.map(el => ({ client: el.clientWidth, scroll: el.scrollWidth, width: el.getBoundingClientRect().width })));
      assert.ok(bounds.every(el => el.width > 0 && el.scroll <= el.client + 1), `Technical IDs overflow: ${JSON.stringify(bounds)}`);
      await noOverflow('expanded technical details with full long IDs');
      await summary.focus();
      await page.keyboard.press('Space');
      assert.equal(await technical.getAttribute('open'), null, 'Space collapses technical details');
      assert.equal(await technical.locator('code').first().isVisible(), false);
      await title(1).click();
      await inspector.getByRole('img', { name: 'PNG file', exact: true }).waitFor();
    });
    await check('row actions remain keyboard reachable when hidden at rest', async () => {
      await page.mouse.move(0, 0);
      await search.focus();
      const row = rows().filter({ has: title(0) });
      const open = row.getByRole('link', { name: `Open artifact: ${fixtures[0].title}`, exact: true });
      const remove = row.getByRole('button', { name: `Delete artifact: ${fixtures[0].title}`, exact: true });
      if (width >= 1280) {
        assert.equal(await open.evaluate(el => getComputedStyle(el.parentElement).opacity), '0');
        assert.equal(await open.evaluate(el => getComputedStyle(el.parentElement).pointerEvents), 'none');
      }
      await title(0).focus();
      await page.keyboard.press('Tab');
      assert.equal(await open.evaluate(el => el === document.activeElement), true, 'Tab reaches Open');
      assert.equal(await open.evaluate(el => getComputedStyle(el.parentElement).opacity), '1');
      assert.equal(await open.evaluate(el => getComputedStyle(el.parentElement).pointerEvents), 'auto');
      await page.keyboard.press('Tab');
      assert.equal(await remove.evaluate(el => el === document.activeElement), true, 'Tab reaches Delete');
      await page.keyboard.press('Enter');
      const dialog = page.getByRole('dialog');
      await dialog.waitFor();
      await dialog.getByText('Delete 1 selected artifacts. This cannot be undone.', { exact: true }).waitFor();
      await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.equal(await rows().count(), 6, 'Cancel keeps the artifact');
    });
    await check('combined Radix filters, clear search, no-match reset', async () => {
      await search.fill('Revenue workflow');
      await count(3);
      await select('Artifact format', 'HTML reports');
      await count(2);
      await select('Creation source', 'Automations');
      await count(2);
      await select('Creation date', 'Last 7 days');
      await count(1);
      assert.equal(await title(0).count(), 1);
      await noOverflow('combined filters');
      await search.fill('not-a-real-artifact');
      await count(0);
      await page.getByText('No matching artifacts', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
      await count(6);
      assert.equal(await search.inputValue(), '');
      for (const [label, text] of [['Artifact format', 'All formats'], ['Creation source', 'All sources'], ['Creation date', 'Any time']]) {
        assert.equal((await page.getByRole('combobox', { name: label }).textContent()).trim(), text);
      }
      await search.fill(fixtures[3].filename);
      await count(1);
      await search.fill('');
      await count(6);
    });
    await check('grouping, keyboard collapse, and collapse preservation', async () => {
      const group = page.locator('details[data-artifact-group]').filter({ has: page.locator(':scope > summary').filter({ hasText: names.agents[ids.agent] }) });
      assert.equal(await group.count(), 1);
      await group.locator(':scope > summary').focus();
      await page.keyboard.press('Enter');
      await page.waitForFunction(name => [...document.querySelectorAll('details[data-artifact-group]')].some(el => el.querySelector(':scope > summary').textContent.includes(name) && !el.open), names.agents[ids.agent]);
      assert.equal(await group.getAttribute('open'), null, 'Enter collapses group');
      assert.equal(await title(0).isVisible(), false);
      await page.getByRole('button', { name: 'By automation', exact: true }).click();
      assert.equal(await page.locator('details[data-artifact-group]').count(), 3);
      await page.getByRole('button', { name: 'All files', exact: true }).click();
      assert.equal(await page.locator('details[data-artifact-group]').count(), 1);
      await page.getByRole('button', { name: 'By agent', exact: true }).click();
      assert.equal(await group.getAttribute('open'), null, 'Returning to grouping preserves collapse');
      await search.fill('Quarterly');
      await search.fill('');
      assert.equal(await group.getAttribute('open'), null, 'Search preserves collapse');
      await group.locator(':scope > summary').focus();
      await page.keyboard.press('Space');
      await title(0).waitFor();
      assert.notEqual(await group.getAttribute('open'), null, 'Space reopens group');
      assert.equal(await title(0).isVisible(), true);
    });
    await check('selection, hidden count, select-visible preservation, clear', async () => {
      await checkbox(0).check();
      await checkbox(1).check();
      assert.equal(await page.getByRole('checkbox', { name: 'Select visible artifacts' }).getAttribute('aria-checked'), 'mixed');
      await search.fill('Recent conversation CSV');
      await page.getByText('2 selected (2 hidden by filters)', { exact: true }).waitFor();
      const all = page.getByRole('checkbox', { name: 'Select visible artifacts' });
      await all.check();
      await page.getByText('3 selected (2 hidden by filters)', { exact: true }).waitFor();
      await noOverflow('hidden selection feedback');
      await all.uncheck();
      await page.getByText('2 selected (2 hidden by filters)', { exact: true }).waitFor();
      await search.fill('');
      assert.equal(await checkbox(0).isChecked(), true);
      assert.equal(await checkbox(1).isChecked(), true);
      assert.equal(await checkbox(3).isChecked(), false);
      await page.getByRole('button', { name: 'Clear selection', exact: true }).click();
      await page.getByText('0 selected', { exact: true }).waitFor();
      assert.equal(await page.getByRole('button', { name: 'Delete selected', exact: true }).isDisabled(), true);
    });
    await check('real confirmation cancel/confirm, bulk feedback, dismiss', async () => {
      await checkbox(0).check();
      await checkbox(1).check();
      await page.getByRole('button', { name: 'Delete selected', exact: true }).click();
      const dialog = page.getByRole('dialog');
      await dialog.waitFor();
      await dialog.getByText('Delete 2 selected artifacts. This cannot be undone.', { exact: true }).waitFor();
      assert.equal(await page.getByRole('searchbox', { name: 'Search artifacts and sources', includeHidden: true }).isDisabled(), true, 'Panel locked during confirmation');
      await noOverflow('confirmation');
      await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.equal(await checkbox(0).isChecked(), true, 'Cancel preserves selection');
      await page.getByRole('button', { name: 'Delete selected', exact: true }).click();
      await dialog.getByRole('button', { name: 'Delete artifacts', exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      await page.getByRole('status').filter({ hasText: '2 artifacts deleted.' }).waitFor();
      assert.equal(await rows().count(), 4);
      await page.getByText('0 selected', { exact: true }).waitFor();
      await noOverflow('deletion feedback');
      await page.getByRole('button', { name: 'Dismiss notification', exact: true }).click();
      assert.equal(await page.getByText('2 artifacts deleted.', { exact: true }).count(), 0);
    });
    await check('Radix sort and metadata-only open links', async () => {
      await page.getByRole('button', { name: 'All files', exact: true }).click();
      await select('Sort artifacts', 'Oldest first');
      assert.equal(await rows().first().getByRole('button', { name: /^Show details:/ }).getAttribute('aria-label'), `Show details: ${fixtures[2].title}`);
      await select('Sort artifacts', 'Name A–Z');
      const actual = await rows().getByRole('button', { name: /^Show details:/ }).allTextContents();
      assert.deepEqual(actual, fixtures.map(a => a.title).sort((a, b) => a.localeCompare(b)));
      const link = page.getByRole('link', { name: `Open artifact: ${fixtures[0].title}`, exact: true });
      assert.equal(await link.getAttribute('href'), `/dashboard/artifacts/${encodeURIComponent(fixtures[0].artifact_id)}`);
      assert.deepEqual(contentRequests.filter(request => request.label === label), [], 'Browsing must not request artifact content or APIs');
    });
    if (theme === 'dark' && [1440, 390].includes(width)) {
      await check('normal-length visual fixture screenshot', async () => {
        await page.goto(`http://127.0.0.1:${address.port}/__artifacts-library/?visual=1`);
        await page.getByRole('button', { name: 'Show details: Quarterly revenue report', exact: true }).waitFor();
        await page.getByRole('img', { name: 'HTML file', exact: true }).first().waitFor();
        await page.evaluate(() => document.fonts.ready);
        await noOverflow('normal-length visual fixture');
        await page.mouse.move(0, 0);
        await page.evaluate(() => window.scrollTo(0, 0));
        const path = join(root, 'node_modules/.cache', `artifacts-library-${width === 1440 ? 'desktop' : 'mobile'}.png`);
        await mkdir(dirname(path), { recursive: true });
        await page.screenshot({ path, fullPage: true, animations: 'disabled' });
        return { path, width, theme };
      });
    }
    await page.close();
  }
  assert.deepEqual(errors, [], 'Uncaught browser page errors');
  assert.deepEqual(contentRequests, [], 'Unexpected artifact content/API requests');
}

try {
  await Promise.race([
    run(),
    new Promise((_, reject) => { deadline = setTimeout(() => { timedOut = true; reject(new Error('Artifacts library browser test exceeded 120 seconds')); }, 120_000); }),
  ]);
} catch (error) {
  failures++;
  console.error('FAIL browser regression', error.stack ?? String(error));
} finally {
  await browser?.close();
  await server?.close();
  clearTimeout(deadline);
  console.log(JSON.stringify({ passes, failures, pageErrors: errors, unexpectedRequests: contentRequests }));
  if (failures) process.exitCode = 1;
}
