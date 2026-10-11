# Automations Workspace Guide

This module owns automation collection CRUD and the chain workspace. Routes live in `src/App.tsx`: `/dashboard/automations/:automationId` now shows one workspace; old `triggers`, `runs`, and `analytics` subroutes redirect into its panels through `WorkspaceRedirect.tsx`.

## Layout and flow

- `AutomationsListPage.tsx`: list/create/delete through `automationApiService`.
- `AutomationDetailLayout.tsx`: load automation metadata, provide typed outlet context, publish templates through `automationMarketplaceApiService`.
- `types.ts`: `useAutomationDetailContext` and context contract.
- `AutomationWorkspacePage.tsx`: production wiring for draft/runs/URL hooks, `apiChainGateway`, status/title/delete/skill operations.
- `AutomationWorkspace.tsx`: shared interactive surface accepting draft, runs, params, gateway, and operations. Also rendered by the public docs sandbox; keep production network/auth concerns out of this component.
- `chain/`: graph-to-chain model, pure mutations, validation, smart values; read its guide.
- `hooks/`: optimistic persistence, run following, URL state; read its guide.
- `components/`: chain cards, trigger editor, test/issues/run panels and typed gateway/context; read its guide.
- `runDisplay.ts`: extracts visible runtime events/tool calls and filters display context.

Edits become pure `GraphMutation`s, update the local draft, and enter its save queue. Testing must flush pending edits before starting a run. Selected runs feed per-node result panels; URL `step`, `panel`, and `run` state supports direct linking. Triggers persist through their own endpoints, not graph writes. Action/trigger fields come from backend schemas/catalogs.

## Extension and CSS

For a new operation, implement/test the graph behavior in `chain/`, connect it through the draft/context, then add the UI. Update the sandbox adapter when a shared contract changes; don't add production service imports to reusable cards.

Plain global CSS is deliberate here: `AutomationsListPage.css` owns the list, `AutomationDetailLayout.css` owns the shell, `workspace.css` owns workspace/chain-card layouts, and `styles.css` owns JSON/runtime-event presentation. `AutomationWorkspace.tsx` imports the last two. Preserve feature prefixes, scope changes carefully because docs reuse the workspace, and avoid generic global selectors.

## Verification

From `spa/`: `yarn test src/pages/dashboard/automations/chain/chain.test.ts src/pages/dashboard/automations/hooks/workspaceParams.test.ts`, `yarn eslint src/pages/dashboard/automations`, then `yarn test`, `yarn lint`, `yarn build`. Check insert/delete/move/branch edits, save errors/retry, test-after-save, run selection, redirect URLs, trigger changes, and public sandbox with `yarn dev`.
