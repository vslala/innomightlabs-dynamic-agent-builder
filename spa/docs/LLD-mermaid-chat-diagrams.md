# Mermaid chat diagrams

| Field | Value |
| --- | --- |
| Status | ✅ Implemented |
| Owner | InnomightLabs Engineering — UI / embed |
| Last reviewed | 2026-10-18 |
| Scope | Dashboard and iframe-widget Markdown; shared UI and build runtime |
| Depends on | Mermaid 12.2.0 (exact pin), ReactMarkdown + GFM, shared Button / Radix Dialog |
| Tracker | — |
| Replaces | — |

> **Summary:** Render fenced `mermaid` blocks as reusable, theme-aware diagram cards in dashboard and embed chat. Both consumers share the same UI, conservative validation and lazy, self-hosted official Mermaid runtime. Implementation is present locally; this status does not assert deployment or deployed-iframe verification.

## Implementation notes

- Deliberately wait for the **full streaming response** to finish, even when a fence has already closed. Full-response completion is chosen over early closed-fence rendering; there is no independent closed-fence detector.
- Local isolated component browser verification exercised the **actual component**: 23 checks with dashboard and embed stylesheets isolated from each other. It did **not** exercise a deployed host or iframe. See validation limits below.
- New implementation paths are plain code text here and in the wiki until available on `main`, avoiding premature repository links.

## Context, goals and non-goals

Agent answers previously exposed Mermaid as code. Provide readable static diagrams without shipping Mermaid in either initial application graph, duplicating renderers, or trusting agent-authored HTML/configuration. Preserve ordinary code rendering and readable source on failure. No backend/schema changes, editing, callbacks, arbitrary styling, external resources, or changes to the older `spa/widget/` are part of this design.

## Design and contracts

### Reusable UI

`spa/src/components/ui/mermaid-diagram.tsx` exposes:

```tsx
interface MermaidDiagramProps {
  source: string;
  pending?: boolean; // default false; caller owns stream completion
  className?: string;
  label?: string; // default "Mermaid diagram"
}

<MermaidDiagram source={source} pending={isStreaming} label="Order lifecycle" />
```

The card uses shared Button and Dialog controls for source toggle, copy and expansion. Source mode replaces the inline diagram directly below the toolbar rather than appending text beneath a potentially tall SVG; the source region is keyboard-focusable. The rendered diagram stays mounted but hidden while source is visible, so toggling back reuses the SVG without a loading-placeholder collapse or repeated Mermaid render. Pending cards show escaped source and completion status, disable expansion and do not mount the SVG renderer. Copy failure exposes selectable source. Completed diagrams have an accessible image label and keyboard-focusable scrolling region; expansion uses a separately rendered SVG with dialog title, description and Escape/focus behavior supplied by Radix.

`mermaid-diagram.module.css` owns the token-backed card, toolbar, source panel, viewport, focus ring, mobile spacing and bounded expanded dialog. ResizeObserver fits SVGs between 85% and 100% of intrinsic width: wide diagrams scroll rather than shrinking to illegibility. Inline diagrams keep their full vertical height in message flow and use normal scroll chaining, so vertical wheel/touch input reaches the conversation. Only the expanded viewport contains overscroll. A content ResizeObserver animates the inline body's height over 220ms with ease-out during source/diagram changes and asynchronous SVG insertion. Interrupted transitions retarget from the visible height; reduced-motion users get immediate changes. The animated wrapper maintains an explicit measured height before content changes and clips without becoming another scroll container, preventing a transient auto-height collapse before ResizeObserver runs. Source scrolling also chains to the conversation at its bounds. This is fitting/scrolling, not a zoom/pan implementation. The module is shared with embed; do not copy its rules into dashboard-global or `ie-*` CSS.

### Markdown and streaming

`MermaidMarkdownPre` in `mermaid-markdown.tsx` replaces the **whole `pre` block**, so cards and controls are never nested inside a code-block wrapper. It inspects ReactMarkdown's AST for the exact, case-sensitive `language-mermaid` class, joins text children and removes one trailing newline. Other fences, inline code and indented code retain their existing rendering; fence metadata is not a UI configuration channel.

- Dashboard `markdown-renderer.tsx` and embed `app/components/Markdown.tsx` install the same `pre` adapter with `pending={isStreaming}`; both default `isStreaming` to false.
- Dashboard `ChatStreamRenderer.tsx` and embed `MessageList.tsx` mark live streaming text with `isStreaming`; completed/history content uses the default rendering path.
- While streaming, even a syntactically complete fenced diagram remains source. After completion, render the final snapshot. This avoids partial parses, repeated layout and ambiguous fence completion; do not infer readiness merely from Markdown producing a code AST.
- Dashboard keeps its existing syntax highlighter for other languages. Embed deliberately has none.

### Runtime, themes and lifecycle safety

`renderMermaid(source, id, dark): Promise<string>` in `mermaid-runtime.ts` returns only the official runtime's strict-sanitized SVG; it never installs Mermaid's `bindFunctions`.

Use **official Mermaid 12.2.0** `look: 'neo'` with `redux-color` for light and `redux-dark-color` for dark, not hand-written palettes or agent-provided theme variables. Root `data-theme` is authoritative (`light` versus other values); absent that, follow `prefers-color-scheme`. Attribute/media observers trigger rerenders. Wait for `document.fonts?.ready`; system font and aligned sequence measurement fonts/sizes plus wrapping avoid layout/text clipping.

Mermaid initialization is global mutable state. One module-level promise queue serializes **initialize plus render**, including inline/expanded views and different themes. Queue rejection is consumed for subsequent jobs; a failed lazy import clears its cached promise so a later request can retry. Failed cards show escaped source rather than breaking the message. Each render receives a dedicated fixed, invisible, zero-height measurement stage styled by `mermaid-runtime.module.css`; its clipped, contained SVG layout cannot expand the page. The stage remains measurable and is removed in `finally`, including failed renders.

Every attempt combines a cleaned React `useId` with `crypto.randomUUID()` under a letter-prefixed ID, including StrictMode replays and expanded views. Runtime IDs must be CSS-safe and start with a letter. Effect cleanup marks results inactive, disconnects ResizeObserver and clears the host: old source/theme renders cannot overwrite the current view after changes or unmount. Already queued jobs are not cancelled, but stale results are ignored.

### Security boundary and conservative fallback

Validate before lazy loading: nonblank source, at most 30,000 characters; runtime also sets `maxTextSize: 30_000` and `maxEdges: 500`. Reject frontmatter and directives rather than stripping them. Reject interactive/link/style commands (including `classDef`), image/icon/resource attributes, URL schemes/protocol-relative URLs, CSS URL/import syntax, HTML, Markdown link/image syntax and backslashes that could conceal escaped resources. Command matching is position-sensitive so ordinary words such as “click”, “link” and “style” in labels remain usable.

Initialize with `securityLevel: 'strict'`, `startOnLoad: false`, `suppressErrorRendering: true`, and HTML labels disabled globally and for flowchart/class diagrams. Only SVG returned by that runtime crosses `innerHTML`; source always uses escaped React text. These are layered, deliberately conservative restrictions, not a promise to accept all valid Mermaid or a formal guarantee against every future Mermaid vulnerability. Benign diagrams containing blocked syntax, invalid syntax, excessive input, import/layout failures all fall back to source with “Diagram unavailable”. Repository documentation's general `classDef`/HTML-label examples are **not** automatically safe chat input.

### Self-hosted lazy ESM, separate from widget IIFE

`spa/scripts/mermaid-renderer.ts` re-exports official Mermaid. `vite-plugin-mermaid-runtime.ts` builds it in `closeBundle` as a separate ESM graph, with fixed `renderer.js`, hashed relative chunks/assets, `base: './'` and `preserveEntrySignatures: 'strict'` to retain the default export consumed by dynamic import.

| Host | Build / resolution |
| --- | --- |
| Dashboard | `spa/vite.config.ts` installs `mermaidRuntimePlugin()` → `dist/mermaid/renderer.js`; production import resolves against Vite `BASE_URL` and `document.baseURI`, not the chat route |
| Embed | `spa/embed/vite.app.config.ts` installs `mermaidRuntimePlugin('embed/mermaid')` and defines `MERMAID_EMBED`; output is `embed/dist/embed/mermaid/renderer.js` beside `embed/app.js` |
| Development | Vite serves `scripts/mermaid-renderer.ts` under `BASE_URL` |

The widget stays a classic IIFE with `inlineDynamicImports`; Mermaid must not become a normal value import in that graph. The host dynamically imports the computed URL with `@vite-ignore` only for a non-pending diagram. Capture `document.currentScript.src` synchronously when widget `app.js` executes, then resolve `mermaid/renderer.js` relative to its CDN URL later. Missing script location fails closed; never fall back to the API iframe origin. No third-party runtime CDN is used.

## Implementation map

All paths below are relative to `spa/`.

| Area | Files | Responsibility |
| --- | --- | --- |
| Shared UI | `src/components/ui/mermaid-diagram.tsx`, `mermaid-diagram.module.css`, `index.ts` | Public card API, lifecycle, accessibility, sizing and export |
| Adapter / runtime | `src/components/ui/mermaid-markdown.tsx`, `mermaid-runtime.ts` | Fence dispatch, validation, queue, themes and lazy import |
| Dashboard | `src/components/ui/markdown-renderer.tsx`, `src/components/chat/ChatStreamRenderer.tsx` | Markdown integration and live-stream flag |
| Embed | `embed/app/components/Markdown.tsx`, `MessageList.tsx` | Lightweight Markdown integration and live-stream flag |
| Build | `scripts/mermaid-renderer.ts`, `scripts/vite-plugin-mermaid-runtime.ts`, `vite.config.ts`, `embed/vite.app.config.ts`, `package.json`, `yarn.lock` | Official dependency and separate self-hosted ESM output |
| Tests | `src/components/ui/mermaid-runtime.test.ts`, `mermaid-markdown.test.tsx`, `scripts/mermaid-runtime-build.test.ts` | Runtime policy/queue/URLs, both Markdown paths, lazy build boundary/default export |

## Rollout and compatibility

Publish the entire generated Mermaid directory and its chunks/assets alongside each corresponding app build, not only `app.js`/`app.css`. Dashboard and widget have separate delivery paths. In `terraform/widget_cdn.tf`, the `embed_build_upload` source trigger hashes all shared UI files (`spa/src/components/ui/**/*`), `spa/src/lib/utils.ts` and both renderer scripts (`spa/scripts/mermaid-renderer.ts`, `spa/scripts/vite-plugin-mermaid-runtime.ts`), alongside existing embed/build inputs, so shared component and runtime changes trigger a rebuild/upload. Deployment and deployed-host behavior remain unverified. Verify deployed asset URLs, JavaScript MIME types, cross-origin module CORS and CSP permissions for the actual iframe/CDN setup; self-hosting alone does not prove these work.

Requires a modern browser with dynamic ESM imports, DOM/SVG layout, ResizeObserver, MutationObserver, media-query change listeners and `crypto.randomUUID()` (secure context, normally HTTPS or localhost). Clipboard writing additionally needs permission/secure-context support; its failure has a manual-copy fallback. Font readiness is awaited when available. This is browser rendering, not server-generated SVG, and there is no legacy-browser/polyfill promise.

## Validation

Final validation results on 2026-10-18:

- From `spa/`: `yarn test src/components/ui/mermaid-runtime.test.ts src/components/ui/mermaid-markdown.test.tsx scripts/mermaid-runtime-build.test.ts` — **69 passed**, including a real separate-runtime build and host graph checks.
- `yarn test` — **493 passed, 1 failed** across 54 files. Known unrelated failure: `src/pages/dashboard/OverviewContent.test.tsx:53` expects `1.2K indexed vectors`; rendered text is `1.2k indexed vectors`. Left unchanged; the full suite is not green.
- `yarn build` and `yarn build:embed` — **passed** for both hosts.
- Focused ESLint — **passed** for all touched code.
- `yarn design:audit` — **completed with warnings only**, reflecting the pre-existing raw-control inventory; not proof of accessibility.
- `terraform fmt -check terraform/widget_cdn.tf` and `git diff --check` — **passed**.
- Runtime unit tests mock Mermaid; Markdown tests use actual components with static server markup (effects do not run). These do not independently prove browser SVG rendering or deployed iframe behavior.
- **23 local isolated component browser checks** exercised the actual component with each host's stylesheet isolated. These checks do not verify a deployed host, iframe/CDN/CSP behavior or cross-browser compatibility.

Both host builds passed; deployment verification remains outstanding. Before release, verify the real dashboard and iframe: lazy network loading, both themes, stream-to-final transition, multiple/wide diagrams, syntax/security fallback, copy, source, keyboard dialog behavior and mobile sizing.

## Alternatives and decisions

- **Early closed-fence rendering:** rejected in favor of full-response completion gating, which is simpler and avoids reparsing transient content.
- **Inline Mermaid / remote CDN:** rejected to keep initial bundles lean, preserve the widget IIFE and serve a pinned runtime from controlled assets.
- **Custom themes / loose HTML / callbacks:** rejected; official themes and static SVG with readable-source fallback are the supported contract.

## Related documentation

- [Experience Index](../wiki/Experience-Index.md)
- [Frontend Design System Hardening](../spa/docs/LLD-frontend-design-system-hardening.md)
- [Widget Guest Sessions](LLD-widget-guest-sessions.md)
- UI contribution guide: `spa/src/components/ui/CONTRIBUTION.md`.
- Embed components guide: `spa/embed/app/components/CONTRIBUTION.md`.
