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
| `testing.ts` | `createFakePlatform()`: in-memory ports that record what they were asked (`opened`, `begun`, `values`, `resume()`) |
| `testSetup.ts` | Vitest setup: installs the web adapter, so tests that stub `localStorage` keep working |

The native adapter (`native/`), `appLinks.ts` and `pkce.ts` arrive with the app shells (Phase 1).

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

From `spa/`: `yarn test src/platform src/services/http`, `yarn lint`, `yarn design:audit`, `yarn build`.
