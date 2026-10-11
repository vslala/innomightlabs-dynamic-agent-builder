# Dashboard Pages Guide

These screens run under `/dashboard` inside `ProtectedRoute` and `DashboardLayout` in `src/App.tsx`. Read the parent pages guide and the feature guide before changing a nested module. Dashboard chrome lives in `src/components/dashboard/`, not here.

## Layout

- `Overview.tsx` loads agents, conversations, automations, knowledge bases and connector/MCP state (a failed request leaves its part empty) and hands them to `OverviewContent.tsx`, the pure view that `OverviewContent.test.tsx` renders. The view is a summary strip, recent work, a setup checklist that disappears once complete, and the latest release; navigation stays in the sidebar, so it carries no feature shortcuts. `Overview.module.css` owns its scoped styles. Keep the loader and the view in separate files: `lazyRoute` requires every export of a routed module to be a component.
- `AgentsList.tsx` loads/deletes through `agentApiService`; `AgentCreate.tsx` fetches the create schema and renders `SchemaForm`. Detail tabs and marketplace have separate guides.
- `Conversations.tsx` loads conversations, agents, and default-agent preference, filters user-visible conversations, and creates the first conversation. `ConversationDetail.tsx` owns message paging, attachments, streaming, active-turn reattachment/stop, image generation, and canvas/form/connect UI. Reuse `src/components/chat/` and `chatService`; don't create another SSE parser here.
- `ArtifactsPage.tsx` loads up to 100 durable artifacts and owns selection, single/bulk delete confirmation, requests, and feedback. `ArtifactsPagePanel.tsx` is the view; `artifactDeletion.ts` owns selection/result/confirmation helpers and `ArtifactsPage.module.css` owns local styles. `ArtifactOpenPage.tsx` gets metadata and a view URL through `artifactApiService` before opening it. Keep retry/fallback links usable.
- `KnowledgeBases.tsx` owns collection CRUD. `KnowledgeBaseDetail.tsx` loads crawl jobs and upload schemas, polls job progress, retries/cancels crawls, and uploads files through `knowledgeApiService`. Respect upload limits/types and clear polling on cleanup.
- `Settings.tsx` combines provider configuration, OpenAI connection, appearance, default agent, subscription actions, suggestions, Dream, and A2A settings. Preserve `useCanManageSettings` affordances; the backend remains the authority for access and trusted origins.
- [IAM](iam/CONTRIBUTION.md) supplies the Members panel and staged email-only invitation form. Access comes from backend IAM capabilities, not account role labels; sending is intentionally unavailable until Phase 2.
- `ConnectorsPage.tsx` orchestrates the `connectors/` helpers. `WhatsNewPage.tsx` reuses public `ReleaseNotes` rather than maintaining a dashboard changelog.
- `oauth/OAuthPopupDone.tsx` is the small builder OAuth return screen: sends the typed `OAUTH_MESSAGE_TYPE` message to `window.opener` using `window.location.origin`. Keep its protocol aligned with `src/services/builder/connect.ts`; do not use a wildcard target origin. This tiny directory is covered here.

## Extension and CSS

Add protected routes in `src/App.tsx`, then update existing dashboard navigation where applicable. Resource tabs should remain nested routes with typed outlet context. Use backend schemas for configurable fields, not duplicate credential/trust validation. Carry existing access metadata into action visibility.

CSS Modules own AgentsList, Conversations, ConversationDetail (`Conversation.module.css`), ArtifactsPage (`ArtifactsPage.module.css`), KnowledgeBaseDetail, and Settings. Other root screens use shared layout/UI plus utility or inline styles; do not assume a missing local CSS file exists. New substantial styles should stay near the page and use semantic names/theme variables.

## KAN-21 artifact deletion

Use the typed [artifact service](../../services/artifacts/CONTRIBUTION.md) and shared UI primitives (`ConfirmationDialog`, `Checkbox`, `Button`, `Alert`); no direct HTTP or global artifact stylesheet. Individual delete actions and row checkboxes are separate controls. “Select all loaded artifacts” includes mixed state and applies only to the currently loaded list (maximum 100), not every stored artifact.

Single and bulk actions open destructive confirmation with a frozen ID snapshot. Lock selection/reload/delete while confirmation is open or deletion is in flight; cancellation issues no request and the synchronous in-flight guard prevents double confirmation. Ignore stale loads and intersect retained selection with IDs still loaded after refresh.

Only remove IDs reported successfully completed after the request resolves (single 204 or bulk 200 `deleted_ids`), including idempotent no-ops for absent IDs. Missing/wrong-owner IDs succeed because they are absent from the caller's partition; foreign artifacts remain untouched. Partial failures represent only actual `DELETE_FAILED` results and stay visible and selected for retry; use safe count-based feedback, never raw provider messages. Keep dismissible, accessible feedback outside the nonempty list so it survives deletion of the last artifact. A request failure must not optimistically remove rows. S3 and metadata deletion are not atomic: failure can occur after bytes are removed, and retries tolerate missing bytes. Existing conversation references are not removed; their deleted content becomes unavailable, but conversations are not deleted.

## Verification

From `spa/`, use `yarn test src/services/builder/connect.test.ts src/services/builder/ila.test.ts src/components/chat/toolActivityFormat.test.ts` for related chat/connect changes. Artifact deletion regressions should cover `artifactDeletion.test.ts` (selection, idempotent completed-ID removal, partial results containing only real `DELETE_FAILED` failures, safe errors, frozen confirmation/cancellation/double-confirm guards) and `ArtifactsPagePanel.test.tsx` (rendered markup and direct control handlers, locking, select-all/mixed state, existing open links, and feedback after the last deletion). The panel tests do not simulate browser interaction or mount the full page. `OverviewContent.test.tsx` tests the overview view. For KAN-21, run:

```bash
yarn test src/services/artifacts/ArtifactApiService.test.ts src/pages/dashboard/artifactDeletion.test.ts src/pages/dashboard/ArtifactsPagePanel.test.tsx
yarn eslint src/pages/dashboard/ArtifactsPage.tsx src/pages/dashboard/ArtifactsPagePanel.tsx src/pages/dashboard/artifactDeletion.ts src/pages/dashboard/artifactDeletion.test.ts src/pages/dashboard/ArtifactsPagePanel.test.tsx
```

Add focused behavior regressions for new logic, then run `yarn test`, `yarn lint`, and `yarn build`; focused lint example: `yarn eslint src/pages/dashboard/ConversationDetail.tsx`. Check streaming/reload/stop, denied actions, crawl polling cleanup, and responsive layouts with `yarn dev`. See nested guides for their existing tests.
