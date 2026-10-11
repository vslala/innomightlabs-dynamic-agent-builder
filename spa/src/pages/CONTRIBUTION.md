# SPA Pages Guide

`src/pages/` owns routed React screens, not shared UI, the embed runtime, or API transport. Read `spa/AGENTS.md`, `spa/SKILLS.md`, and `CODE_PHILOSOPHY.md` first. Paths below are relative to `spa/` unless stated otherwise. Feature directories have their own `CONTRIBUTION.md`; start there for dashboard, docs, legal, sitemap, and release notes.

## Layout and flows

| Files | Responsibility |
| --- | --- |
| `LandingPage.tsx` | Composes Navbar, Hero, Features, HowItWorks, and Footer; those components own their presentation |
| `Contact.tsx` | Query-prefilled contact form, submission through `httpClient`, success/error feedback |
| `DownloadsPage.tsx`, `PluginDetailsPage.tsx` | List plugins, load `pluginId` detail through `downloadsApiService`, render README with MarkdownRenderer, link to download URLs |
| `Pricing.tsx` | Load plans through `pricingService`, select billing cycle, start checkout; signed-out selection is remembered as `pendingCheckout` in sessionStorage |
| `Login.tsx`, `LoginSuccess.tsx` | Sign-in and callback; save auth token, establish active account, resume eligible pending checkout or enter dashboard |
| `PaymentSuccess.tsx`, `PaymentCancel.tsx` | Checkout return states; success looks up session/subscription state and deduplicates conversion tracking |

## Routing and extension

`src/App.tsx` lazily loads named exports. `src/routes/publicPages.ts` is the source for public routes, indexing metadata, the human sitemap, and build-generated public HTML/XML. Add a public page there and to App's `Record<PublicPath, ReactElement>` together. Parameterized download detail routes are routed but not indexed; login and payment returns are also non-indexed. Preserve BrowserRouter's configured basename.

Use domain services under `src/services/` and explicit response types. Existing contact/auth/payment screens have direct `httpClient` calls: preserve their boundary rather than adding raw fetch or duplicating transport. Keep loading, empty, error, and disabled-submit states visible. Never expose tokens or server keys in examples or logs.

## Styling ownership

`Downloads.module.css` serves both download screens; `PaymentResult.module.css` serves both payment returns. Pricing, Login, and LoginSuccess own their named CSS Modules. Landing styling belongs to composed components; Contact currently uses local inline/utility styling. These are actual mixed conventions, not a mandate to convert everything. Prefer semantic page-local classes for substantial new layout, shared UI primitives, theme variables, and dynamic-only inline styles.

## Verification

Run commands from `spa/`:

```bash
yarn test src/routes/publicPages.test.ts
yarn eslint src/pages/Pricing.tsx src/pages/LoginSuccess.tsx
yarn test
yarn lint
yarn build
yarn design:audit
```

`test` is `vitest run`; `build` is `tsc -b && vite build`. Focus eslint on the TS/TSX files actually changed; it is not a Markdown check. Use `yarn dev` for visual checks of public navigation, auth returns, checkout continuation, and narrow layouts. Guides document commands, not evidence that they were run.
