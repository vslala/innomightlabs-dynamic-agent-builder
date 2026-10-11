# MCP Sharing Guide

This module lets an owner delegate a connector's selected tools through one agent. It is opened by `AgentMCPToolsPage.tsx`, not a standalone route. Owner access and delegated access are different: the owner retains tools while the allowlist constrains the chosen audiences.

## Layout and flow

`MCPSharingDialog.tsx` loads `getAgentMCPSharing(agentId, mcpId)`, creates a draft, refreshes the tool catalog when requested, saves through `updateAgentMCPSharing`, then reloads the caller and closes. `AudiencePicker.tsx` uses parent `audiences.ts`; `ToolAllowlist.tsx` presents/searches risk-grouped tools; `SharingDisclaimer.tsx` renders backend disclaimer paragraphs and acceptance; `SharingSummary.tsx` renders the compact summary.

`sharingDraft.ts` owns pure draft/request behavior; `sharingDraft.test.ts` protects it:

- First sharing preselects read-only tools only, with no audiences and no consent.
- Existing shares retain only tools still offered. Catalog refresh drops retired selections rather than selecting newly offered write/destructive tools.
- Sharing requires an audience, a tool, and explicit acceptance; acceptance starts false when the dialog opens.
- Clearing audiences stops sharing and sends empty audience/tool lists.
- Requests use the disclaimer version from the loaded backend view, not a hardcoded version.

## Extension and CSS

Change selection/risk/request semantics in `sharingDraft.ts` and test them before wiring controls. New audience labels belong in the shared audience list and must agree with backend types/policy. UI checks are affordances, not authorization. Keep saving errors visible and prevent closing while saving.

`MCPSharingDialog.module.css` is shared by dialog subcomponents and owns this module's layout. Keep scoped classes there, use shared UI primitives/theme variables, and preserve accessible selection and consent controls.

## Verification

From `spa/`: `yarn test src/pages/dashboard/agent-detail/mcp-sharing/sharingDraft.test.ts`, `yarn eslint src/pages/dashboard/agent-detail/mcp-sharing`, then `yarn test`, `yarn lint`, `yarn build`. Manually check first share, catalog failure/refresh, retired tools, stop sharing, and backend save errors.
