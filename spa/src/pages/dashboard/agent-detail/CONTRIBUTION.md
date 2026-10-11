# Agent Detail Guide

`/dashboard/agents/:agentId` is a nested resource workspace. `AgentDetailLayout.tsx` loads the agent via `agentApiService` and supplies the outlet; `types.ts` exposes `useAgentDetailContext`. `AgentSideNav.tsx` owns tab links and checks Dream availability. Add tabs to both `src/App.tsx` and this navigation, then consume the existing context rather than loading a second independent agent record.

## File map and flows

| File | Ownership |
| --- | --- |
| `AgentOverviewPage.tsx` | Update SchemaForm, readiness summaries, marketplace publication, A2A sharing toggle |
| `AgentMemoryPage.tsx` | List/create/delete memory blocks and lazily load/edit their content through `memoryApiService` |
| `AgentDreamPage.tsx` | Dream runs, cursor, selected-run action audit, run-now through `dreamApiService` |
| `AgentKnowledgeBasesPage.tsx` | List attached/available bases and link/unlink through `knowledgeApiService` |
| `AgentSkillsPage.tsx` | Discover/install/configure/enable/uninstall skills, connector and OAuth returns, audience selection through skill/connector services |
| `AgentMCPToolsPage.tsx` | Attach/enable/remove connector bindings and launch `mcp-sharing/` |
| `AgentApiKeysPage.tsx` | Widget keys, guest opt-in, A2A secret issuance; composes SecretKeysCard and WidgetSnippets |
| `SecretKeysCard.tsx` | Server key lifecycle, one-time secret display, usage through `secretKeyService` |
| `WidgetSnippets.tsx` | Distinct iframe-embed and classic-widget snippets using a public key |
| `AgentA2ATasksPage.tsx` | Context/task selection, statuses, messages, copyable IDs, collapsed raw JSON |
| `AgentAnalyticsPage.tsx` | Thin entry point to `analytics/` |
| `audiences.ts`, `SkillSharingBadge.tsx` | Shared audience labels and owner-only/shareable affordances |

A successful agent edit updates the parent context. Skill installation fetches a schema, submits typed config, and displays backend errors; trusted-origin policy belongs in Settings/API, not a second page validator. Keep widget public keys separate from server secrets and A2A credentials; do not persist newly revealed secrets in browser storage.

## CSS ownership

Layout, memory, API keys, SecretKeysCard, and WidgetSnippets use their named `.module.css` files. Overview, SideNav, Skills, and A2ATasks use named plain CSS files with feature-prefixed global selectors. Dream, knowledge-base bindings, and MCP bindings currently compose shared UI/layout and utilities. Analytics and MCP sharing document their own styling. Keep new selectors with the owning screen, and don't leak generic global card/button rules.

## Verification

From `spa/`: `yarn test src/pages/dashboard/agent-detail/mcp-sharing/sharingDraft.test.ts src/services/apikeys/ApiKeyService.test.ts`; focused lint: `yarn eslint src/pages/dashboard/agent-detail`. Finish code changes with `yarn test`, `yarn lint`, `yarn build`. Manually check direct tab URLs, agent edit propagation, owner-only actions, guest opt-in, one-time key display, and OAuth return/error states. Most tabs have no colocated tests yet; add tests for newly extracted behavior rather than claiming existing UI coverage.
