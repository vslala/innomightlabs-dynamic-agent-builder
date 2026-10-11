# Automation Chain Logic Guide

This directory turns the backend graph into the ordered chain UI and describes edits without doing I/O. Backend contracts remain in `src/types/automation.ts`; persistence belongs to `../hooks/useAutomationDraft.ts`.

## Layout

- `chainModel.ts`: edge indexes, ancestor/descendant/join traversal, `linearize`, recursive lane/item types, lookup/editability helpers.
- `chainOperations.ts`: insert, patch, action selection, delete, move, convert, stop lane, skeleton creation, and derived positions. Returns `GraphMutation` with a `PersistPlan` (`none`, node patch, or structural write).
- `chainValidation.ts`: chain issues, required arguments, per-node grouping/error counts. Client diagnostics help editing; backend validation remains authoritative.
- `actionSummary.ts`: catalog lookup, step/condition/trigger summaries, icons, cron/run-at descriptions.
- `aliases.ts`: reserved aliases, slugification, alias errors.
- `conditionExpression.ts`: parse/compile supported structured conditions and retain raw-expression fallback.
- `formArguments.ts`: argument/FormValue conversion and schema smart-value affordances.
- `smartValues.ts`: input-key detection, eligible upstream steps, aliases/references, declared/sample output fields, path resolution.
- `chain.test.ts`: existing graph, mutation, validation, summary, condition, and smart-value behavior tests.

## Extension rules

Order comes from edges, not stored coordinates; positions are derived for graph consumers. A branch operation must preserve lanes, joins, and terminal reachability. Return a new graph and the correct persistence plan instead of calling services inside a mutation. Whole-graph saves carry all surviving nodes; omissions mean deletion to the API.

For new graph behavior, add fixtures/assertions in `chain.test.ts`, implement it in the owning file, then wire draft/context/cards. Keep unknown condition expressions usable as raw expressions. Smart-value candidates must respect graph ancestry rather than offering arbitrary future steps. Don't duplicate alias or argument conversion logic in cards.

## Styling and verification

No CSS or rendered components live here; display styling belongs to parent `workspace.css`/`styles.css` and cards. From `spa/`: `yarn test src/pages/dashboard/automations/chain/chain.test.ts`, `yarn eslint src/pages/dashboard/automations/chain`, then `yarn test`, `yarn lint`, `yarn build`. Use real graph fixtures for joins, empty branches, stop/delete/move cases, and references rather than mocking these pure functions.
