# Documentation Shell Contribution Guide

## Purpose and layout

`DocsLayout.tsx` and `DocsLayout.module.css` provide the public documentation shell. Actual documentation pages live in `src/pages/docs/`; public-route/indexing metadata lives in `src/routes/publicPages.ts`.

## Flow and extension

The shell receives `children`, `title`, `description`, and `navItems` with `{ id, label, href }`. It renders Navbar, a documentation/page-section sidebar, the main heading/content, and Footer. The document links are a local list in the shell. Section links use the supplied hrefs; IntersectionObserver watches elements found by each item id and updates the active class. The observer disconnects on cleanup and uses a top offset for the fixed navbar.

When adding a section, provide a stable, unique DOM id and matching anchor href; this shell does not generate headings or ids. When adding a public docs page, coordinate the route registry, App page mapping, and shell document-link list—changing navigation alone does not register a route. Keep content and page-specific interactive examples out of the shell.

## CSS and accessibility

Styles are a CSS module, not global prose CSS. Descendant prose rules intentionally exclude elements inside `[data-docs-embed]`; wrap embedded product surfaces with that attribute so documentation heading/list/code styles do not restyle them. Preserve the `:where()` specificity choice. Shared color/border tokens provide theme adaptation, although existing literal backgrounds still need visual checking.

The sidebar is hidden below 1024px. Check content and anchor usability without it; do not assume a mobile navigation menu is supplied here. Headings have scroll offsets. Use real links, meaningful heading order, visible focus, and `aria-current` when improving active navigation. The current active classes alone are not programmatic current-section announcements.

## Verification

There are no local shell tests. Run `yarn test src/routes/publicPages.test.ts` from `spa/` if navigation/route metadata changes, and add focused coverage for new helper logic. Manually test direct docs URLs, anchors and navbar offsets, scrollspy, observer cleanup, long code blocks, embedded examples, mobile versus desktop sidebar behavior, keyboard navigation, and both themes. For implementation changes run focused ESLint and `yarn build`; helper tests do not exercise IntersectionObserver layout.
