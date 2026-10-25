# Chat Components Contribution Guide

## Purpose and layout

These are dashboard/builder chat surfaces. They do not own the entire SSE lifecycle, persistence, or turn cancellation; consuming pages and services supply the transcript, stream state, and callbacks. The embeddable widget lives in `spa/embed/`.

- `ChatStreamRenderer.tsx`: message/stream/activity presentation using `buildChatStreamRenderPlan` from `packages/chat-stream-renderer/src`.
- `ChatComposer.tsx` and module CSS: controlled textarea, attachment/document/image/debug actions, send/stop UI.
- `AttachmentChip`, `TokenUsageIndicator`: attachment and usage display.
- `DocumentChip`: a conversation document (PDF, Word…) with its reading status and a remove button. The composer's `onAttachDocuments` opens the picker; the page owns the documents through `useConversationDocuments`.
- `ToolActivityCard`, `ToolActivitySummary`, `toolActivityFormat`: detailed versus compact tool display.
- `IlaWorking`, `ilaStatus`, `useHeldLabel`: Ila's live status line. `ilaStatus` words the tool she is running (from its name and arguments, never a page id) or "Thinking" between tools, and nothing once the turn ends; `useHeldLabel` keeps each line up long enough to read (`MIN_SHOWN_MS`). It is one line in the widget's "current tool, then gone" manner, styled like ChatGPT and Claude, not a list; her tools are never listed (`showsToolActivity`). A new Ila tool gets a phrase in `TOOL_PHRASES`; one without falls back to "Working on it".
- `ChatFormRenderer`, `SubmittedFormMessage`, `submittedFormParser`: interactive chat questions and saved answer presentation.
- `InlineCanvasCard`, `CanvasSidePanel`, `CanvasPlaceholder`: artifact previews and expanded canvas.
- `ConnectAccountCard`: popup connection prompt and fallback link.

## Flow and extension

A parent updates `messages`, `streamingContent`, tool activities, and status. `ChatStreamRenderer` builds a shared render plan, then renders Markdown, attachments, images, canvases, submitted forms, and extra nodes. Change shared ordering/deduplication rules in the shared renderer package rather than duplicating them here; verify other renderer consumers too.

The composer receives `value`, `onChange`, and `onSubmit`. Enter without Shift invokes `onSubmit`; Shift+Enter leaves a newline. The parent must guard submission validity and running-turn state: disabled button logic is not a universal keyboard submission guard. During submission, `stopAction` replaces the send action with stop; the callback performs cancellation elsewhere. Textarea height is measured dynamically and capped at 160px.

Chat forms submit trimmed, nonempty `{ field_id, label, value }` answers, not the `Record<string, FormValue>` used by settings `SchemaForm`. Choice checkboxes can encode multiple choices as comma-separated text. Preserve this distinction; do not assume upload/key-value settings field support here.

Canvases fetch authenticated raw HTML through `useArtifactHtml`. Inline previews wait for IntersectionObserver visibility; expanded panels fetch immediately. Both use `srcDoc`, `sandbox="allow-scripts"`, `referrerPolicy="no-referrer"`, and a title. Do not add same-origin privileges or inject artifact HTML into the SPA DOM. Image loading uses authenticated fetch for relative/API-origin URLs and revokes created object URLs on cleanup.

`ConnectAccountCard` starts connection through the builder service, processes popup messages with `connectOutcome`, and offers a new-tab fallback when blocked. Keep message validation in that helper; the manual “I've signed in” callback is not proof of backend authorization.

## CSS and accessibility

Newer surfaces have local `.module.css`; the transcript and some older cards still use inline styles/utilities. Reuse `ui` and shared tokens for new controls and static styling. Existing raw canvas buttons are not a reason to bypass primitives in new code. Keep icon action labels, iframe titles, keyboard submission behavior, readable errors, and non-color tool status cues. Check composer controls at the 640px breakpoint and long transcript content in both themes.

## Verification

From `spa/`:

```bash
yarn test src/components/chat/ilaStatus.test.ts src/components/chat/toolActivityFormat.test.ts
```

Add helper regressions beside these tests; they do not exercise the SSE network lifecycle. Manually check saved plus streaming messages, tool success/error/running states, Enter/Shift+Enter, parent submission guards, stop, popup blocked/error flows, lazy canvas loading/failure, image fallback, and narrow screens. For implementation changes run focused ESLint, `yarn build`, and `yarn design:audit`.
