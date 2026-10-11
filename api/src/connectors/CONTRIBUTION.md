# Connectors Contribution Guide

`connectors/` owns what an account has connected to the outside world. The top level is the small set of Google OAuth connectors that skills depend on (Drive, Gmail, Ads). `mcp/` is the larger half: MCP (Model Context Protocol) servers an account installs, links to agents, shares, and calls on an agent's behalf. Connections belong to the account; admins manage them, any member may list them.

## Layout

```text
src/connectors/
  models.py            ConnectorDefinition / ConnectorStatus (Google connectors)
  service.py           CONNECTORS registry + ConnectorService (connected = a ProviderSettings record exists)
  router.py            /connectors (list) and /connectors/{id}/start (Google OAuth start)
  oauth_completion.py  POST /connectors/oauth/complete: the signed-in half of every connect flow
  mcp/
    models.py          Request/response models, MCPConnection, AgentMCPConnection, MCPToolCatalog, sharing
    repository.py      DynamoDB access for the three MCP item types
    service.py         MCPConnectorService: create/install/update, linking, sharing, tool listing and calls
    router.py          /connectors/mcp/* (router) and the OAuth callback (public_router)
    client.py          Streamable HTTP MCP client, MCPClientError
    oauth.py           PKCE state, discovery, dynamic client registration, token exchange/refresh
    delivery.py        OAuthDelivery strategies: how a token reaches a server (BearerHeader, AccessTokenEnv)
    resolved.py        HttpTarget / StdioTarget / OAuthBinding / ResolvedConnection
    resolvers.py       Custom connections: stored config -> ResolvedConnection
    providers/         Catalog presets (one file each) + resolver.py for catalog installs
    sidecar.py         Client for hosted stdio servers on infra-cli-runner
    usage.py           Per-call audit rows and daily counters
    disclaimer.py      Sharing consent text and its version
    runtime_tools.py   The list_mcp_tools / call_mcp_tool tool definitions given to agents
```

## Conventions

- Split: `router.py` does HTTP and permission dependencies, `service.py` holds the logic and raises `ValueError`, `repository.py` is only DynamoDB. Routers turn `ValueError` into 400, or 404 when the message contains "not found" (`_not_found_from_value_error`). Keep that wording if you want a 404.
- Keys (all in `mcp/models.py`, via `pk`/`sk` properties and `to_dynamo_item`):
  - `MCPConnection`: `pk=Account#{account_id}`, `sk=MCPConnection#{mcp_id}`.
  - `MCPToolCatalog`: same `pk`, `sk=MCPToolCatalog#{mcp_id}` (deleted with the connection).
  - `AgentMCPConnection` (the link plus its sharing): `pk=Agent#{agent_id}`, `sk=MCPConnection#{mcp_id}`.
  - Usage: `Agent#{agent_id}#MCPUsage` / `Day#...` counters, plus audit rows with a 90-day `ttl` (`usage.py`).
- Access: `Member` (`get_principal`) to list, `Manager` (`settings_manager`, action `settings:Manage`) to create, install, edit, delete, start OAuth. Linking and sharing go through `own_agent_with(...)` from `src/agents/access.py`: the agent's owner decides. Google connectors: `/start` needs `settings_manager`.
- Secrets (API keys, OAuth credentials, stdio env) are stored encrypted (`encrypted_auth_config`, `src.crypto`). Responses carry summaries, never secrets.
- Two kinds of connection: catalog installs (`provider_key` set, resolved by `providers/resolver.py`) and custom ones (`resolvers.py`). Both yield a `ResolvedConnection`; the service never branches on provider names.
- An unshared tool answers like a missing connector so callers cannot probe what exists (see `service.py`, sharing section). Preserve that.
- Setting: the OAuth redirect is `settings.mcp_oauth_redirect_uri` (`config/settings.py`, plus Terraform/Railway). Sidecar settings live in the same file.
- Gotcha: `/connectors/mcp/providers` is registered before `/connectors/mcp/{mcp_id}`; new fixed paths go above the parameterised ones.

## Add a catalog provider (the common change)

1. Copy `providers/github.py` (OAuth with the user's client), `providers/tavily.py` (API key) or `providers/atlassian.py` (discovered OAuth).
2. Define `PROVIDER = MCPProvider(key=..., inputs=(FormInput, ...), target=..., oauth=...)`. `key` is the stable id stored on installs: never rename it. Password inputs are the secrets; `transport` must match the target type.
3. Register it in `providers/resolver.py` (`PROVIDERS`). Nothing else changes: the install form, listing and resolution come from the preset.
4. Add a case to `tests/test_mcp_providers.py`.

New OAuth token-delivery style: add a class implementing `OAuthDelivery` in `delivery.py`. New Google connector: add to `CONNECTORS` in `service.py` and a flow in `auth/router.py`.

## Testing

```bash
uv run pytest tests/test_connectors_router.py tests/test_mcp_*.py tests/test_blueprints_mcp.py -q
uv run ruff check src/connectors && uv run mypy src/connectors
```

`tests/test_mcp_connectors.py` has the fakes (`FakeMCPRepository`, `FakeMCPUsage`, `FakeOAuthMCPClient`, `make_agent`) that other MCP tests import; build the service with them rather than hitting moto or the network. Router tests use `test_client`/`auth_headers` from `tests/conftest.py`. Never call a real MCP server in tests.

## Do / Don't

- Do put provider-specific behaviour in its `providers/<name>.py` preset, not in `service.py`.
- Do choose a delivery strategy over an `if` on the provider.
- Do keep secrets out of logs and responses.
- Don't add a provider field that only one preset uses to the shared models; use a form input.
- Don't read connections by account from a request body; take `principal.account_id`.
- Don't add comments that restate the code; explain why (see the GitHub read-only header).
