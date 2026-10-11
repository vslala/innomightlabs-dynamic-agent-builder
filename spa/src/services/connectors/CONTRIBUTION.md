# Connectors Service Guide

`ConnectorApiService.ts` owns connector starts, MCP connections/providers, OAuth discovery/start, stdio package/runtime operations, tool refresh and agent connection/sharing links. Types come from `src/types/connectors`.

- Connection CRUD under `/connectors/mcp` is distinct from agent attachment PUT/DELETE under `/agents/{id}/mcp-connections/{mcpId}`. Sharing views/updates belong to the attachment subresource; don't equate owning a connection with sharing it.
- Provider install and connection settings forms return `FormSchema`. Pass backend schema values rather than adding credential/allowlist validation here.
- `startConnector(path, payload)` accepts a supplied route; MCP OAuth discovery/start and install methods have explicit routes. Keep returned authorization URLs as flow results, not general dashboard HTTP endpoints.
- Runtime restart and tool-catalog refresh are explicit POSTs with `{}`; reads must not trigger those mutations. Backend controls execution and credentials.

No adjacent tests currently. Add connection-versus-link path tests, install-schema contracts and runtime POST tests; from `spa/`, run `yarn test src/services/connectors` once added. See [services guide](../CONTRIBUTION.md).
