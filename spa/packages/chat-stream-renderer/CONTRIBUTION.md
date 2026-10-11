# Shared Chat Stream Planner Guide

Despite its name, this package currently exports a pure render-plan helper, not a React component, SSE parser or Markdown renderer. `src/index.tsx` is the sole source; dashboard, classic Preact widget and embed app import source directly.

## Contract

`buildChatStreamRenderPlan<TMessage>()` returns a discriminated list:

1. Existing messages in input order, with caller-provided key and original index/reference.
2. A `streaming` item only for truthy streaming content.
3. An `extra` item when `hasExtraNode` is true (the caller renders forms or other extras).
4. A `typing` item only when loading, no streaming content and `showTypingIndicator` (default true).

Extra content does not suppress typing. Whitespace streaming content is still truthy. Reserved keys are `streaming`, `extra` and `typing`; callers must choose stable message keys without collisions. Do not mutate message arrays or introduce transport/session state into planning.

Each consumer owns its DOM framework, tool feedback, scroll behavior, sanitization/Markdown and CSS. The helper owns none of those; adding React runtime imports would also affect the Preact caller. Although package metadata declares React peers, the current implementation has no runtime React dependency.

## Verification

From this directory, `yarn build` is `tsc -p tsconfig.json`, emitting JS and declarations into `dist`; no test/lint scripts exist in this package. `package.json` exposes `dist/index.js` and `dist/index.d.ts`, so preserve export compatibility as well as direct-source consumers.

No dedicated render-plan tests were found. Add pure behavior tests (order, keys, optional extra, streaming/loading combinations and nonmutation) and run them through SPA Vitest from `spa/` with `yarn test packages/chat-stream-renderer` once added. Then verify the SPA and embed consumers with `yarn test`, `yarn build`, `yarn build:embed` from `spa/` and the classic widget with `yarn build` from `spa/widget/`. These are configuration-verified commands, not executed validation results.
