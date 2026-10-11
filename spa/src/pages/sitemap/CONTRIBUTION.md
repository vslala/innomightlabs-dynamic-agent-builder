# Human Sitemap Guide

`SitemapPage.tsx` renders public `/sitemap` with Navbar/Footer and sectioned links. Search engines use build-generated `/sitemap.xml`; both derive from `src/routes/publicPages.ts`.

## Flow and extension

The page calls `indexablePages()` and groups entries by `SitemapSection` (Product, Documentation, Legal), showing titles and section counts. `SitemapPage.module.css` owns header, cards, lists, and links.

To add/remove an indexed page, change `PUBLIC_PAGES` and the route component mapping in `src/App.tsx`, not a hardcoded list here. Dynamic `:param` paths are excluded; login/payment return routes carry `indexed: false`. The same source is consumed by `scripts/vite-plugin-public-pages.ts` for public HTML copies and generated sitemap/robots content.

A new section requires updating the section type and page grouping/presentation as well as entry metadata. Preserve React Router links and the app basename; do not replace this with separate absolute-path navigation rules. Keep cards and section counts derived from the same filtered data.

## Verification

From `spa/`: `yarn test src/routes/publicPages.test.ts`, `yarn eslint src/pages/sitemap`, then `yarn test`, `yarn lint`, `yarn build`. No tests are colocated in this directory; routing/sitemap helpers have the referenced test. With `yarn dev`, verify section counts, link destinations, omitted private/non-indexed/parameterized routes, and mobile layout. For route changes, inspect the generated build outputs rather than assuming the visible sitemap alone verifies static hosting.
