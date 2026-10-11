# Agent Marketplace Service Guide

`AgentMarketplaceApiService.ts` exposes catalog listing/detail, import planning, import and publication under `/agent-marketplace/agents`; types come from `src/types/agentMarketplace`.

- Listing trims the optional query and omits it when blank. Template IDs and search terms are URL-encoded.
- Keep `getImportPlan()` separate from `importAgent()`: inspecting a template must not create an agent. Submit the typed import/publish payload unchanged; the API decides dependencies and access.
- These calls currently use authenticated/account-aware `httpClient`, including catalog reads. Do not assume a marketplace route is anonymous because the UI presents a catalog.

No adjacent tests currently. Add request-boundary tests for blank queries, encoded IDs, import-plan versus import paths and payloads; run `yarn test src/services/agentMarketplace` from `spa/` after adding them. Shared rules and full checks: [services guide](../CONTRIBUTION.md).
