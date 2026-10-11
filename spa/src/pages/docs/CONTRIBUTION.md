# Public Documentation Pages Guide

These are public product docs rendered inside `src/components/docs/DocsLayout.tsx`. Routing/indexing comes from `src/routes/publicPages.ts` plus `src/App.tsx`; the documentation layout owns navigation/chrome rather than each page duplicating Navbar/Footer.

## Layout

- `QuickStart.tsx`: setup, agents, knowledge bases, widget integration and guest behavior.
- `PublicApi.tsx`: server API-key integration and request/response examples.
- `AgentToAgent.tsx`: discovery, A2A credentials, sharing and protocol examples.
- `Automations.tsx`: chain/trigger/action/smart-value/import concepts with embedded `automations/AutomationSandbox.tsx` examples.
- `FAQ.tsx`: interactive question sections; its own `FAQ.module.css`.
- `QuickStart.module.css`: shared prose/section/example styles also imported by PublicApi, AgentToAgent, and Automations.
- `automations/`: simulated interactive tutorial, with a separate guide.

## Extending docs

Add a new public page to publicPages and App's public element map together, then update DocsLayout navigation where needed. Match section IDs to its TOC and incoming hash links; App's ScrollToHash depends on actual element IDs. Keep snippets aligned with real services/API/widget contracts and distinguish public widget keys, secret server keys, and A2A secrets. Never use actual credentials.

For an automation example, extend tutorial fixtures/adapter, not a separate imitation editor. Docs should describe supported behavior, with planned features labeled explicitly; don't infer support from historical release notes alone.

## CSS and verification

Most prose shares `QuickStart.module.css`; a change there affects four pages. FAQ owns a separate module; DocsLayout owns shared shell styling outside this directory. The sandbox combines its module with dashboard workspace global styles, so inspect both docs and dashboard for shared changes.

From `spa/`: `yarn test src/routes/publicPages.test.ts src/pages/dashboard/automations/chain/chain.test.ts`, `yarn eslint src/pages/docs`, then `yarn test`, `yarn lint`, `yarn build`. There are no colocated prose-page tests. Use `yarn dev` to check TOC/hash links, long code blocks, FAQ interaction, tutorial reset, and mobile layout; verify examples against the actual API contract when changing them.
