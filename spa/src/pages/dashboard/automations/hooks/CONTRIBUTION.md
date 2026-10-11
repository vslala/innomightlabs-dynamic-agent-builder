# Automation Workspace Hooks Guide

These hooks adapt API and URL state to the shared workspace. The docs sandbox supplies compatible state separately; keep its implementation in view when changing returned interfaces.

## Layout and invariants

`useAutomationDraft.ts` loads graph/catalog, ensures a chain skeleton, derives chain/issues, and owns optimistic persistence. Field edits coalesce per node after an 800 ms debounce and PATCH nodes. Structural mutations immediately queue a whole-graph PUT with all nodes/edges and derived positions. Only one save request runs at a time; revision tracking prevents responses from rolling back newer local edits. Failed work is retained for retry, and `flush()` reports whether queued work succeeded. Trigger writes use `refreshGraph()` rather than graph persistence.

`useAutomationRuns.ts` loads history in pages of 20 and follows a selected run every 1500 ms until succeeded/failed/cancelled. Poll generation and mounted guards stop obsolete follows. It exposes `resultsByNodeId` and context for the cards. Starting a test adds history but intentionally leaves selection to the caller/URL.

`useWorkspaceParams.ts` owns `step`, `panel`, `run`, and legacy `focus` query state. Its pure `applyParamPatch` and latest-search ref preserve unrelated query keys and multiple writes before the next render. `workspaceParams.test.ts` covers URL patch behavior.

## Extending safely

Put graph semantics in `../chain/`, not the save queue. Keep node-vs-structural persistence explicit. Any action that requires persisted edits must await `flush()` and handle false; don't start a run against stale saved state. New run statuses must agree with backend types and terminal-follow semantics. New URL keys need typed patch handling and regression tests, including back/forward and unrelated query preservation. Clean up timers/subscriptions on unmount and avoid stale updates after selection changes.

## CSS and verification

Hooks own no CSS; visible save/run states are rendered by parent components. From `spa/`: `yarn test src/pages/dashboard/automations/hooks/workspaceParams.test.ts src/pages/dashboard/automations/chain/chain.test.ts`, `yarn eslint src/pages/dashboard/automations/hooks`, then `yarn test`, `yarn lint`, `yarn build`. There are no colocated save-queue or run-follow tests yet; add boundary/timer regressions when changing them. Manually check rapid edits, failed-save retry, test flush, run switching, and URL history.
