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

## Styling philosophy and design rules

Read this before touching the look of any module. InnomightLabs is a working tool people return to every day, so its surfaces should feel calm, precise and trustworthy: quiet neutrals, one blue accent, colour kept for meaning, and generous but consistent space. A page should look like it belongs to the same product as its neighbours before it looks clever. `src/pages/dashboard/iam/` is a small reference implementation of these rules.

**Colour**

- Every colour comes from a token in `src/styles/tokens.css`. No hex, `rgb()` or Tailwind palette colours (`bg-blue-500`) in a module or page stylesheet; if a role is missing, add a semantic token with both its dark and light values.
- Pick the semantic token, not the one that happens to look right: `--surface-page` < `--surface-panel` < `--surface-control` for depth, `--surface-subtle` for table heads and callouts, `--border-default` for edges, `--text-primary` / `--text-secondary` / `--text-muted` for the text hierarchy.
- Blue (`--gradient-start`, `--link-color`, `--accent-blue-bg`) is the brand accent: the active tab, the primary button, focus rings, icon tiles and avatars. Use it sparingly; a screen full of blue has no emphasis left.
- Green, amber and red (`--success`, `--warning`, `--danger` with their `-bg` pair) mean succeeded, needs attention and failed. Never use them for decoration, and never use colour alone: a status is a `StatusBadge` or `Pill` with a word, an error is an `Alert` with a sentence.

**Type, space and shape**

- Type scale: page title 1.5rem / 600, section heading 1.125rem / 600, panel title 1rem / 600, body 0.875rem, and table headers 0.75rem / 600 uppercase in `--text-muted` with slight letter spacing. Secondary lines (emails, dates, descriptions) step down to `--text-muted`, not a smaller font.
- Space on the 4/8/12/16/24/32px rhythm through the `--space-*` and alias tokens (`--page-gap`, `--section-gap`, `--card-padding`, `--field-gap`). Related things sit closer than unrelated ones: a heading and its count share a row, sections are separated by a clear gutter.
- Radius by role: `--radius-lg` for cards, panels and table containers; `--radius-md` for callouts and icon tiles; full rounding for badges, pills and avatars. One border (`1px var(--border-default)`) per surface; prefer borders and surface steps to shadows.

**Composition**

- Start a page with `Page` / `PageBody` from `components/layout` and the shared primitives in `components/ui` (`Button`, `Input`, `Label`, `Alert`, `StatusBadge`, `Pill`, `Spinner`, `EmptyState`). Restyling a primitive locally is a sign the change belongs in the primitive.
- One primary action per surface (the default `Button`); secondary actions are `outline`. A destructive row action is a quiet `ghost` button in `--danger`; the `destructive` variant belongs on the confirm button of a `confirmation-dialog`. Primary actions and status come before secondary metadata.
- Lists of records are tables or `ListRow`s inside one bordered panel: a muted header row, hairline dividers, a subtle hover, people shown with an initials avatar and their email beneath the name. Show counts as a small `Pill` next to the heading.
- Every async surface designs all of its states: loading (`Spinner` with text, `role="status"`), empty (an `InlineEmptyState` that says what will appear there), error (`Alert` with a retry), read-only and success. None may fall back to unstyled text.
- Icons are lucide, 16px inside buttons, tabs and notices (18-22px in icon tiles), placed before the label, `aria-hidden` when a label is present.
- Dates read as people say them (`2 Oct 2026`, `in 5 days` via `utils/time.ts`) inside a `<time dateTime>` carrying the machine value; ids are shortened with the full value on copy or `title`.

**Before you call it done**

- Look at it, in both themes, at desktop width and around 600px. Wide tables scroll inside their card (`overflow-x: auto` and a table `min-width`) rather than breaking words letter by letter; grid columns that hold them use `minmax(0, 1fr)`.
- Check keyboard focus is visible on every control, motion respects `prefers-reduced-motion`, and text stays legible on its surface in the light theme, where the subtle backgrounds are faintest.
- Tests, `yarn lint`, `yarn build` and `yarn design:audit` do not prove any of this; say what you checked visually.

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
