# Automations Service Guide

`AutomationApiService.ts` is the HTTP boundary for automation metadata, graph editing, action catalogs, enabled skills, triggers, smart-value previews and runs. Types live in `src/types/automation`.

- Creation returns `AutomationGraphResponse`; metadata reads return `AutomationResponse`. Graph replacement uses PUT `/graph`, node and metadata updates use PATCH. Do not interchange these payloads.
- Trigger forms come from `/triggers/forms/{triggerType}` as `FormSchema`; backend schema/validation owns trigger configuration.
- Skill enablement encodes `skill_id` in the query. Preview and test-run are explicit POST operations, not local graph execution.
- Run listing returns `PaginatedResponse<AutomationRunResponse>` with URLSearchParams-built filters; run detail has its own response contract. Preserve pagination instead of flattening results.

No adjacent tests currently. Add graph/patch, trigger schema, pagination and test-run request tests; use `yarn test src/services/automations` from `spa/` once added. [Services guide](../CONTRIBUTION.md) covers HTTP/auth and full checks.
