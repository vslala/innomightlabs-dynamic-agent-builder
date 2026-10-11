# Agent Marketplace Guide

Routes are `/dashboard/agents/marketplace` and `/dashboard/agents/marketplace/:templateId`, registered in `src/App.tsx`. This module imports published templates; publication itself lives in `agent-detail/AgentOverviewPage.tsx`.

## Layout and flow

`AgentMarketplacePage.tsx` queries `agentMarketplaceApiService.listAgents` with search text and links cards to template detail. `MarketplaceAgentDetail.tsx` loads template detail, import plan, and the agent create schema. Its import form combines the plan with backend model/provider options, submits through `importAgent`, and navigates to the imported agent.

Contracts live in `src/types/agentMarketplace.ts` and transport in `src/services/agentMarketplace/AgentMarketplaceApiService.ts`. Keep displayed dependencies/readiness aligned with the returned import plan; a template is not a live agent and importing should not silently reuse its publisher's credentials.

## Extension and styles

Add searchable/list metadata to the typed service contract before rendering it. Extend the import schema/form flow rather than hardcoding model catalogs or duplicating backend skill validation. Preserve loading, missing-template, and import-error feedback and disable duplicate submissions.

`AgentMarketplacePage.module.css` owns search/cards/grid. `MarketplaceAgentDetail.module.css` owns detail, skill rows, and import dialog. Use their scoped classes and shared layout/UI; do not style publication controls here.

## Verification

No colocated marketplace tests exist. Add focused tests for any new import-plan transforms. From `spa/`: `yarn eslint src/pages/dashboard/agent-marketplace`, then `yarn test`, `yarn lint`, `yarn build`. With `yarn dev`, check search, direct detail URLs, unavailable dependencies/providers, import failure/success navigation, and responsive cards/dialogs.
