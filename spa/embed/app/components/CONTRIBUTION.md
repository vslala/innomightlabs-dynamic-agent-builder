# Embed Components Guide

These components render the iframe's visitor UI. `App` and `useChat` supply session/chat state; only guest entry in `LoginPanel` has its own focused API interaction. Do not import dashboard auth or attach active-account headers here.

- `MessageList` consumes `buildChatStreamRenderPlan` from the shared source package; messages precede streaming text, pending form and typing/tool feedback. Stable message IDs are keys.
- Follow new text only while near the bottom (48px threshold); user messages resume following. Scroll the list itself, not `scrollIntoView`, which can move the embedding host page. Keep the jump-to-latest affordance and live-log accessibility.
- `Markdown` uses ReactMarkdown + GFM and safe external-link attributes. It intentionally omits a syntax highlighter to avoid inflating customer-site bundles; don't copy the classic widget's HTML-rendering stack here.
- Mermaid uses the shared UI `MermaidMarkdownPre` adapter and CSS module. Preserve `MessageList`'s live `isStreaming` flag: even closed fences wait for response completion. Keep Mermaid lazy ESM outside the app IIFE, resolved relative to the captured CDN `app.js` URL; publish the full `embed/mermaid/` output. Do not import SPA global styles. See [Mermaid chat diagrams](../../../../docs/LLD-mermaid-chat-diagrams.md); isolated stylesheet/component browser checks are not deployed-iframe verification.
- `FormCard` uses `../forms.ts` for choice/answer/submission semantics. Submitted user messages reuse the dashboard's `submittedFormParser` when no display override exists. Preserve actual submission text while showing a compact label.
- `Composer`, `Header`, `ConversationList` and `LoginPanel` retain keyboard, focus, disabled/busy and error behavior. Guest entry must remain cancellable and respect backend availability, not silently replace failed entry with a session.

CSS belongs in `../styles.css` with `ie-*` names and iframe-local variables. Loader launcher/panel CSS belongs elsewhere; avoid importing SPA global CSS or putting static layout in inline styles.

From `spa/`: `yarn test embed/app` runs nearby form/guest-entry and helper coverage (tests live one directory up). For visual changes verify focus, mobile sizing, history, Markdown, pending forms and scroll manually; build with `yarn build:embed`. See [embed verification](../../CONTRIBUTION.md).
