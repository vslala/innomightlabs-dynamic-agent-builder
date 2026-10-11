# Connector Page Helpers Guide

These helpers support parent `../ConnectorsPage.tsx` at `/dashboard/connectors`; they are not nested routes. Account connections are configured here, while agent attachment/delegation lives in `agent-detail/`.

## Layout and flow

- `CustomMCPDialog.tsx`: custom HTTP/stdio connection create/edit, credentials and OAuth discovery; submits through `connectorApiService` and can restart a hosted runtime after saving.
- `mcpConnectionForm.ts`: typed editable state, rows/arguments, create/update request construction, delivery choices. `mcpConnectionForm.test.ts` covers these transformations.
- `MCPProviderCatalog.tsx`: curated providers, backend install schema, installation and authorization continuation.
- `SchemaFormDialog.tsx`: async schema loading/submission and visible loading/error states for provider install/settings.
- `MCPRuntimeStatus.tsx`: runtime status fetch/restart affordance.
- `connectorUi.tsx`: provider icons and small Field/Hint/IconBox helpers.
- `connectorUrls.ts`: constructs return-to-connectors URLs.

The parent loads ordinary connector statuses, MCP connections, and providers; starts authorization and refreshes after writes. Service contracts are in `src/services/connectors/ConnectorApiService.ts` and `src/types/connectors.ts`. Preserve the distinction between connection config, authorization, runtime state, and agent enablement.

## Extension and styles

Put request conversion in `mcpConnectionForm.ts` and test create/update cases, especially existing-secret preservation and stdio credentials. Backend schemas/policy own credential and allowlist validation; browser checks should only aid input. Use existing authorization return helpers instead of hardcoding redirect origins. Preserve `useCanManageSettings` behavior in the parent and never display/log secret values unnecessarily.

There are no local CSS Modules or plain CSS files here. Components use shared UI with utility/inline styling. Add semantic local styling for substantial new layout rather than leaking generic global dialog/input rules.

## Verification

From `spa/`: `yarn test src/pages/dashboard/connectors/mcpConnectionForm.test.ts`, `yarn eslint src/pages/dashboard/connectors src/pages/dashboard/ConnectorsPage.tsx`, then `yarn test`, `yarn lint`, `yarn build`. Check create/edit for HTTP and stdio, OAuth discovery failure/return, provider schema errors, runtime restart, and restricted settings access.
