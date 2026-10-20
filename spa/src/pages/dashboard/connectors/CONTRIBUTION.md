# Connector Page Helpers Guide

These helpers support parent `../ConnectorsPage.tsx` at `/dashboard/connectors`; they are not nested routes. Account connections are configured here, while agent attachment/delegation lives in `agent-detail/`.

## Layout and flow

- `CustomMCPDialog.tsx`: custom HTTP/stdio connection create/edit, credentials and OAuth discovery; submits through `connectorApiService` and can restart a hosted runtime after saving.
- `mcpConnectionForm.ts`: typed editable state, rows/arguments, create/update request construction, delivery choices. `mcpConnectionForm.test.ts` covers these transformations.
- `catalogItems.ts`: one `CatalogItem` type for Google accounts and MCP providers, plus `buildCatalog`, `filterCatalog` (name, description, tags) and `groupCatalog` (Popular, then categories). Tested in `catalogItems.test.ts`.
- `ConnectorCatalog.tsx`: search, the installed strip, category rows (`+` installs, `…` manages) and the "Your own server" section. `ConnectorCatalog.test.tsx` covers the controls members and admins see.
- `ConnectorDetailsDialog.tsx` / `MCPConnectionCard.tsx`: what one connector has installed, with sign-in, settings, runtime and uninstall.
- `ConnectorIcon.tsx`: local SVG/PNG brand marks from `src/assets/connectors/<icon>.svg|png`, a server symbol for custom MCP connections, otherwise a lettered tile. Google Ads also accepts the legacy `megaphone` account key. Asset sources and padding rules are in `src/assets/connectors/README.md`; `ConnectorIcon.test.tsx` checks coverage against backend icon definitions.
- `SchemaFormDialog.tsx`: async schema loading/submission and visible loading/error states for provider install/settings.
- `MCPRuntimeStatus.tsx`: runtime status fetch/restart affordance.
- `connectorUi.tsx`: provider icons and small Field/Hint/IconBox helpers.
- `connectorUrls.ts`: constructs return-to-connectors URLs.
- `connectionIcon.ts`: chooses the same local provider mark for hand-added connections by exact MCP hostname, with a server fallback. Used in Installed, Your own server and custom details; this does not change provider membership or authentication. Covered by `connectionIcon.test.ts` and catalog rendering tests.

The parent loads ordinary connector statuses, MCP connections, and providers; starts installs and authorization and refreshes after writes. Install state is derived from connections, not from the providers' `installed_count`. Service contracts are in `src/services/connectors/ConnectorApiService.ts` and `src/types/connectors.ts`. Preserve the distinction between connection config, authorization, runtime state, and agent enablement.

## Extension and styles

Put request conversion in `mcpConnectionForm.ts` and test create/update cases, especially existing-secret preservation and stdio credentials. Backend schemas/policy own credential and allowlist validation; browser checks should only aid input. Use existing authorization return helpers instead of hardcoding redirect origins. Preserve `useCanManageSettings` behavior in the parent and never display/log secret values unnecessarily.

Layout lives in `ConnectorCatalog.module.css`. Add semantic local styling there rather than leaking generic global dialog/input rules.

## Verification

From `spa/`: `yarn test src/pages/dashboard/connectors`, `yarn eslint src/pages/dashboard/connectors src/pages/dashboard/ConnectorsPage.tsx`, then `yarn test`, `yarn lint`, `yarn build`. Check create/edit for HTTP and stdio, OAuth discovery failure/return, provider schema errors, runtime restart, and restricted settings access.
