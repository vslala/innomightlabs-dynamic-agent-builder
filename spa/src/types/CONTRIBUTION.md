# Shared Types Contribution Guide

## Purpose and layout

This directory holds shared frontend domain/API shapes and a few runtime constants. It is not generated validation code or a guarantee that an unknown response conforms to TypeScript. Some service-specific response types intentionally remain in their service files; do not duplicate them here just for uniformity.

- `agent`, `agentMarketplace`: agent and marketplace contracts.
- `automation`, `automationMarketplace`: automation/run and marketplace shapes.
- `conversation`, `message`: history, attachments, images, canvases, tool activity, and SSE payloads.
- `form`: backend form-schema contract and typed form values.
- `connectors`, `skills`, `knowledge`: connected resources and configuration.
- `downloads`, `pricing`, `subscription`: public/download/payment-related shapes.

## Data flow and extension

Services use these types for requests/responses; pages and shared components import them for presentation. Keep backend field spellings and optional/null distinctions explicit. Inspect both the service and API definition before changing a contract; do not invent a field because a component would find it convenient. New unknown payloads should use `unknown` and narrow at a real boundary, not broad `any`.

`form.ts` defines the supported `FormInputType` union, `FormValue` (string, FileList/File arrays, key-value record, or null), grouped options/filtering, option sources, validation, and suggestions. A typed option source `endpoint` or `mode` does not imply that `useHydratedFormSchema` implements arbitrary sources; currently it hydrates agents only. Adding an input type also requires editing and read-only renderers, and backend coordination.

`message.ts` includes runtime attachment extension/count/size constants and the `SSEEventType` object plus derived union. Keep attachment rules aligned with the API; chat text/Excel attachments are not arbitrary binary uploads. Tool-call identity uses `tool_call_id`, not tool name alone. Optional display names/arguments support wrapper-tool presentation; maintain fallback behavior when older events lack them. Add an event only with coordinated service/consumer handling, not just a union member.

## CSS, accessibility, and verification

Types have no CSS or UI semantics. Consumers own design-token styling, labels, focus, and readable status; a status union alone cannot make a view accessible.

For contract changes, run focused consumer tests and `yarn build` (which runs `tsc -b`) from `spa/`. Nearby existing coverage includes form option-filter tests, chat activity-format tests, and route metadata tests. Add tests for runtime constants/transforms where behavior changes; a type-only compile does not validate server JSON. Check loading/null/omitted fields against actual responses and manually inspect affected views. Do not centralize service-owned types into a second source of truth.
