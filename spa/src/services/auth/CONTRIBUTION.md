# Dashboard Auth Service Guide

`index.ts` owns `auth_token` storage, display claims, Google login URL, `/auth/me`, logout and `/users/me` deletion. This is not widget visitor auth.

- `decodeToken()` reads JWT payloads without signature verification. `isAuthenticated()` only checks readable expiry; neither is authorization. `sub` is the user ID, while email is display data.
- `getCurrentUser()` uses authenticated `httpClient` and maps backend `user_id` to UI `userId`. Keep that mapping explicit.
- `removeToken()` clears the active-account selection as well as the token; logout then navigates to `/`. HTTP client's 401 path is separate and currently clears only the token.
- Google login is a URL/navigation flow using `VITE_API_BASE_URL` (localhost:8000 fallback), not a JSON request. Do not mix dashboard tokens with public widget keys or visitor tokens.

No adjacent tests currently. Test malformed/expired claims, account cleanup and the `/auth/me` mapping at browser/network boundaries; run `yarn test src/services/auth` from `spa/` once added. See [services guide](../CONTRIBUTION.md).
