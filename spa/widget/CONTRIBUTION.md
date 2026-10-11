# Classic Widget Guide

`widget/` is the older Preact host-page `widget.js`, Google sign-in only. It is not `../embed/`'s React iframe app: its DOM, CSS and storage live on the customer's origin.

## Layout and contracts

- `src/index.ts` publishes `window.InnomightChat.init/destroy/open/close` and prevents multiple active containers. Keep its public API and `WidgetConfig` compatibility.
- `src/api.ts` configures API URL/public key and maps snake_case `/widget/*` responses to local types. Requests use `X-API-Key` plus the visitor bearer, never dashboard auth/account headers.
- Google sign-in sends `opener_origin`; `Widget.tsx` verifies callback API origin and popup source, then redeems a one-time code. Unlike embed session management, this client does not implement rotating refresh sessions or guest entry.
- `src/storage.ts` stores visitor token/info/current conversation in host localStorage, tolerating storage failures. JWT decoding is an expiry hint only, not verification. Do not claim iframe isolation for these tokens.
- `sendMessage()` yields line-based SSE JSON, skips malformed lines, stops on `[DONE]` and releases the reader. It does not offer dashboard turn reattachment/stop or embed's block-parser behavior.
- `ChatStreamRenderer` reuses the shared render-plan helper but owns Preact nodes. `MarkdownRenderer` uses marked/highlight.js then DOMPurify before HTML insertion; keep sanitization after rendering.

## CSS and verification

`src/styles.ts` injects a document-head stylesheet with `innomight-*` selectors and theme variables. These styles are not Shadow DOM-isolated: keep selectors scoped, and check collisions on customer pages. Do not borrow iframe `ie-*` or SPA page CSS.

From `spa/widget/`, `package.json` defines `yarn build` (Rollup production), `yarn build:analyze` (same build with ANALYZE set) and `yarn dev` (watch). The current Rollup config has no analyzer plugin; don't promise a bundle report. Output is the IIFE `dist/widget.js`; declaration generation is disabled by Rollup despite the package's types field.

There is no package test/lint script. Use manual fixtures in `test/` for popup sign-in, host CSS, storage failures, forms, streaming and destroy/reinit; inspect fixture assumptions before use. Shared logic regressions can use SPA Vitest (`yarn test` from `spa/`), but there are no adjacent widget unit tests established here. Commands are configuration-verified, not claimed successful runs.
