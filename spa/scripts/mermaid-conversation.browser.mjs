// Run from spa/: node scripts/mermaid-conversation.browser.mjs
// Uses installed Playwright or an existing npm-exec cache; never downloads dependencies/browsers.
// Optional: PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs
// Optional: PLAYWRIGHT_EXECUTABLE_PATH=/absolute/path/to/chromium
import assert from 'node:assert/strict';
import { access, readdir } from 'node:fs/promises';
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

// Only the fixture shell is synthetic: renderers, Mermaid runtime, and scroll-parent CSS are real.
const entry = `
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MarkdownRenderer } from '/src/components/ui/markdown-renderer.tsx';
import { Markdown } from '/embed/app/components/Markdown.tsx';
import dashboard from '/src/pages/dashboard/Conversation.module.css';
const embed = new URLSearchParams(location.search).has('embed');
if (embed) await import('/embed/app/styles.css'); else await import('/src/index.css');
function App() {
  // Vite can reload once when it discovers Mermaid's cold lazy dependencies.
  const [state, setState] = useState({ content: sessionStorage.getItem('mermaid-browser-content') || '', revision: 0 });
  window.setHarness = content => {
    sessionStorage.setItem('mermaid-browser-content', content);
    setState(previous => ({ content, revision: previous.revision + 1 }));
  };
  return <main style={{height: '100dvh', display: 'flex', flexDirection: 'column', overflow: 'hidden'}}>
    <div data-conversation className={embed ? 'ie-messages' : dashboard.messagesPane}>
      <article key={state.revision} style={{flexShrink: 0, minWidth: 0}} className={embed ? 'ie-bubble ie-bubble-assistant' : undefined}>
        {embed ? <Markdown content={state.content} /> : <MarkdownRenderer content={state.content} />}
      </article>
      <p data-end style={{flexShrink: 0, minHeight: state.content.includes('flowchart LR') ? 740 : 400}}>Conversation end</p>
    </div>
  </main>;
}
createRoot(document.getElementById('root')).render(<App />);
`;
const fence = source => '```mermaid\n' + source + '\n```';
const tall = 'flowchart TD\n' + Array.from({ length: 32 }, (_, i) => `N${i}[Step ${i}: validate input and prepare the next operation] --> N${i + 1}`).join('\n');
const wide = 'flowchart LR\n' + Array.from({ length: 12 }, (_, i) => `N${i}[Operation ${i}] --> N${i + 1}`).join('\n');
let server;
let browser;
let failures = 0;
const errors = [];
const deadline = setTimeout(() => {
  console.error('Mermaid conversation browser test exceeded 120 seconds');
  process.exit(124);
}, 120_000);

try {
  const { chromium } = await loadPlaywright();
  server = await createServer({
    root, configFile: join(root, 'vite.config.ts'), logLevel: 'warn',
    server: { host: '127.0.0.1', port: 0, strictPort: false },
    plugins: [{
      name: 'mermaid-conversation-browser-fixture',
      resolveId(id) { if (id === '/__mermaid-conversation.tsx') return root + id; },
      load(id) { if (id === root + '/__mermaid-conversation.tsx') return entry; },
      configureServer(vite) {
        vite.middlewares.use('/__mermaid-conversation/', async (req, res, next) => {
          if (req.url !== '/' && req.url !== '' && !req.url.startsWith('/?')) return next();
          try {
            const html = await vite.transformIndexHtml('/__mermaid-conversation/', '<!doctype html><html data-theme="dark"><head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="icon" href="data:,"></head><body style="margin:0"><div id="root"></div><script type="module" src="/__mermaid-conversation.tsx"></script></body></html>');
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
  for (const embed of [false, true]) {
    const page = await browser.newPage({ viewport: { width: 390, height: 740 } });
    page.setDefaultTimeout(8_000);
    page.on('pageerror', error => errors.push(String(error)));
    await page.addInitScript(() => {
      window.measurementStages = [];
      new MutationObserver(records => {
        for (const record of records) for (const node of record.addedNodes) {
          if (!(node instanceof HTMLElement) || !node.className.includes('measurementStage') || !node.isConnected) continue;
          const style = getComputedStyle(node);
          window.measurementStages.push({ position: style.position, height: node.getBoundingClientRect().height, visibility: style.visibility, overflow: style.overflow });
        }
      }).observe(document, { childList: true, subtree: true });
    });
    await page.goto(`http://127.0.0.1:${address.port}/__mermaid-conversation/${embed ? '?embed=1' : ''}`);
    await page.waitForFunction(() => typeof window.setHarness === 'function');
    const parent = page.locator('[data-conversation]');
    const section = page.locator('section[aria-label="Mermaid diagram"]');
    const region = section.getByRole('region', { name: 'Mermaid diagram; scroll to explore', exact: true });
    const toggle = page.getByRole('button', { name: 'Toggle Mermaid source', exact: true });
    async function render(source) {
      await page.evaluate(content => window.setHarness(content), fence(source));
      await section.locator('svg[role="img"]').waitFor({ timeout: 20_000 });
      await page.waitForTimeout(300);
      await parent.evaluate(el => { el.scrollTop = 0; });
    }
    async function wheel(target, dx, dy) {
      // Aim within the visible intersection, not at a giant element's offscreen center.
      const point = await target.evaluate(el => {
        const r = el.getBoundingClientRect();
        const p = document.querySelector('[data-conversation]').getBoundingClientRect();
        const left = Math.max(r.left, p.left, 0), right = Math.min(r.right, p.right, innerWidth);
        const top = Math.max(r.top, p.top, 0), bottom = Math.min(r.bottom, p.bottom, innerHeight);
        if (right - left < 4 || bottom - top < 4) throw new Error('Wheel target not visible');
        return { x: (left + right) / 2, y: (top + bottom) / 2 };
      });
      await page.mouse.move(point.x, point.y);
      await page.mouse.wheel(dx, dy);
      // Browser/compositor scroll delivery is asynchronous, including when chaining is blocked.
      await page.waitForTimeout(140);
    }
    async function check(name, run) {
      try { console.log('PASS', embed ? 'embed' : 'dashboard', name, JSON.stringify(await run() ?? {})); }
      catch (error) { failures++; console.error('FAIL', embed ? 'embed' : 'dashboard', name, error); }
    }

    await check('tall inline diagram stays full-height; wheel reaches conversation bottom', async () => {
      await render(tall);
      const dimensions = await region.evaluate(el => ({ client: el.clientHeight, scroll: el.scrollHeight, svg: el.querySelector('svg').getBoundingClientRect().height, overscroll: getComputedStyle(el).overscrollBehavior }));
      assert.ok(dimensions.svg > 2000, 'Fixture must be taller than the conversation');
      assert.ok(dimensions.client >= dimensions.svg, 'Inline SVG must not be vertically clipped');
      assert.ok(dimensions.scroll <= dimensions.client + 1, 'Inline viewport must not scroll vertically');
      await wheel(region, 0, 400);
      assert.ok(await parent.evaluate(el => el.scrollTop > 100), 'Wheel over inline SVG must scroll the conversation');
      for (let i = 0; i < 20; i++) {
        if (await parent.evaluate(el => el.scrollHeight - el.clientHeight - el.scrollTop <= 2)) break;
        await wheel(region, 0, 900);
      }
      assert.ok(await parent.evaluate(el => el.scrollHeight - el.clientHeight - el.scrollTop <= 2), 'Wheel over diagram must reach conversation bottom');
      return { ...dimensions, parentScrollTop: await parent.evaluate(el => el.scrollTop) };
    });

    await check('short wide inline diagram chains vertical wheel and scrolls horizontally', async () => {
      await render(wide);
      const dimensions = await region.evaluate(el => ({ width: el.clientWidth, scrollWidth: el.scrollWidth, height: el.clientHeight, scrollHeight: el.scrollHeight }));
      assert.ok(dimensions.scrollWidth > dimensions.width);
      assert.ok(dimensions.height < 250);
      await wheel(region, 240, 0);
      const horizontal = await region.evaluate(el => el.scrollLeft);
      assert.ok(horizontal > 0, 'Horizontal wheel must scroll the inline viewport');
      await wheel(region, 0, 180);
      assert.ok(await parent.evaluate(el => el.scrollTop > 0), 'Vertical wheel over a short horizontal scroller must chain to conversation');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No page-level horizontal overflow');
      return { ...dimensions, horizontal, parentScrollTop: await parent.evaluate(el => el.scrollTop) };
    });

    await check('Source replaces giant SVG immediately; source wheel chains at both bounds', async () => {
      await render(tall);
      await toggle.click();
      const source = section.locator('pre');
      assert.equal(await source.locator('code').textContent(), tall);
      assert.equal(await section.locator('svg[role="img"]').isVisible(), false, 'Retained SVG must be hidden in source mode');
      assert.equal(await region.count(), 0, 'Diagram viewport must be replaced by source');
      const bounds = await source.boundingBox();
      const toolbar = await toggle.boundingBox();
      assert.ok(bounds && toolbar && bounds.y >= toolbar.y && bounds.y < toolbar.y + 100 && bounds.y < 740, 'Source must appear directly below visible toolbar');
      assert.equal(await toggle.getAttribute('aria-pressed'), 'true');
      const before = await source.evaluate(el => ({ height: el.clientHeight, scroll: el.scrollHeight }));
      assert.ok(before.scroll > before.height, 'Fixture must have scrollable source');
      await wheel(source, 0, 120);
      assert.ok(await source.evaluate(el => el.scrollTop > 0), 'Source itself must scroll');
      await source.evaluate(el => { el.scrollTop = el.scrollHeight; });
      await wheel(source, 0, 180);
      const down = await parent.evaluate(el => el.scrollTop);
      assert.ok(down > 0, 'Wheel at source bottom must chain down to conversation');
      await source.evaluate(el => { el.scrollTop = 0; });
      await wheel(source, 0, -180);
      assert.ok(await parent.evaluate((el, previous) => el.scrollTop < previous, down), 'Wheel at source top must chain up to conversation');
      await parent.evaluate(el => { el.scrollTop = 0; });
      await toggle.click();
      await section.locator('svg[role="img"]').waitFor();
      assert.equal(await section.locator('pre').count(), 0);
      return { source: before, parentAfterDown: down };
    });

    await check('source/diagram height transitions animate and respect reduced motion', async () => {
      await render(tall);
      const body = section.locator(':scope > div').last();
      const originalHeight = await body.evaluate(el => el.getBoundingClientRect().height);
      await toggle.click();
      await page.waitForFunction(() => document.querySelector('section[aria-label="Mermaid diagram"]').lastElementChild.getAnimations().some(a => a.playState === 'running'));
      const shrinking = await body.evaluate(el => el.getBoundingClientRect().height);
      assert.ok(shrinking > 400 && shrinking < originalHeight, 'Source switch must interpolate height instead of jumping');
      await page.waitForTimeout(300);
      assert.ok(await body.evaluate(el => el.getBoundingClientRect().height < 500));
      const retainedId = await section.locator('svg[role="img"]').getAttribute('id');
      await toggle.click();
      await section.locator('svg[role="img"]').waitFor();
      assert.equal(await section.locator('svg[role="img"]').getAttribute('id'), retainedId, 'Source toggle must retain SVG, not restart rendering');
      assert.equal(await section.getByText('Rendering diagram…', { exact: true }).count(), 0, 'No loading-placeholder collapse on return to diagram');
      await page.waitForFunction(() => document.querySelector('section[aria-label="Mermaid diagram"]').lastElementChild.getAnimations().some(a => a.playState === 'running'));
      await page.waitForTimeout(300);
      assert.ok(await body.evaluate(el => el.getBoundingClientRect().height > 2000));
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await toggle.click();
      await page.waitForTimeout(50);
      assert.equal(await body.evaluate(el => el.getAnimations().length), 0);
      assert.ok(await body.evaluate(el => el.getBoundingClientRect().height < 500));
      await page.emulateMedia({ reducedMotion: 'no-preference' });
      return { originalHeight, shrinking, reducedMotion: 'no animation' };
    });

    await check('expanded tall diagram scrolls; Escape restores trigger focus', async () => {
      await render(tall);
      const trigger = page.getByRole('button', { name: 'Expand diagram', exact: true });
      await trigger.click();
      const dialog = page.getByRole('dialog');
      const expanded = dialog.getByRole('region');
      await dialog.locator('svg[role="img"]').waitFor();
      const dimensions = await expanded.evaluate(el => ({ height: el.clientHeight, scroll: el.scrollHeight, overscroll: getComputedStyle(el).overscrollBehavior }));
      assert.ok(dimensions.scroll > dimensions.height && dimensions.height > 0);
      const parentBefore = await parent.evaluate(el => el.scrollTop);
      await wheel(expanded, 0, 300);
      assert.ok(await expanded.evaluate(el => el.scrollTop > 0));
      assert.equal(await parent.evaluate(el => el.scrollTop), parentBefore);
      await page.keyboard.press('Escape');
      await dialog.waitFor({ state: 'hidden' });
      await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Expand diagram');
      return dimensions;
    });
    await check('temporary Mermaid measurement is isolated from page layout', async () => {
      const stages = await page.evaluate(() => window.measurementStages);
      assert.ok(stages.length > 0, 'Observed real Mermaid measurement stages');
      for (const stage of stages) assert.deepEqual(stage, { position: 'fixed', height: 0, visibility: 'hidden', overflow: 'hidden' });
      assert.equal(await page.locator('[class*="measurementStage"]').count(), 0, 'Measurement stages must be cleaned up');
      return { isolatedRenders: stages.length };
    });
    await page.close();
  }
  assert.deepEqual(errors, [], 'Uncaught browser errors');
  if (failures) process.exitCode = 1;
} catch (error) {
  console.error(error);
  process.exitCode = 1;
} finally {
  await browser?.close();
  await server?.close();
  clearTimeout(deadline);
}
