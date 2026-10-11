# Token Usage Service Guide

`TokenUsageApiService.ts` owns per-agent usage series and the reusable `buildTokenUsageQuery`; `index.ts` exports both and their types.

- GET `/analytics/agents/{id}/token-usage` takes required `period` (`day`, `month`, `year`) plus optional `from`, `to` and `llm_model`. URLSearchParams encodes these and omits absent optional values.
- Preserve response range/model-filter metadata and the `series` envelope. Points include prompt/completion/total tokens and call count; don't substitute chart aggregates for backend facts in the service.
- `../apikeys/SecretKeyService.ts` reuses the same query builder and series type for key usage. Change that shared contract in one place and verify both callers.
- Reads use dashboard account/auth context; date bucketing and access enforcement belong to the API.

No adjacent tests currently. Add required/optional query and encoding tests, including the secret-key caller; from `spa/`, run `yarn test src/services/tokenUsage src/services/apikeys` after adding coverage. See [services guide](../CONTRIBUTION.md).
