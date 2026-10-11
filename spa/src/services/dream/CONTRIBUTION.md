# Dream Service Guide

`DreamApiService.ts` separates user dream configuration from per-agent runs, action audits and cursors.

- `/dream/status` reports availability; `/dream/settings` may return null. Configuration schema comes from `/dream/settings/forms/configure`.
- `DreamSettingsRequest` omits response-only `user_email`; do not send server-owned identity from a settings response back as configuration.
- `/agents/{id}/dream/runs` and each run's `/actions` are audit reads. `runNow()` explicitly POSTs `{}` to `/dream/run`; it returns a status acknowledgement, not a completed run.
- Cursor may be null. Preserve run statuses including `partial` and `skipped`, action outcomes and token counts instead of reducing them to a success boolean.

No adjacent tests currently. Cover null settings/cursor and run-now versus audit paths; use `yarn test src/services/dream` from `spa/` after adding tests. See [services guide](../CONTRIBUTION.md).
