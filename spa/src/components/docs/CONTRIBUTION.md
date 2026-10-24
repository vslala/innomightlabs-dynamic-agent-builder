# Documentation Shell Contribution Guide

## Purpose and layout

`DocsLayout.tsx` and `DocsLayout.module.css` provide the public documentation shell. Actual documentation pages live in `src/pages/docs/`; public-route/indexing metadata lives in `src/routes/publicPages.ts`.

## Flow and extension

The shell receives `children`, `title`, `description`, and `navItems` with `{ id, label, href, nested? }`. It renders Navbar, a left documentation sidebar, the main heading/content, a sticky right-hand "On this page" index, and Footer. The document links are a local list in the shell. Section links use the supplied hrefs. A requestAnimationFrame-throttled scroll/resize handler selects the last target above the navbar offset, including nested headings, and updates its active class and `aria-current="location"`. Listeners and pending animation frames are cleaned up on navigation/unmount.

When adding a section, provide a stable, unique DOM id and matching anchor href; this shell does not generate headings or ids. When adding a public docs page, coordinate the route registry, App page mapping, and shell document-link list—changing navigation alone does not register a route. Keep content and page-specific interactive examples out of the shell.

## CSS and accessibility

Styles are a CSS module, not global prose CSS. Descendant prose rules intentionally exclude elements inside `[data-docs-embed]`; wrap embedded product surfaces with that attribute so documentation heading/list/code styles do not restyle them. Preserve the `:where()` specificity choice. Shared color/border tokens provide theme adaptation, although existing literal backgrounds still need visual checking.

The documentation sidebar is hidden below 1024px. At 1280px and above, the section index sits in a sticky right rail with its own overflow for long lists. Below 1280px, it becomes a native, initially collapsed "On this page" disclosure above the content. No mobile cross-page menu is supplied here. Anchor targets have a 100px scroll offset for the fixed navbar. Use real links, meaningful heading order, visible focus, and stable IDs. Active documentation links use `aria-current="page"`; active section links use `aria-current="location"`. Set `nested: true` for a subsection's visual indentation.

## Verification

Run `yarn test src/components/docs/DocsLayout.test.tsx` from `spa/` for shell markup, accessible index links, and valid anchor targets across all five public docs pages. Run `yarn test src/routes/publicPages.test.ts` if navigation/route metadata changes, and add focused coverage for new helper logic. Manually test direct docs URLs, anchors and navbar offsets, scrollspy, observer cleanup, long code blocks, embedded examples, mobile versus desktop sidebar behavior, keyboard navigation, and both themes. For implementation changes run focused ESLint and `yarn build`; static-render tests do not exercise browser scrolling, sticky positioning, or responsive layout.
