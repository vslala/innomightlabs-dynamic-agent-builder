# HTTP Boundary Guide

`client.ts` is the dashboard JSON/multipart boundary; `index.ts` exports the singleton, `authorizedFetch`, `HttpError`, options and account/header helpers.

- Base URL is `VITE_API_BASE_URL`, falling back to `http://localhost:8000`. `authHeaders()` reads the access token from `platform().tokens` and `active_account_id` from `platform().storage` (both localStorage on the web) and emits bearer plus `X-Account-Id`. Never read them from storage directly: `yarn design:audit` fails on it (see `src/platform/CONTRIBUTION.md`).
- `skipAuth` omits both auth/account headers, but does not disable response interceptors. Auth headers are assigned after custom headers on ordinary requests.
- A 401 on an authenticated request asks `platform().tokens.refresh()` for a new token and retries once. The web has no refresh token, so it returns null and the 401 stands: the client clears only the token (`tokens.clear()`) and navigates to `/` unless already there; unlike explicit logout it keeps the account selection.
- Structured 429 `detail.message` dispatches the browser `rate-limit` event with message/upgrade URL. Other failures become `HttpError` with status; non-HttpError failures become status 0. Do not swallow these into empty domain results.
- JSON is the default. FormData suppresses automatic Content-Type so the browser chooses a boundary. 204 currently returns `{}` cast to the response type, not undefined.
- Direct fetch callers (streams, blobs, canvas HTML) use `authorizedFetch(url, init)`: the signed-in headers plus the same refresh-and-retry on 401. It returns the response either way, so they keep their own error handling; there is no redirect or 429 event for them.

`client.test.ts` covers account context, skipAuth, refresh-and-retry (with `createFakePlatform`), 401, 429, multipart, 204 and `authorizedFetch`. From `spa/`, run `yarn test src/services/http`, then [services full checks](../CONTRIBUTION.md). Never print credential values in tests/logs.
