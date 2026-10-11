# API Keys Service Guide

`ApiKeyService.ts` manages agent widget/public keys and one-time A2A secrets; `SecretKeyService.ts` manages agent secret keys for the public `/v1` API. Management requests use dashboard `httpClient`, not the keys being managed.

- Widget key CRUD is `/agents/{id}/api-keys`; updates use PATCH. `issueA2ASecret()` POSTs to `{keyId}/a2a-secret` and returns a secret shown once.
- Secret key CRUD is `/agents/{id}/secret-keys`. Only `CreatedSecretKeyResponse` carries plaintext; list/update responses must not be typed as create responses. Never log or persist returned secrets.
- Key usage reuses `buildTokenUsageQuery` and `TokenUsageTimeseriesResponse` from `../tokenUsage`; do not duplicate analytics filters.
- Guest/origin configuration is a backend-enforced widget-key contract. Preserve typed options; do not equate widget public keys, A2A secrets and `/v1` secret keys.

From `spa/`: `yarn test src/services/apikeys` runs `ApiKeyService.test.ts`. Extend boundary coverage for secret-only-on-create and usage filters as needed. Full checks: [services guide](../CONTRIBUTION.md).
