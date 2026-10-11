# HTTP Boundary Guide

`client.ts` is the dashboard JSON/multipart boundary; `index.ts` exports the singleton, `HttpError`, options and account/header helpers.

- Base URL is `VITE_API_BASE_URL`, falling back to `http://localhost:8000`. `authHeaders()` reads `auth_token` and `active_account_id` from localStorage and emits bearer plus `X-Account-Id`. The selection is not actually tab-local despite the source comment.
- `skipAuth` omits both auth/account headers, but does not disable response interceptors. Auth headers are assigned after custom headers on ordinary requests.
- `x-refreshed-token` is stored before status handling. A 401 removes only the auth token and navigates to `/` unless already there; unlike explicit auth logout it does not clear account selection.
- Structured 429 `detail.message` dispatches the browser `rate-limit` event with message/upgrade URL. Other failures become `HttpError` with status; non-HttpError failures become status 0. Do not swallow these into empty domain results.
- JSON is the default. FormData suppresses automatic Content-Type so the browser chooses a boundary. 204 currently returns `{}` cast to the response type, not undefined.
- Direct streaming fetch callers reuse `authHeaders`, not response interception; don't claim shared refresh/redirect behavior for them.

No adjacent tests currently. Add fetch/browser-boundary tests for account context, skipAuth, refresh-before-error, 401, 429, multipart and 204. From `spa/`, run `yarn test src/services/http` once added, then [services full checks](../CONTRIBUTION.md). Never print credential values in tests/logs.
