# Dashboard Pages Guide

These screens run under `/dashboard` inside `ProtectedRoute` and `DashboardLayout` in `src/App.tsx`. Read the parent pages guide and the feature guide before changing a nested module. Dashboard chrome lives in `src/components/dashboard/`, not here.

## Layout

- `Overview.tsx` aggregates agents, conversations, automations, knowledge bases, connector/MCP state, artifacts, and release notes. `Overview.css` owns globally scoped, prefixed `overview*` classes.
- `AgentsList.tsx` loads/deletes through `agentApiService`; `AgentCreate.tsx` fetches the create schema and renders `SchemaForm`. Detail tabs and marketplace have separate guides.
- `Conversations.tsx` loads conversations, agents, and default-agent preference, filters user-visible conversations, and creates the first conversation. `ConversationDetail.tsx` owns message paging, attachments, streaming, active-turn reattachment/stop, image generation, and canvas/form/connect UI. Reuse `src/components/chat/` and `chatService`; don't create another SSE parser here.
- `ArtifactsPage.tsx` lists durable artifacts; `ArtifactOpenPage.tsx` gets metadata and a view URL through `artifactApiService` before opening it. Keep retry/fallback links usable.
- `KnowledgeBases.tsx` owns collection CRUD. `KnowledgeBaseDetail.tsx` loads crawl jobs and upload schemas, polls job progress, retries/cancels crawls, and uploads files through `knowledgeApiService`. Respect upload limits/types and clear polling on cleanup.
- `Settings.tsx` combines provider configuration, OpenAI connection, appearance, default agent, subscription actions, suggestions, Dream, and A2A settings. Preserve `useCanManageSettings` affordances; the backend remains the authority for access and trusted origins.
- `ConnectorsPage.tsx` orchestrates the `connectors/` helpers. `WhatsNewPage.tsx` reuses public `ReleaseNotes` rather than maintaining a dashboard changelog.
- `oauth/OAuthPopupDone.tsx` is the small builder OAuth return screen: sends the typed `OAUTH_MESSAGE_TYPE` message to `window.opener` using `window.location.origin`. Keep its protocol aligned with `src/services/builder/connect.ts`; do not use a wildcard target origin. This tiny directory is covered here.

## Extension and CSS

Add protected routes in `src/App.tsx`, then update existing dashboard navigation where applicable. Resource tabs should remain nested routes with typed outlet context. Use backend schemas for configurable fields, not duplicate credential/trust validation. Carry existing access metadata into action visibility.

CSS Modules own AgentsList, Conversations, ConversationDetail (`Conversation.module.css`), KnowledgeBaseDetail, and Settings. Other root screens use shared layout/UI plus utility or inline styles; do not assume a missing local CSS file exists. New substantial styles should stay near the page and use semantic names/theme variables.

## Verification

From `spa/`, use `yarn test src/services/builder/connect.test.ts src/services/builder/ila.test.ts src/components/chat/toolActivityFormat.test.ts` for related chat/connect changes. There are no root dashboard page tests in this directory. Add focused behavior regressions for new logic, then run `yarn test`, `yarn lint`, and `yarn build`; focused lint example: `yarn eslint src/pages/dashboard/ConversationDetail.tsx`. Check streaming/reload/stop, denied actions, crawl polling cleanup, and responsive layouts with `yarn dev`. See nested guides for their existing tests.
