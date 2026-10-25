# WordPress AI Search: real browser walkthrough

The recording uses Playwright Chromium against `https://preview.varunshrivastava.in/` as an anonymous visitor. It performs two real AI requests, consumes the configured agent's allowance, and stores a conversation on that service. It does not intercept requests, manufacture responses, log in, or change site settings.

## Reproduce

Run from the repository root:

```sh
npm install --prefix dist/browser-tools --no-save --package-lock=false playwright
node dist/browser-tools/node_modules/playwright/cli.js install chromium
node scripts/demos/record-wordpress-ai-search.mjs
ffmpeg -hide_banner -loglevel error -y \
  -i dist/ai-search-recording/walkthrough.webm \
  -c:v libx264 -preset slow -crf 26 -pix_fmt yuv420p \
  -movflags +faststart -an \
  plugins/wordpress/innomight-ai-search/.wordpress-org/demo.mp4
```

Install FFmpeg separately if unavailable. No dependency is added to the SPA or shipped WordPress plugin. Playwright and raw recordings remain in ignored `dist/` directories. The script replaces its own generated `screenshot-4.png` through `screenshot-6.png` and `demo.vtt`, not the original screenshots 1–3.

The script records at 1440×1080, searches for `memory`, asks for LLM posts with titles/links, asks which post covers context memory and its publication date, then opens the source article. It captures screenshots only after both requests complete without widget errors. A failed attempt is saved under `dist/ai-search-recording/failed-attempt.webm`, not promoted to demo media. Successful raw video and capture timing/answers are stored alongside it for inspection. No cookies or browser storage state are exported.

## Published assets

Canonical media live in `plugins/wordpress/innomight-ai-search/.wordpress-org/`:

- `screenshot-4.png`: search results with the embedded chat.
- `screenshot-5.png`: live post-discovery answer and links.
- `screenshot-6.png`: contextual follow-up answer.
- `demo.mp4`: silent H.264 browser recording; encoded for compatibility with no time cuts or mocked results. The current recording is about 54 seconds and 1.1 MB.
- `demo.vtt`: English action captions generated from the capture timestamps. These describe the interaction, not spoken audio.

The SPA public-pages build copies these five files to `/plugins/wordpress-ai-search/`. The details page uses a native, non-autoplay video player with captions. The plugin README links the recording and screenshots. `.wordpress-org` media are excluded from the downloadable plugin ZIP, so the installed plugin stays small.

Deploy the SPA media before publishing the updated README/ZIP to the download catalogue or submitting the new screenshot captions to WordPress.org. Screenshots 4–6 belong in the WordPress.org SVN `assets/` directory; the video itself is hosted on the Innomight site, not submitted as a WordPress.org screenshot.

## Second demo: Microservices on BeMyAficionado

`record-wordpress-ai-search-microservices.mjs` records the live site `https://www.bemyaficionado.com/` the same way (run from the repository root after the install step above; encode `dist/ai-search-recording-microservices/walkthrough.webm` with the same ffmpeg command, writing `demo-microservices.mp4`). It types `Microservices` into the home page's search, asks in which order to read all the matching posts, asks for a summary of "How to Architect a Solution", asks whether there is anything newer about distributed systems, then opens the linked article. Between answers it scrolls the chat the way a reader would. It writes `demo-microservices.vtt` and `screenshot-7.png` through `screenshot-9.png`. The recording is about two and a half minutes, 4.7 MB. Answer time varies with the live agent (the first answer took 39 to 57 seconds across runs) and is not cut.

The summary works because this site's agent has the WordPress Search skill's `read_post` action, which returns a post's full text. Each run sends four real requests to that agent.

The plugin page shows both videos (`demo` and `demo-microservices`); the Vite plugin copies all ten media files.

## What the demo does and does not establish

The captured posts response and follow-up use the live SSE endpoint and real rendered answers. The configured search skill returns titles and metadata. A preliminary summary attempt correctly declined because it had no article text; that attempt is not presented as a successful summarization demo. Full-article summaries need a content-reading tool or a knowledge base; the second demo has one. No agent configuration was changed to make this recording.

Verify build output and playback before release:

```sh
cd spa
yarn test scripts/vite-plugin-public-pages.test.ts src/pages/PluginDetailsPage.test.tsx
yarn build
```

After packaging the plugin and building the SPA, run `node scripts/demos/verify-wordpress-ai-search-media.mjs` from the repository root. It starts a bounded local Vite preview child process and uses Playwright to check video metadata/caption loading, native playback, screenshot requests and mobile overflow. Only the downloads API is fixture-backed (published metadata plus the new local README); the original WordPress chat recording is not mocked. The source plugin screenshots remain the single source of truth; do not copy them into `spa/public/`.
