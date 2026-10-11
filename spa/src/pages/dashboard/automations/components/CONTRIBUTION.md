# Automation Workspace Components Guide

These components render the chain and its operational panels. They are shared with the public docs sandbox and are not independently routed.

## Layout and flow

`ChainColumn.tsx` recursively renders `TriggerCard.tsx`, `StepCard.tsx`, `ConditionCard.tsx`, and `EndCard.tsx`; `InsertAffordance.tsx` opens `AddStepPalette.tsx`. `chainContext.ts` exposes the workspace graph/catalog, mutations, selections, run data, and gateway through `useChain`. `chainGateway.ts` defines `ChainGateway` and `apiChainGateway(automationId)` for smart-value previews and trigger schema/CRUD calls.

`StepCard.tsx` combines action-schema editing, reference names, smart values, menus, and `StepDataPanel.tsx`. `ConditionBuilder.tsx` handles structured/raw expressions. `TriggerCard.tsx` owns trigger setup in place. `StepIcon.tsx` and `RunStatusBadge.tsx` provide consistent affordances; `runStatus.ts` maps statuses/time/duration.

`WorkspaceTopBar.tsx` presents title/status/save/actions. `IssuesPanel.tsx` combines client issues and save failures. `TestPanel.tsx` derives input fields from graph `input.*` references and offers JSON editing via `AutomationJsonEditor.tsx`. `RunsDrawer.tsx` combines history and `AutomationAnalyticsPanel.tsx`; analytics are derived from the loaded page of runs, not complete all-time backend analytics. Runtime display transforms live in parent `runDisplay.ts`.

## Extension and CSS

Read/mutate through context, pure chain operations, and the gateway rather than importing production services into cards. Add any new gateway method to both the API implementation and sandbox adapter. Use SchemaForm/SmartValueProvider for action fields; preserve unknown/raw JSON paths when schemas cannot describe the data. Keep IDs copyable, statuses textual, and raw results collapsed where appropriate.

There are no component-local stylesheets. Parent `workspace.css` owns workspace/chain classes; `styles.css` owns JSON/runtime-event classes. Shared UI contributes its own styles. Changes affect both dashboard and docs; use prefixed selectors and inspect both surfaces.

## Verification

No component tests are colocated here; related pure logic is covered by `../chain/chain.test.ts` and `../hooks/workspaceParams.test.ts`. From `spa/`, run those with `yarn test`, focus lint with `yarn eslint src/pages/dashboard/automations/components`, then run `yarn test`, `yarn lint`, `yarn build`. Check nested conditions, schema edits, result expansion, drawer pagination, trigger forms, and sandbox interactions visually.
