#!/usr/bin/env node
/** Bounded local smoke test; fixtures are used only for the downloads API, not the recorded chat. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require(path.resolve("dist/browser-tools/node_modules/playwright"));
const origin = "http://127.0.0.1:4175";
const server = spawn(process.execPath, [
  path.resolve("spa/node_modules/vite/bin/vite.js"), "preview", "--host", "127.0.0.1", "--port", "4175", "--strictPort",
], { cwd: path.resolve("spa"), stdio: ["ignore", "pipe", "pipe"] });
let serverLog = "";
server.stdout.on("data", (chunk) => { serverLog += chunk; });
server.stderr.on("data", (chunk) => { serverLog += chunk; });
let browser;
try {
  let ready = false;
  for (let attempt = 0; attempt < 30; attempt++) {
    if (server.exitCode !== null) throw new Error(`Preview failed: ${serverLog}`);
    try { ready = (await fetch(origin)).ok; } catch { /* Wait for the bounded child process. */ }
    if (ready) break;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  assert.ok(ready, "Local Vite preview did not start");
  const metadataResponse = await fetch("https://api.innomightlabs.com/downloads/plugins/wordpress-ai-search", { signal: AbortSignal.timeout(20000) });
  assert.ok(metadataResponse.ok, "Published plugin metadata is unavailable");
  const metadata = await metadataResponse.json();
  metadata.readme_markdown = (await readFile("dist/downloads/wordpress-ai-search/README.md", "utf8"))
    .replaceAll("https://innomightlabs.com/plugins/wordpress-ai-search/", `${origin}/plugins/wordpress-ai-search/`);
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  await page.route("**/downloads/plugins/wordpress-ai-search", async (route) => {
    if (route.request().resourceType() === "fetch") {
      await route.fulfill({ json: metadata });
    } else {
      await route.continue();
    }
  });
  await page.goto(`${origin}/downloads/plugins/wordpress-ai-search`, { waitUntil: "networkidle", timeout: 30000 });
  const videos = page.locator("video");
  assert.equal(await videos.count(), 2);
  const playbacks = [];
  for (const [index, expected] of [[0, { min: 50, max: 65, captions: 6 }], [1, { min: 120, max: 175, captions: 8 }]]) {
    const video = videos.nth(index);
    await video.scrollIntoViewIfNeeded();
    assert.equal(await video.getAttribute("autoplay"), null);
    assert.equal(await video.getAttribute("preload"), "none");
    await video.evaluate(async (element) => { element.muted = true; await element.play(); });
    await page.waitForFunction((position) => {
      const video = document.querySelectorAll("video")[position];
      return video.currentTime > 0.4 && !video.paused && video.videoWidth === 1440;
    }, index, { timeout: 15000 });
    await page.waitForFunction((position) => document.querySelectorAll("video")[position].querySelector("track").readyState === 2, index, { timeout: 10000 });
    const playback = await video.evaluate((element) => ({
      duration: element.duration, width: element.videoWidth, height: element.videoHeight,
      captions: element.textTracks[0].cues.length, currentTime: element.currentTime,
    }));
    assert.ok(playback.duration > expected.min && playback.duration < expected.max, `video ${index} duration ${playback.duration}`);
    assert.ok(playback.captions >= expected.captions, `video ${index} captions ${playback.captions}`);
    await video.evaluate((element) => { element.pause(); });
    playbacks.push(playback);
  }
  const video = videos.first();
  const images = page.locator('article img[src*="/plugins/wordpress-ai-search/"]');
  assert.ok(await images.count() >= 3);
  for (const image of await images.all()) {
    await image.scrollIntoViewIfNeeded();
    await image.evaluate((element) => element.decode());
    assert.ok(await image.evaluate((element) => element.naturalWidth > 0));
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await video.scrollIntoViewIfNeeded();
  assert.ok(await video.evaluate((element) => element.getBoundingClientRect().width <= innerWidth));
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  console.log(JSON.stringify({ playbacks, screenshots: await images.count(), mobileOverflow: false, apiFixture: "published metadata + local README", chatRecording: "real live responses; not mocked" }, null, 2));
} finally {
  if (browser) await browser.close();
  server.kill("SIGTERM");
}
