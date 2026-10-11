# Blueprints Service Guide

`BlueprintApiService.ts` owns YAML examples, validation, planning and deployment history/application. Its exported issues, plans and deployment status types are also reused by kits.

- `getExample()` unwraps `{ name, yaml }` to a string and encodes the example name.
- Validation POSTs `{ yaml }`; planning and application send `{ yaml, params }`. Parameters are `Record<string, string>`. Keep validation/plan separate from POST `/blueprints/deployments`, which applies changes.
- Preserve `applying`, `applied`, `failed` and `failed_partial`: partial failure is not successful deployment or an empty result. Retain issue/step detail for callers.
- Backend planning, resource ownership and validation are authoritative; do not parse/apply blueprints in the SPA service.

No adjacent tests currently. Add example-unwrapping and validate/plan/apply payload tests; use `yarn test src/services/blueprints` from `spa/` once added. See [services guide](../CONTRIBUTION.md).
