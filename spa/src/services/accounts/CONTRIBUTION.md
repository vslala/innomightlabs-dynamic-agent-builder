# Accounts Service Guide

`index.ts` owns membership discovery and account switching through `accountService`.

- `GET /accounts` returns memberships, including `access_summary`, suspended/active status and the API's `active` flag. These are display/context data, not client authorization.
- `current()` prefers the stored `active_account_id` when found in the returned list, then the API-active membership. It does not independently filter suspended memberships.
- `switchTo()` awaits `PUT /accounts/active` with `{ account_id }` before storing the selection via `setActiveAccountId`; a failed switch must not change local context. Subsequent dashboard calls receive `X-Account-Id` from the HTTP layer.
- Storage is currently localStorage, despite comments describing a per-tab choice; do not document it as sessionStorage isolation. Account-scoped UI reload/reset belongs to consumers.

From `spa/`: `yarn test src/services/accounts` exercises `accounts.test.ts`. Extend it for fallback selection and failed switches; see [the services guide](../CONTRIBUTION.md) for HTTP and full validation commands.
