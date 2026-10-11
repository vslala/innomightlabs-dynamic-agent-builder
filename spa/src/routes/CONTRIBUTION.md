# Public Route Metadata Contribution Guide

## Purpose and layout

`publicPages.ts` is the single public-route metadata source; `publicPages.test.ts` tests its filtering and output. Actual React route composition is in `src/App.tsx`, including signed-in routes. This directory is not a second router implementation.

## Flow

`PUBLIC_PAGES` lists signed-out paths with indexing decisions and, for indexed fixed pages, title and sitemap section. Its literal entries derive `PublicPath`. App maps these paths to page elements; `scripts/vite-plugin-public-pages.ts` uses the same metadata for sitemap/robots output and per-page HTML copies so fixed GitHub Pages URLs resolve directly. The public `/sitemap` page consumes this metadata too.

`indexablePages` excludes unindexed entries and parameterized paths; `indexablePaths` extracts paths. `buildSitemap` writes absolute XML URLs with escaping. `buildRobotsTxt` points to the sitemap and disallows dashboard/sign-in-return/payment paths. `SITE_ORIGIN` is the production origin used by default. Robots directives and omitted sitemap entries are not authorization or a promise that a URL can never be indexed.

## Adding a page

1. Add the public path and indexing choice to `PUBLIC_PAGES`; indexed fixed pages need a meaningful title and Product/Documentation/Legal section.
2. Add the corresponding page mapping in `src/App.tsx` and implement the page in its own area. Keep signed-in pages under the protected dashboard routing rather than adding them to this list.
3. Update relevant navigation (for example DocsLayout) when the page should be discoverable there.
4. Preserve the literal array and `satisfies` typing so `PublicPath` remains useful. Do not maintain a separate sitemap list or hand-edit generated build output.

Parameterized paths are routable but never included in sitemap output. Mark sign-in/payment-return utility pages unindexed. If changing origin/output behavior, inspect the build plugin and consuming page too; metadata tests alone do not verify generated HTML or hosting behavior.

## Styling, accessibility, and verification

Route metadata has no CSS. Link/nav consumers use their local styles and shared tokens; labels should be meaningful, selected navigation should expose `aria-current`, and direct links should remain keyboard-accessible.

From `spa/`:

```bash
yarn test src/routes/publicPages.test.ts
```

Existing tests check fixed/indexable filtering, private-flow exclusions, titles/sections, duplicate paths, XML escaping, and robots sitemap reference. Add regressions for changed output/filtering. For implementation changes run focused ESLint and `yarn build`; inspect generated sitemap/robots/per-page files and manually check direct navigation, refresh, and parameterized routes on the relevant hosting setup. Build success is not proof of production HTTP status behavior.
