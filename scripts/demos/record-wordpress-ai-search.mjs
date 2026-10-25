#!/usr/bin/env node
/** Run from the repository root after installing Playwright into dist/browser-tools. */
import { copyFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(path.resolve("dist/browser-tools/node_modules/playwright"));
const output = path.resolve("dist/ai-search-recording");
const assets = path.resolve("plugins/wordpress/innomight-ai-search/.wordpress-org");
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 1080 },
  deviceScaleFactor: 1,
  colorScheme: "light",
  locale: "en-GB",
  recordVideo: { dir: output, size: { width: 1440, height: 1080 } },
});
const page = await context.newPage();
const recordingStarted = Date.now();
const moments = [];
const requests = [];
const mark = (label) => {
  const moment = { seconds: (Date.now() - recordingStarted) / 1000, label };
  moments.push(moment);
  console.log(`${moment.seconds.toFixed(1)}s ${label}`);
};
page.on("response", (response) => {
  if (response.url().includes("/innomight-search/v1/chat")) {
    requests.push({ status: response.status(), contentType: response.headers()["content-type"] });
  }
});
const pause = (ms) => page.waitForTimeout(ms);
const widget = page.locator("[data-innomight-search]");
const input = widget.getByRole("textbox");
const answers = widget.locator(".is-bot .innomight-search__body");
async function completedAnswer() {
  await page.waitForFunction(() => {
    const root = document.querySelector("[data-innomight-search]");
    return root && !root.querySelector("form input").disabled &&
      root.querySelectorAll(".is-bot .innomight-search__body").length > 0;
  }, null, { timeout: 150000 });
  const error = widget.locator(".innomight-search__error");
  if (await error.count()) throw new Error(`Live widget failed: ${await error.last().innerText()}`);
  const answer = await answers.last().innerText();
  if (answer.trim().length < 30) throw new Error("Live answer was unexpectedly empty/short");
  return answer;
}

let success = false;
try {
  await page.goto("https://preview.varunshrivastava.in/?s=AI", { waitUntil: "networkidle", timeout: 45000 });
  await page.evaluate(() => document.fonts.ready);
  mark("Start with normal WordPress search results");
  await pause(1800);
  const search = page.locator("form.wp-block-search");
  await search.locator("input[name=s]").fill("");
  await search.locator("input[name=s]").pressSequentially("memory", { delay: 180 });
  await pause(700);
  await Promise.all([
    page.waitForURL("**/?s=memory", { timeout: 45000 }),
    search.getByRole("button", { name: "Search", exact: true }).click(),
  ]);
  await widget.waitFor();
  await page.evaluate(() => document.fonts.ready);
  await pause(1800);
  await page.screenshot({ path: path.join(output, "screenshot-4.png") });
  mark("Search memory; normal results and follow-up chat appear together");
  await pause(1800);
  await input.click();
  await input.pressSequentially("Find posts about LLMs. Include the titles and links.", { delay: 70 });
  await pause(800);
  await widget.getByRole("button", { name: "Send", exact: true }).click();
  mark("Ask the agent to find posts about LLMs with titles and links");
  const firstAnswer = await completedAnswer();
  mark("Read the real AI answer and its article links");
  await widget.scrollIntoViewIfNeeded();
  await pause(3500);
  await widget.screenshot({ path: path.join(output, "screenshot-5.png") });
  await input.click();
  await input.pressSequentially("Which one is specifically about context memory, and when was it published?", { delay: 65 });
  await pause(1000);
  await widget.getByRole("button", { name: "Send", exact: true }).click();
  mark("Ask a follow-up in the same conversation");
  const followUp = await completedAnswer();
  mark("Read the contextual follow-up answer");
  await widget.scrollIntoViewIfNeeded();
  await pause(5000);
  await widget.screenshot({ path: path.join(output, "screenshot-6.png") });
  const linkedPost = widget.locator(".is-bot a[href]").filter({ hasText: /context|memory/i }).first();
  if (await linkedPost.count()) {
    const href = await linkedPost.getAttribute("href");
    const url = new URL(href, page.url());
    if (["preview.varunshrivastava.in", "varunshrivastava.in"].includes(url.hostname)) {
      await linkedPost.click();
      await page.waitForLoadState("domcontentloaded");
      mark("Open the linked article to read the source");
      await pause(4500);
    }
  }
  mark("End of walkthrough");
  await writeFile(path.join(output, "capture.json"), JSON.stringify({
    source: "https://preview.varunshrivastava.in/", capturedAt: new Date().toISOString(),
    viewport: { width: 1440, height: 1080 }, moments, requests, firstAnswer, followUp,
  }, null, 2) + "\n");
  const timestamp = (seconds) => {
    const ms = Math.round(seconds * 1000);
    return `${String(Math.floor(ms / 3600000)).padStart(2, "0")}:${String(Math.floor(ms / 60000) % 60).padStart(2, "0")}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}.${String(ms % 1000).padStart(3, "0")}`;
  };
  const captions = moments.slice(0, -1).map((moment, index) =>
    `${timestamp(moment.seconds)} --> ${timestamp(moments[index + 1].seconds)}\n${moment.label}\n`,
  );
  await writeFile(path.join(assets, "demo.vtt"), `WEBVTT\n\n${captions.join("\n")}`);
  for (const filename of ["screenshot-4.png", "screenshot-5.png", "screenshot-6.png"]) {
    await copyFile(path.join(output, filename), path.join(assets, filename));
  }
  success = true;
} catch (error) {
  await page.screenshot({ path: path.join(output, "failure.png") }).catch(() => {});
  console.error(error.message);
  process.exitCode = 1;
} finally {
  const video = page.video();
  await context.close();
  if (video) await video.saveAs(path.join(output, success ? "walkthrough.webm" : "failed-attempt.webm"));
  await browser.close();
}
