# Settings Services Guide

This directory has four narrow singletons rather than one catch-all settings service.

- `ProviderSettingsService.ts`: provider list/status/settings save/delete under `/settings/providers`; OpenAI connect start/complete under `/auth/openai`. Schemas/configuration and connection responses are distinct; don't expose or cache credential material in UI metadata.
- `Agent2AgentSettingsService.ts`: `/settings/agent2agent` GET/PUT and `/schema`. Allowed origins use backend form values; origin normalization, allowlists and runtime trust checks remain API responsibilities.
- `DefaultAgentService.ts`: GET/PUT/DELETE `/settings/default-agent`; PUT sends `{ agent_id }`, clear returns void. A preference is not permission to chat with that agent.
- `SettingsAccessService.ts`: `/settings/access` returns access information for presentation. Hiding controls is not enforcement; preserve backend permission errors on actual requests.

Keep backend schema-driven values and explicit response types; use normal authenticated/account-aware HTTP. No barrel currently exists, so retain direct imports rather than adding indirection for symmetry.

No adjacent tests currently. Add tests beside the service being changed for schema routes, connect payloads, preference clearing or access responses; from `spa/`, use `yarn test src/services/settings` once added. Full checks: [services guide](../CONTRIBUTION.md).
