# Agents Service Guide

There are two distinct contracts here. `AgentApiService.ts` exports the real REST singleton `agentApiService`; `IAgentService.ts`, `LocalStorageAgentService.ts` and `index.ts` implement an older local model.

- REST CRUD uses `/agents`, backend snake_case `AgentResponse`, and backend create/update schemas. Preserve `account_id`, `owner_id`, `created_by` and `access`; owner/shared/admin metadata must not be treated as equivalent capabilities.
- A2A sharing and task inspection are REST subresources (`a2a-sharing`, `a2a-tasks`). Preserve the protocol's `TASK_STATE_*` and `ROLE_*` values rather than converting them to chat UI enums.
- `getAgentService()` currently returns the local-storage implementation even when `VITE_AGENT_BACKEND=api`; the API branch warns and falls back. Do not claim this factory selects `agentApiService` or interchange the local camelCase models with REST responses.
- Chat streaming lives in `../chat`, memory REST in `../memory`; avoid growing the local interface into a second production API.

No adjacent tests currently. Add focused REST request/schema tests or local-storage behavior tests for the implementation you change; from `spa/`, run `yarn test src/services/agents` once tests exist. Follow [services verification](../CONTRIBUTION.md).
