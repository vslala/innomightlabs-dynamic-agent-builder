# Dashboard Auth Service Guide

`index.ts` owns display claims, `/auth/me`, logout and `/users/me` deletion. The token itself lives behind `platform().tokens`, and sign-in starts with `platform().auth.begin(provider)`. This is not widget visitor auth.

- `decodeToken()` reads JWT payloads without signature verification. `isAuthenticated()` only checks readable expiry; neither is authorization. `sub` is the user ID, while email is display data.
- `getCurrentUser()` uses authenticated `httpClient` and maps backend `user_id` to UI `userId`. Keep that mapping explicit.
- `removeToken()` clears the active-account selection as well as the token. `logout()` is async: `platform().auth.end()` (native revokes the device), clears the selection, then navigates to `/`. HTTP client's 401 path is separate and clears only the token.
- Do not mix dashboard tokens with public widget keys or visitor tokens. The Settings "Delete account" card (`pages/dashboard/DeleteAccountCard.tsx`) calls `deleteAccount()` then `logout()`.

No adjacent tests currently. Test malformed/expired claims, account cleanup and the `/auth/me` mapping at browser/network boundaries; run `yarn test src/services/auth` from `spa/` once added. See [services guide](../CONTRIBUTION.md).
