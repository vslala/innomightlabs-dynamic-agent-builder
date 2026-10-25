#!/usr/bin/env node
/** Run from the repository root after installing Playwright into dist/browser-tools. */
import { copyFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(path.resolve("dist/browser-tools/node_modules/playwright"));
const output = path.resolve("dist/ai-search-recording-microservices");
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
const thread = widget.locator(".innomight-search__thread");
async function completedAnswer(previousAnswers) {
  await page.waitForFunction((previous) => {
    const root = document.querySelector("[data-innomight-search]");
    return root && !root.querySelector("form input").disabled &&
      root.querySelectorAll(".is-bot .innomight-search__body").length > previous;
  }, previousAnswers, { timeout: 150000 });
  await pause(1500); // let the streamed answer finish rendering
  const error = widget.locator(".innomight-search__error");
  if (await error.count()) throw new Error(`Live widget failed: ${await error.last().innerText()}`);
  const answer = await answers.last().innerText();
  if (answer.trim().length < 30) throw new Error("Live answer was unexpectedly empty/short");
  return answer;
}
/** Show the answer from its first line, then scroll down the way a reader would. */
async function readAnswer() {
  await widget.scrollIntoViewIfNeeded();
  await answers.last().evaluate((element) => element.scrollIntoView({ block: "start" }));
  await pause(2800);
  for (let step = 0; step < 6; step++) {
    const moved = await thread.evaluate((element) => {
      const before = element.scrollTop;
      element.scrollBy({ top: Math.round(element.clientHeight * 0.55), behavior: "smooth" });
      return before;
    });
    await pause(2200);
    if (await thread.evaluate((element, before) => element.scrollTop === before, moved)) break;
  }
}

let success = false;
const answersByQuestion = [];
async function ask(question, label, readLabel, { typingDelay = 65, readPause = 1500, screenshot } = {}) {
  await input.click();
  await input.pressSequentially(question, { delay: typingDelay });
  await pause(900);
  await widget.getByRole("button", { name: "Send", exact: true }).click();
  mark(label);
  const answer = await completedAnswer(answersByQuestion.length);
  answersByQuestion.push({ question, answer });
  mark(readLabel);
  await answers.last().evaluate((element) => element.scrollIntoView({ block: "start" }));
  await pause(700);
  if (screenshot) await widget.screenshot({ path: path.join(output, screenshot) });
  await readAnswer();
  await pause(readPause);
}
try {
  await page.goto("https://www.bemyaficionado.com/", { waitUntil: "networkidle", timeout: 45000 });
  await page.evaluate(() => document.fonts.ready);
  mark("Start on the BeMyAficionado blog");
  await pause(1800);
  const query = page.locator("form[data-bma-ask-form] input[name=s]");
  await query.click();
  await query.pressSequentially("Microservices", { delay: 150 });
  await pause(700);
  await Promise.all([
    page.waitForURL("**/?s=Microservices", { timeout: 45000 }),
    query.press("Enter"),
  ]);
  await widget.waitFor();
  await page.evaluate(() => document.fonts.ready);
  await pause(2200);
  await page.screenshot({ path: path.join(output, "screenshot-7.png") });
  mark("Search Microservices: every matching article is listed, with the follow-up chat above");
  await pause(2200);
  await ask(
    "In which order should I read all these posts?",
    "Ask which order to read the whole Microservices series in",
    "Read the suggested reading order",
    { screenshot: "screenshot-8.png" },
  );
  await ask(
    'Could you summarize the article "How to Architect a Solution"?',
    "Ask for a summary of one article",
    "Read the summary of the full article",
    { screenshot: "screenshot-9.png" },
  );
  await ask(
    "Is there anything newer on this site about distributed systems?",
    "Ask a follow-up: is there anything newer on the wider topic?",
    "Read the newer posts it found",
    { readPause: 2500 },
  );
  const linkedPost = widget.locator(".is-bot a[href]").filter({ hasText: /Forward Retry/i }).first();
  if (await linkedPost.count()) {
    const url = new URL(await linkedPost.getAttribute("href"), page.url());
    if (url.hostname.endsWith("bemyaficionado.com")) {
      await linkedPost.click();
      await page.waitForLoadState("domcontentloaded");
      mark("Open the linked article to read the source");
      await pause(4500);
    }
  }
  mark("End of walkthrough");
  await writeFile(path.join(output, "capture.json"), JSON.stringify({
    source: "https://www.bemyaficionado.com/", capturedAt: new Date().toISOString(),
    viewport: { width: 1440, height: 1080 }, moments, requests, answers: answersByQuestion,
  }, null, 2) + "\n");
  const timestamp = (seconds) => {
    const ms = Math.round(seconds * 1000);
    return `${String(Math.floor(ms / 3600000)).padStart(2, "0")}:${String(Math.floor(ms / 60000) % 60).padStart(2, "0")}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}.${String(ms % 1000).padStart(3, "0")}`;
  };
  const captions = moments.slice(0, -1).map((moment, index) =>
    `${timestamp(moment.seconds)} --> ${timestamp(moments[index + 1].seconds)}\n${moment.label}\n`,
  );
  await writeFile(path.join(assets, "demo-microservices.vtt"), `WEBVTT\n\n${captions.join("\n")}`);
  for (const filename of ["screenshot-7.png", "screenshot-8.png", "screenshot-9.png"]) {
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
