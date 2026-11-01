# Platform Seam Guide

The website and the store apps differ in a short, fixed list of ways: how sign-in starts and finishes, where
tokens live, where a flow returns to, how a link or file leaves, where small values are kept, what happens on
returning to the foreground, whether push exists and whether the app may sell. Each is a port in `types.ts`;
an adapter implements them all. Design: [LLD-mobile-ready-app](../../../docs/LLD-mobile-ready-app.md), section 1.

| File | What it is |
| --- | --- |
| `types.ts` | The `Platform` interface and its ports. Read this first |
| `index.ts` | `initPlatform()` (awaited by `main.tsx` before the first render), `platform()`, `setPlatformForTests()` |
| `api.ts` | `apiPost()`: a bare JSON POST for the adapters, which can't use the HTTP client (it depends on the token port) |
| `web/` | The browser adapter: today's behaviour (localStorage `auth_token`, redirects, `visibilitychange`, downloads) |
| `native/` | The Capacitor adapter for the store apps. `tokens.ts` (access token in memory, `{userId, refreshToken}` in the vault, single-flight refresh; a 401 from refresh signs out, offline does not), `vault.ts` (Keychain/Keystore via `@aparajita/capacitor-secure-storage`, this-device-only; also holds the `device_id`), `auth.ts` (PKCE sign-in in the system browser), `links.ts` (`Browser`, `appUrlOpen` and the launch URL, deduplicated), `storage.ts` (Preferences behind a memory cache), `files.ts` (cache + share sheet), `statusBar.ts` (status bar text follows the app theme) |
| `pkce.ts` | `createVerifier()`, `challengeFor()` (RFC 7636 S256; tested with the RFC's example) |
| `appLinks.ts` | `parseAppLink()`: `<scheme>://auth/...` (login code or error) and `<scheme>://return/dashboard/...`; anything else is dropped |
| `testing.ts` | `createFakePlatform()`: in-memory ports that record what they were asked (`opened`, `begun`, `values`, `resume()`) |
| `testSetup.ts` | Vitest setup: installs the web adapter, so tests that stub `localStorage` keep working |

`../components/platform/AppLinkRouter.tsx` acts on app links (it lives outside this folder because it uses the
router and services): a login code is redeemed and the dashboard opens; the chat card's return
(`/dashboard/oauth/done`) is completed in place and posted to the card like the web popup's message; any other
return is a full load of its page, as on the web, so the page reads the result on mount.

`publicSite` is false in the apps: `/` goes to the dashboard, a signed-out person to `/login`, and the concierge,
navbar and footer are not shown. Gate on it, not on `kind`.

## Rules

- Call `platform().<port>` from pages, components, services and hooks. Never ask which platform you are on:
  gate UI on capabilities (`commerce.canSellSubscriptions`, `push !== null`).
- Don't read `auth_token` or `active_account_id` from storage, send the page to a sign-in URL, or call
  `window.open` outside this folder. `yarn design:audit` fails on these (Settings' OpenAI tab is the one
  listed exception).
- ESLint enforces the imports: callers use `src/platform` (index or types), never `platform/web` or
  `platform/native`; this folder imports nothing from pages, components, services or hooks; only `native/`
  may import `@capacitor/*`.
- A new stored value gets a `StorageKey`. A port method that means nothing on one platform is still
  implemented, as a no-op or an honest default; only `push` may be `null`.

## Verify

From `spa/`: `yarn test src/platform src/services/http`, `yarn lint`, `yarn design:audit`, `yarn build`. For the
apps also `yarn cap:sync` (see `spa/AGENTS.md`); the website bundle must not contain Capacitor
(`grep -rli capacitor dist/` prints nothing).
