# Automation Marketplace Service Guide

`AutomationMarketplaceApiService.ts` manages catalog/detail, import plans, imports, saved import sessions and publishing under `/automation-marketplace/automations`. Contracts live in `src/types/automationMarketplace`.

- Trim/encode search queries and encode template IDs as the existing methods do.
- Import planning, `import-session` saving and actual `/import` are different requests with different typed responses. Preserve the resumable import-session contract; do not collapse it into resource creation.
- Publication submits the typed publish request. Dependency checks and installation authority stay on the API.
- All current calls use dashboard bearer/account context, including catalog reads; anonymous browsing is not implied by this service.

No adjacent tests currently. Cover encoded identifiers, session versus import endpoints and exact payloads; use `yarn test src/services/automationMarketplace` from `spa/` once tests exist. Full checks: [services guide](../CONTRIBUTION.md).
