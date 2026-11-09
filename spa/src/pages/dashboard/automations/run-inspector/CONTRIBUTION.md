# Run Inspector Guide

The run page at `/dashboard/automations/:automationId/runs/:runId`: every step one run took and every tool call its
agents made, in order, laid out for a phone first. Design: [LLD](../../../../../../docs/LLD-automation-run-inspector.md).

## Layout and flow

- `RunInspectorPage.tsx`: route. Follows the run with `useAutomationRuns` (polls while it executes), loads graph
  nodes for step names, keeps `?step=<result_id>&tab=&call=<tool_call_id>` through `useWorkspaceParams`.
- `runSteps.ts`: results joined to nodes in run order, step labels, which tab a step opens on.
- `RunOverview.tsx`: run summary and the step list. `RunStepPanel.tsx`: one step's Activity / Output / Input / Raw tabs.
- `useStepToolCalls.ts`: fetches a step result's events once (`getStepEvents`), only when it has tool calls.
- `toolCalls.ts`: pure. `toolCallsFrom` pairs START and RESULT by `tool_call_id` in start order (name order only for
  events recorded without an id), plus titles, argument summaries, result parsing, filters and search.
- `ActivityTimeline.tsx`: search, filter chips, the timeline; the selected call in a side pane when the activity
  area is at least 46rem wide, otherwise in a bottom sheet (`Dialog`) with previous/next.
- `ToolCallDetail.tsx`: one call in full. `RunsDialog.tsx`: switch runs, analytics. `parts.tsx`: section, copy
  button, `ExpandableText`, `ValueList`.

## Rules

- Never trim content. Fold long text with `ExpandableText`; it keeps the whole value in the DOM. One-line summaries
  are for list rows only, with the full value one tap away.
- Pair tool calls by id. Don't reintroduce name-based pairing for events that have an id.
- Breakpoints are container queries in `run-inspector.css`. `SIDE_BY_SIDE_PX` in `ActivityTimeline.tsx` must equal
  the `run-activity` query width (46rem).
- Row buttons reuse `Button`; their overrides are scoped under `.run-inspector` so they beat its centred defaults.

## Verification

From `spa/`: `yarn test src/pages/dashboard/automations/run-inspector/toolCalls.test.ts`,
`yarn eslint src/pages/dashboard/automations`, then `yarn test`, `yarn build`. Check at 390px and desktop: a run with
failed and unanswered calls, a deep link with `?call=`, previous/next in the sheet, the runs dialog, and an old run
recorded before step logs (no timings, still paired).
