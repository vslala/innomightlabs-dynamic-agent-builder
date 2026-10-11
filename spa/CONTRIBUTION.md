# SPA Contribution Guide

The SPA is the React 19 / TypeScript / Vite application for the public InnomightLabs site, documentation, and signed-in agent dashboard. This directory also contains two embedded chat clients and their shared stream-rendering helpers. These are separate build/runtime boundaries, not interchangeable dashboard components.

Read [AGENTS.md](AGENTS.md), [SKILLS.md](SKILLS.md), and the repository [coding philosophy](../CODE_PHILOSOPHY.md) before making changes. The module guides below explain current implementation and extension points; approved designs remain in `docs/` and their wiki copies.

## Module map

| Area | Ownership and contribution guide |
| --- | --- |
| [Pages](src/pages/CONTRIBUTION.md) | Public routed screens and feature-specific dashboard pages |
| [Dashboard](src/pages/dashboard/CONTRIBUTION.md) | Resource lists, settings, agent detail, automations, marketplaces, connectors and conversations; feature directories carry narrower guides |
| [Components](src/components/CONTRIBUTION.md) | Reusable UI, layout, auth wrapper, dashboard shell, chat, schema forms and documentation shell |
| [Services](src/services/CONTRIBUTION.md) | Typed domain API clients; each service directory has its own guide |
| [Routes](src/routes/CONTRIBUTION.md) | Public route metadata shared with sitemap and static page generation |
| [Styles](src/styles/CONTRIBUTION.md) | Shared design tokens and theme/CSS ownership |
| [Hooks](src/hooks/CONTRIBUTION.md) | Shared browser/UI behavior; feature hooks remain with their feature |
| [Config](src/config/CONTRIBUTION.md) | Browser-visible API and integration configuration |
| [Types](src/types/CONTRIBUTION.md) | Shared frontend contracts, not a duplicate of every service response |
| [Utilities](src/utils/CONTRIBUTION.md) | Reusable transformations and browser helpers |
| [Library helpers](src/lib/CONTRIBUTION.md) | Class composition and theme initialization |
| [Assets](src/assets/CONTRIBUTION.md) | Bundled visual assets and branding |
| [Embed](embed/CONTRIBUTION.md) | Customer-facing iframe app, host loader and message protocol |
| [Classic widget](widget/CONTRIBUTION.md) | Older separately built widget with its own package and authentication |
| [Chat stream renderer](packages/chat-stream-renderer/CONTRIBUTION.md) | Pure render-plan helpers shared across chat clients |

## Application flow and boundaries

`src/main.tsx` imports `src/index.css`, applies the stored theme, and mounts `App` inside React StrictMode. `src/App.tsx` owns route composition and lazy page loading. Public metadata lives in `src/routes/publicPages.ts`; `scripts/vite-plugin-public-pages.ts` uses it to generate sitemap output and public HTML shells during the Vite build. Do not hand-maintain another public route list.

Signed-in resource details use nested routes and outlet context. Keep resource state and orchestration near the page. Ordinary API requests go through singleton domain services and `src/services/http/client.ts`; authenticated streaming has its own transport in `services/chat`. Follow those boundaries rather than adding page-local raw fetch. Backend account/IAM checks remain authoritative regardless of hidden or disabled UI controls.

Schema-backed editing uses `components/forms/SchemaForm.tsx` and backend-owned schemas. Submit typed values and show API errors; do not duplicate credential or security policy validation in the browser. File uploads use the existing multipart transport.

## Component, page and CSS conventions

- Use existing `components/ui` primitives and `components/layout` composition first. Reusable components belong in their meaningful component module; one-off resource behavior stays in its page module.
- Most shared components use colocated `Name.module.css` files imported as a `styles` object. Pages also use CSS Modules, but some operational pages and dashboard chrome intentionally use plain `.css` with semantic, feature-prefixed class names. A plain CSS import is global, not scoped.
- Follow the neighboring implementation. Put substantial new static layout in a local stylesheet rather than long utility strings or inline objects. Reserve inline styles for genuinely dynamic values where practical; do not rewrite unrelated legacy styles.
- `src/styles/tokens.css` is the shared token source, including embed consumers. `src/index.css` owns global base rules/utilities. Use semantic colors, surfaces, borders and spacing tokens; maintain dark and light values together. Follow the established 4/8/12/16/24/32px spacing rhythm.
- Do not introduce broad element selectors or resets in a page stylesheet. Keep one-off geometry local and shared semantic roles in the token file.
- Use real links/buttons, visible focus, labeled icon actions, and status text beyond color. Check narrow layouts, both themes, keyboard navigation, loading/empty/error states and disabled actions. Dashboard surfaces should prioritize useful operational content over marketing-style hero layouts.

## Making a change

1. Read the owning module's guide and inspect its consuming routes, services and styles.
2. Extend the existing typed contract and service before wiring page behavior; keep secrets out of client code, logs and public environment variables.
3. For a public page, update route metadata and App composition together. For resource tabs, extend the existing nested route/context and navigation.
4. Add focused behavior tests near the changed helper/service/feature. Existing helper coverage is not a substitute for browser interaction checks.
5. If the change alters an approved design, update its LLD and wiki copy under the repository documentation rules. These contribution guides document code ownership, not a new design approval.

## Verification

Run from `spa/`:

```sh
yarn dev                # local Vite development, mode dev
yarn test path/to/test.ts # focused Vitest file
yarn test               # complete configured Vitest suite
yarn lint               # ESLint; does not validate Markdown
yarn build              # TypeScript project build, then Vite production build
yarn design:audit       # flags raw controls outside shared UI; not an accessibility test
```

Use focused ESLint on changed TS/TSX files while working. Build the embed with `yarn build:embed` when its implementation or shared styling changes; follow the classic widget guide for its independent commands. Do not edit generated `dist/` output or dependency directories.

For documentation-only changes, verify concrete file references and relative links, distinguish current behavior from recommendations, and do not claim runtime validation that was not run. Report unrelated lint failures or build warnings separately rather than changing unrelated code.
