# Legal Pages Guide

`Terms.tsx`, `Privacy.tsx`, and `PricingPolicy.tsx` are public policy documents at `/legal/terms`, `/legal/privacy`, and `/legal/pricing`. Each composes Navbar/Footer and a document layout with section navigation. They do not fetch policy content from a service.

## Layout and ownership

`Legal.module.css` is shared across all three pages: page/container/header, effective-date presentation, side navigation, content sections, and responsive layout. Policy wording and section IDs live in the individual TSX files. Public route titles/indexing live in `src/routes/publicPages.ts`, not in a second sitemap list.

## Changing policy

Edit the owning document, keep its section links and IDs synchronized, and update its displayed effective date when appropriate to the approved change. Privacy statements must match actual connected-service data use, storage/retention, and revocation behavior. Pricing policy must agree with `../Pricing.tsx`, checkout return wording, and Settings subscription actions. Do not turn intended behavior into a legal assertion without confirming it.

For another policy page, add its publicPages entry and App element mapping, then reuse the legal module and navigation pattern. Avoid extracting a generic policy framework for three static documents. Policy changes need the relevant human approval; a successful frontend build is not legal review.

## Verification

No colocated legal tests exist. From `spa/`: `yarn test src/routes/publicPages.test.ts`, `yarn eslint src/pages/legal`, then `yarn test`, `yarn lint`, `yarn build`. Use `yarn dev` to check all document navigation/hash targets, external links, date visibility, and mobile side-nav/content layout. Shared CSS changes require checking all three policies.
