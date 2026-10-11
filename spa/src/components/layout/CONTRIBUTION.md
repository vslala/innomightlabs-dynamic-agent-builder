# Layout Primitives Contribution Guide

## Purpose and layout

These are small structural wrappers, not router shells. `dashboard/DashboardLayout` and `docs/DocsLayout` own their respective navigation. Files are exported through `index.ts` and use matching CSS modules.

- `Page.tsx`: Page, PageHeader, PageTitle (`h1`), PageDescription, PageActions, PageBody.
- `Section.tsx`: Section (`section`), SectionHeader, SectionTitle (`h2`), SectionDescription.
- `Stack.tsx`: vertical Stack, wrapping Inline, and Grid with named gaps.
- `FormLayout.tsx`: FormStack (an actual `form`), FieldGroup, FormActions.

## Composition and extension

Components forward native attributes and combine caller classes using `cn`. They apply token-backed layout defaults in inline styles, then spread caller styles so consumers can override them. Inspect both CSS and inline defaults before changing spacing. Stack gaps are `none`, `xs`, `sm`, `md`, `lg`, and `xl`, mapped to shared `--space-*` tokens; Inline defaults to wrapping and accepts alignment/justification. Grid does not supply every consumer's column definition.

Compose these wrappers to express page/section/form groups. Keep fetches, permissions, submit state, and business workflows out of layout. Add a new wrapper only for a demonstrated repeated structure, not every local flex row. There is also a separate `ui/grid.tsx`; inspect the import and behavior before assuming the two Grid exports are interchangeable.

## CSS and accessibility

Use the existing `.module.css` pattern and shared `--page-gap`, `--section-gap`, `--form-gap`, `--field-gap`, and spacing tokens. Existing inline token defaults are an intentional local pattern, not a reason for long static inline styling in pages. Preserve caller override order.

Keep heading hierarchy meaningful; wrappers do not automatically enforce one `h1` per page. Give sections headings or labels as appropriate. Do not nest FormStack inside another form. Non-submit actions inside forms need `type="button"`; labels and validation messages belong to controls/forms, not these structural wrappers.

## Verification

No layout tests are colocated here. For meaningful new behavior, add focused tests without assuming a browser-test dependency exists. Check consuming forms/pages at narrow widths with long titles/actions, wrapping, keyboard order, heading hierarchy, and both themes. From `spa/`, run focused ESLint and `yarn build` for code changes. A successful build alone does not verify spacing or overflow.
